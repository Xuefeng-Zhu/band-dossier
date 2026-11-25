"""Per-build research through WebRouter, with units reserved before every call."""
import asyncio
import os
from functools import lru_cache
from urllib.parse import urlsplit

from web_router import (
    AsyncWebRouter, ConfigurationError, DeadlineExceededError, ExtractFailedError,
    InvalidParameterError, ProviderError, ResearchTimeoutError, UnsupportedFormatError,
    UnsupportedParameterError,
)

from evidence import FIELD_NAMES, blank_fields, sentences, values

TERMS = {
    "legal_name": "legal name registered name legal entity",
    "hq_city": "headquarters headquartered city head office",
    "ceo": "CEO chief executive leadership",
    "founded_year": "founded founding year company history",
    "headcount_range": "headcount employees workforce staff",
    "funding_total": "total equity funding raised investment",
}

@lru_cache(maxsize=1)
def router():
    config = {"nimble": {"max_retries": 0, "timeout": 60.0}}
    if endpoint := os.getenv("TAVILY_BASE_URL"):
        config["tavily"] = {"api_base_url": endpoint}
    return AsyncWebRouter(provider="nimble", provider_config=config, router=None)

def initialize():
    # Construct SDK clients during startup so several first requests can share their pools.
    service = router()
    for name in available():
        service.get_provider(name)
        service.get_extract_provider(name)
    if "nimble" in available():
        service.get_research_provider("nimble")

def available():
    return [p for p in ("nimble", "tavily") if os.getenv(p.upper()+"_API_KEY")]

def claim_schema():
    properties = {}
    for field in FIELD_NAMES:
        kind = "integer" if field in ("funding_total", "founded_year") else "string"
        properties[field] = {
            "type":"object", "properties":{
                "value":{"type":[kind,"null"], "description":TERMS[field]},
                "url":{"type":["string","null"], "description":"URL of the quoted source"},
                "excerpt":{"type":["string","null"], "description":"One verbatim source sentence naming the company and stating this fact"}
            }, "required":["value","url","excerpt"], "additionalProperties":False}
    return {"type":"object","properties":properties,"required":list(properties),"additionalProperties":False}

def valid_url(url):
    try:
        return isinstance(url,str) and urlsplit(url).scheme in ("https","http") and bool(urlsplit(url).hostname)
    except ValueError:
        return False

class Build:
    def __init__(self, domain):
        self.domain = domain
        self.succeeded = False
        self.spent = 0
        self.reserved = 0
        self.calls = []
        self.pages = []
        self.research_answers = []
        self.sources = {}
        self.fetched = set()
        self.full = set()
        self.candidates = {key:[] for key in FIELD_NAMES}
        self.snippets = {key:[] for key in FIELD_NAMES}

    def add(self, field, value, url, excerpt, provider, *, partial=False):
        citation = {"url":url,"excerpt":excerpt,"provider":provider}
        candidate = {"value":value,"citation":citation}
        options = self.snippets[field] if partial else self.candidates[field]
        if candidate not in options:
            options.append(candidate)

    def page(self, provider, url, text, title="", full=True):
        if not valid_url(url) or not text:
            return
        self.pages.append({"url":url,"provider":provider,"title":title,"text":text,"full":full})
        if full:
            self.full.add(url)
        for sentence, prose in sentences(text):
            for key,value in values(self.domain,prose).items():
                self.add(key,value,url,sentence,provider,partial=not full)

    def options(self, key):
        # Prefer a full page or supported research claim. A snippet remains evidence
        # when extraction is refused or the provider answers without the page.
        return self.candidates[key] or [c for c in self.snippets[key] if c["citation"]["url"] not in self.full]

    def fields(self):
        result = blank_fields()
        for key in FIELD_NAMES:
            if options := self.options(key):
                # Prefer the company's own source when there are competing supported claims.
                choice = next((c for c in options if (urlsplit(c["citation"]["url"]).hostname or "").removeprefix("www.") == self.domain), options[0])
                result[key] = {"status":"known","value":choice["value"],"citations":[choice["citation"]]}
        return result

    def missing(self):
        return [key for key in FIELD_NAMES if not self.options(key)]

    def record(self, when):
        return {"time":when,"calls":self.calls,"pages":self.pages,"answers":self.research_answers}

    async def call(self, provider, operation, argument, price, request):
        if self.spent + self.reserved + price > 80:
            return None
        self.reserved += price
        units, outcome = price, "no_answer"
        try:
            result = await request()
            self.succeeded = True
            outcome = "answered"
            return result
        except ExtractFailedError as exc:
            if not exc.call_errors:
                # The provider answered the request but could not retrieve this page.
                self.succeeded = True
                outcome = "missing_page"
            elif any(getattr(err, "status_code", None) for err in exc.call_errors):
                units, outcome = 0, "refused"
        except ProviderError as exc:
            if exc.status_code or exc.kind in ("auth", "rate_limit", "bad_request","not_found"):
                units, outcome = 0, "refused"
        except (DeadlineExceededError, ResearchTimeoutError, TimeoutError, OSError):
            # No answer arrived. The reserved price is still payable.
            pass
        except (ConfigurationError, InvalidParameterError, UnsupportedFormatError, UnsupportedParameterError) as exc:
            units, outcome = 0, type(exc).__name__
        except Exception as exc:
            # Without a confirmed refusal or local validation failure, keep the reservation.
            outcome = type(exc).__name__
        finally:
            self.reserved -= price
            self.spent += units
            self.calls.append({"provider":provider,"operation":operation,"argument":argument,"units":units,"outcome":outcome})
        return None

    async def search(self, provider, query, depth="lite"):
        price = {"nimble":{"lite":1, "fast":5, "deep":15}, "tavily":{"lite":8,"fast":16,"deep":16}}[provider][depth]
        result = await self.call(provider,"search_"+depth,query,price,
            lambda: router().search(query,provider=provider,search_depth=depth,max_results=10,timeout=55,data_apis=False))
        if result is None:
            return False
        for hit in result.results:
            if valid_url(hit.url):
                self.sources.setdefault(hit.url, provider)
                self.page(provider,hit.url,hit.content or hit.description,hit.title,full=depth=="deep")
        return True

    async def extract(self, provider, url):
        self.fetched.add((provider,url))
        result = await self.call(provider,"extract",url,1 if provider=="nimble" else 2,
            lambda: router().extract(url,provider=provider,format="markdown",timeout=55,data_apis=False))
        if result:
            for doc in result.documents:
                self.page(provider,doc.url,doc.content,doc.title)
                if doc.content:
                    self.full.add(url)

    async def read_sources(self, reserve=0):
        work = []
        remaining = 80 - self.spent - self.reserved - reserve
        for url,provider in self.sources.items():
            if url in self.full or (provider,url) in self.fetched:
                continue
            price = 1 if provider == "nimble" else 2
            if price <= remaining:
                remaining -= price
                work.append(self.extract(provider,url))
        await asyncio.gather(*work)

    def check_claim(self, field, claimed, cite):
        if not isinstance(cite,dict) or claimed is None:
            return
        url = cite.get("url") or cite.get("source_url")
        quote = cite.get("excerpt") or cite.get("snippet") or cite.get("quote")
        if not valid_url(url) or not isinstance(quote,str):
            return
        for sentence, prose in sentences(quote):
            value = values(self.domain,prose).get(field)
            if value is not None and (value == claimed or str(value) == str(claimed).strip()):
                self.add(field,value,url,sentence,"nimble")

    async def research(self):
        prompt = (f"Research the company identified by {self.domain}. Give its legal name, headquarters city, CEO, "
                  "founding year, employee range and total equity funding in whole US dollars. For each give the source "
                  "URL and a verbatim single sentence naming the company and stating the fact. Use null for unsupported facts.")
        job = await self.call("nimble","research",prompt,25,lambda: router().submit_research(
            prompt,provider="nimble",output_schema=claim_schema(),effort="low"))
        if not job:
            return
        job.poll_interval = 0.3
        job.poll_max_interval = 3
        try:
            result = await job.aresult(timeout=175)
        except Exception:
            return
        data = result.structured
        self.research_answers.append({"structured":data, "answer":result.answer,
            "citations":[c.model_dump() for c in result.citations]})
        if not isinstance(data,dict):
            return
        for field in FIELD_NAMES:
            claim = data.get(field)
            claimed = claim.get("value") if isinstance(claim,dict) else claim
            if isinstance(claim,dict):
                self.check_claim(field,claimed,claim)
                self.check_claim(field,claimed,claim.get("citation"))
                for cite in claim.get("citations") or []:
                    self.check_claim(field,claimed,cite)
            for citation in result.citations:
                if (citation.field or "").lstrip("$./").split(".")[0] == field:
                    for snippet in citation.extra.get("excerpts") or [citation.snippet]:
                        self.check_claim(field,claimed,{"url":citation.url,"excerpt":snippet})

    async def exact_search(self, providers):
        for provider in providers:
            depth = "lite" if provider == "nimble" else "deep"
            if await self.search(provider, self.domain, depth):
                return True
        return False

    async def recover_exact(self, providers):
        # Recovery overlaps field discovery. Reserve the extraction wave until
        # this loop has either succeeded or exhausted its bounded retry window.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 4
        pause = 0.125
        while self.spent + self.reserved < 80:
            if await self.exact_search(providers):
                return
            if loop.time() + pause >= deadline:
                return
            await asyncio.sleep(pause)
            pause = min(1, 2 * pause)

    async def investigate(self):
        providers = available()
        if not providers:
            return
        # First use the inexpensive index and read each distinct URL it found.
        exact = await self.exact_search(providers)
        await self.read_sources()
        missing = self.missing()
        if not missing:
            return
        # Discover pages hidden behind field-specific queries and ask for independently cited claims.
        jobs = [] if exact else [self.recover_exact(providers)]
        if "nimble" in providers:
            jobs.append(self.research())
            jobs.extend(self.search("nimble", f"{self.domain} {key} {TERMS[key]}") for key in missing)
        if "tavily" in providers:
            query = self.domain + " " + " ".join(TERMS[key] for key in missing)
            jobs.append(self.search("tavily",query,"deep"))
        await asyncio.gather(*jobs)
        if self.missing():
            await self.read_sources()
        # Full search bodies can still be available when extraction is refused or returns no page.
        if self.missing() and "nimble" in providers:
            terms = " ".join(TERMS[k] for k in self.missing())
            await self.search("nimble", f"{self.domain} company profile about {terms}", "deep")

    async def run(self):
        try:
            async with asyncio.timeout(290):
                await self.investigate()
        except TimeoutError:
            pass
