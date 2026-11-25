"""Budgeted WebRouter research. Each Build owns its receipts and evidence."""
import asyncio
import os
import re
import time
from urllib.parse import urlsplit

from web_router import AsyncWebRouter
from web_router import ExtractFailedError

from evidence import FIELDS, Support, amounts, headcount, sentences, unknown_fields


TOPICS = {
    "legal_name": "legal name registered company legal entity corporate registry",
    "hq_city": "headquarters city head office location based in",
    "ceo": "CEO chief executive officer leadership",
    "founded_year": "founded established year company history",
    "headcount_range": "headcount employees workforce staff people",
    "funding_total": "funding total equity raised investment financing",
}
DESCRIPTIONS = {
    "legal_name": "registered legal name, including its legal-form suffix",
    "hq_city": "headquarters city, without the region or country",
    "ceo": "full name of the current chief executive officer",
    "founded_year": "year the company was founded, as an integer",
    "headcount_range": "company employee count as a range of 1-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001-10000, or 10001+",
    "funding_total": "total equity funding in whole US dollars, as an integer",
}


def citation_schema(field):
    typ = "integer" if field in ("funding_total", "founded_year") else "string"
    return {
        "type": "object",
        "properties": {
            "value": {"type": [typ, "null"], "description": DESCRIPTIONS[field]},
            "url": {"type": ["string", "null"], "description": "URL of the source page"},
            "excerpt": {"type": ["string", "null"], "description": "Verbatim single sentence from that page naming the company, the field and the value"},
        },
        "required": ["value", "url", "excerpt"], "additionalProperties": False,
    }


SCHEMA = {"type": "object", "properties": {f: citation_schema(f) for f in FIELDS}, "required": list(FIELDS), "additionalProperties": False}


class Providers:
    def __init__(self):
        self.available = [p for p in ("nimble", "tavily") if os.environ.get(p.upper() + "_API_KEY")]
        nimble_host = urlsplit(os.environ.get("NIMBLE_BASE_URL") or "https://sdk.nimbleway.com").hostname
        self.live = nimble_host == "sdk.nimbleway.com"
        self.timeout = 55 if self.live else 4
        config = {"nimble": {"max_retries": 0, "timeout": self.timeout}}
        if os.environ.get("TAVILY_BASE_URL"):
            config["tavily"] = {"api_base_url": os.environ["TAVILY_BASE_URL"]}
        self.router = AsyncWebRouter(provider="nimble", provider_config=config)

    async def close(self):
        await self.router.aclose()


def claim_matches(field, claimed, supported):
    if type(claimed) is type(supported) and claimed == supported:
        return True
    if field == "headcount_range" and str(claimed).replace(",", "").isdigit():
        return headcount(int(str(claimed).replace(",", ""))) == supported
    if field in ("funding_total", "founded_year") and isinstance(claimed, str):
        if claimed.replace(",", "").isdigit():
            return int(claimed.replace(",", "")) == supported
        if field == "funding_total":
            return amounts(claimed) == {supported}
    return False


class Build:
    def __init__(self, domain, providers):
        self.domain = domain
        self.providers = providers
        self.support = Support(domain)
        self.succeeded = False
        self.spent = 0
        self.reserved = 0
        self.fields = unknown_fields()
        self.record = {"calls": [], "pages": [], "research": [], "candidates": []}
        self.full_urls = set()
        self.tried = set()
        self.task = None
        self.last_start = float("inf")

    def missing(self):
        return [field for field in FIELDS if self.fields[field]["value"] is None]

    def available_units(self):
        return 80 - self.spent - self.reserved

    async def call(self, provider, operation, argument, price, invoke):
        if time.monotonic() > self.last_start or price > self.available_units():
            return None
        self.reserved += price
        receipt = {"provider": provider, "operation": operation, "argument": argument, "units": price}
        self.record["calls"].append(receipt)
        try:
            result = await invoke()
        except asyncio.CancelledError:
            receipt["outcome"] = "interrupted"
            raise
        except Exception as exc:
            code = getattr(exc, "status_code", None)
            empty = operation == "extract" and (
                (isinstance(exc, ExtractFailedError) and not exc.call_errors) or code == 404
            )
            if empty:
                receipt["outcome"] = "no_page"
                self.succeeded = True
            elif code or getattr(exc, "kind", None) in ("auth", "rate_limit", "bad_request", "server"):
                receipt.update(units=0, outcome="refused")
            else:
                receipt["outcome"] = "connection_error"
            if code:
                receipt["http_status"] = code
            return None
        else:
            receipt["outcome"] = "answered"
            self.succeeded = True
            return result
        finally:
            self.reserved -= price
            self.spent += receipt["units"]

    def consider(self, field, value, citation):
        candidate = {"field": field, "value": value, "citation": citation}
        if candidate not in self.record["candidates"]:
            self.record["candidates"].append(candidate)
        if self.fields[field]["value"] is None:
            self.fields[field] = {"value": value, "status": "known", "citations": [citation]}

    def page(self, provider, url, body, title="", full=True):
        if not url or not body:
            return
        self.record["pages"].append({"provider": provider, "url": url, "text": body, "title": title, "full": full})
        if full:
            self.full_urls.add(url)
        for sentence in sentences(body):
            # A snippet can end in the middle of a value or before a qualification.
            if not full and not re.search(r'[.!?]["”’)]*$', sentence):
                continue
            citation = {"provider": provider, "url": url, "excerpt": sentence}
            for field, value in self.support.parse(sentence).items():
                self.consider(field, value, citation)

    async def search(self, provider, query, depth="lite"):
        cost = {"nimble": {"lite": 1, "deep": 15}, "tavily": {"lite": 8, "deep": 16}}[provider][depth]
        result = await self.call(provider, "search_" + depth, query, cost, lambda: self.providers.router.search(
            query, max_results=10, search_depth=depth, provider=provider, data_apis=False,
        ))
        if result is None:
            return None
        for item in result.results:
            self.page(provider, item.url, item.content or item.description, item.title, full=depth == "deep")
        return [item.url for item in result.results if item.url]

    async def extract(self, provider, url):
        self.tried.add((provider, url))
        result = await self.call(provider, "extract", url, 1 if provider == "nimble" else 2,
                                 lambda: self.providers.router.extract(url, provider=provider, data_apis=False))
        if result:
            for doc in result.documents:
                self.page(provider, doc.url, doc.content)

    async def gather_urls(self, provider, urls, reserve=0):
        urls = [u for u in dict.fromkeys(urls) if u not in self.full_urls and (provider, u) not in self.tried]
        capacity = max(0, self.available_units() - reserve) // (1 if provider == "nimble" else 2)
        if urls and capacity and self.missing():
            await asyncio.gather(*(self.extract(provider, url) for url in urls[:capacity]))

    def research_claim(self, field, value, provider, url, excerpt):
        if not isinstance(url, str) or not url or not isinstance(excerpt, str):
            return
        parts = list(sentences(excerpt))
        if len(parts) != 1:
            return
        sentence = parts[0]
        supported = self.support.parse(sentence).get(field)
        if supported is not None and claim_matches(field, value, supported):
            self.consider(field, supported, {"provider": provider, "url": url, "excerpt": sentence})

    def read_research(self, result):
        self.record["research"].append(result.model_dump(mode="json", include={"structured", "raw"}))
        structured = result.structured
        if not isinstance(structured, dict):
            return
        for field in FIELDS:
            claim = structured.get(field)
            value = claim.get("value") if isinstance(claim, dict) else claim
            if value is None:
                continue
            if isinstance(claim, dict):
                citations = claim.get("citations", [])
                citations = citations if isinstance(citations, list) else []
                for item in [claim, claim.get("citation"), *citations]:
                    if isinstance(item, dict):
                        self.research_claim(field, value, "nimble", item.get("url"), item.get("excerpt"))
            for cite in result.citations:
                path = (cite.field or "").strip("#$/").replace("/", ".").split(".")
                if field in path or not cite.field:
                    for excerpt in cite.extra.get("excerpts") or [cite.snippet]:
                        self.research_claim(field, value, "nimble", cite.url, excerpt)

    async def research(self):
        query = (f"Research the company at {self.domain}. Return its registered legal name, headquarters city, "
                 "CEO, founding year, employee range and total equity funding. For each value quote an exact "
                 "sentence from its source, containing the company's name and the fact. Use null for unsupported values.")
        job = await self.call("nimble", "research", query, 25, lambda: self.providers.router.submit_research(
            query, provider="nimble", output_schema=SCHEMA, effort="low",
        ))
        if job is None:
            return
        try:
            while not job.progress.is_terminal:
                if time.monotonic() > self.last_start:
                    return
                await job.astatus()
                if not job.progress.is_terminal:
                    await asyncio.sleep(0.15 if not self.providers.live else 1)
            if job.progress.response:
                self.read_research(job.progress.response)
        except Exception as exc:
            self.record["research"].append({"error": type(exc).__name__})

    async def exact_search(self):
        # A refusal never claims the one successful domain search. Back off and
        # give each configured provider another opportunity within the build.
        until = time.monotonic() + (20 if self.providers.live else 2.8)
        delay = 0.025
        while True:
            for provider in self.providers.available:
                depth = "lite" if provider == "nimble" else "deep"
                hits = await self.search(provider, self.domain, depth)
                if hits is not None:
                    return provider, hits
            if time.monotonic() + delay >= until or self.available_units() < 1:
                return self.providers.available[0], None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 0.3 if not self.providers.live else 2)

    async def gather(self):
        available = self.providers.available
        if not available:
            return
        provider, exact = await self.exact_search()
        await self.gather_urls(provider, exact or [])
        if not self.missing():
            return

        if "nimble" in available:
            queries = [f"{self.domain} {TOPICS[f]}" for f in self.missing()]
            hits = await asyncio.gather(*(self.search("nimble", q) for q in queries))
            urls = [url for result in hits if result for url in result]
            await self.gather_urls("nimble", urls, reserve=41 if "tavily" in available else 25)
        if not self.missing():
            return

        if "tavily" in available:
            query = self.domain + " " + " ".join(TOPICS[f] for f in self.missing())
            await self.search("tavily", query, "deep")
        if self.missing() and "nimble" in available:
            await self.research()
        if self.missing():
            # Discover additional first-party and registry pages with a focused query.
            topics = " ".join(TOPICS[f] for f in self.missing())
            if "nimble" in available:
                extras = await self.search("nimble", f"site:{self.domain} about company {topics}")
                await self.gather_urls("nimble", extras or [])
                if self.missing() and self.available_units() >= 15:
                    await self.search("nimble", f"{self.domain} company profile {topics}", "deep")
            if self.missing() and "tavily" in available:
                for field in self.missing():
                    if self.available_units() < 16:
                        break
                    await self.search("tavily", f"{self.domain} {TOPICS[field]}", "deep")

    async def run(self):
        # The live limit leaves enough time for a started call to get a full 30 seconds.
        if self.providers.live:
            self.last_start = time.monotonic() + 260
        try:
            async with asyncio.timeout(294 if self.providers.live else 9.2):
                await self.gather()
        except TimeoutError:
            self.record["deadline"] = True
