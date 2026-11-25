"""One research transaction. Reserve worst-case units before each outbound dispatch."""
import asyncio
import os
import re
import time
from urllib.parse import urlsplit
from web_router import AsyncWebRouter
from web_router.exceptions_typed import ExtractFailedError
from evidence import Evidence, FIELDS

QUERIES = {
    "legal_name": "legal name registered company legal entity",
    "hq_city": "where is headquartered headquarters based in",
    "ceo": "CEO chief executive officer",
    "founded_year": "when was company founded established incorporated",
    "headcount_range": "number of employees people headcount workforce",
    "funding_total": "total equity funding raised investment dollars",
}
SCHEMA = {"type":"object","properties":{
    k: {"type":["integer" if k in ("funding_total","founded_year") else "string","null"]}
    for k in FIELDS}, "required":list(FIELDS)}
COST = {"nimble":{"lite":1,"deep":15,"extract":1,"research":25},
        "tavily":{"lite":8,"deep":16,"extract":2}}
_router = None

def router():
    global _router
    if _router is None:
        config = {"nimble":{"timeout":65, "max_retries":0}}
        if os.getenv("TAVILY_BASE_URL"):
            config["tavily"] = {"api_base_url":os.environ["TAVILY_BASE_URL"]}
        _router = AsyncWebRouter(provider="nimble",provider_config=config)
    return _router

def completed_page_failure(exc):
    """Find a billed target-fetch outcome wrapped in an SDK HTTP exception."""
    while exc is not None:
        body = getattr(exc, "body", None)
        if isinstance(body, dict) and body.get("task_id"):
            status = str(body.get("status", "")).lower()
            failed = status in {"failed", "error", "blocked"} or str(body.get("success")).lower() == "false"
            # A task's page status is distinct from the HTTP status of the provider endpoint.
            page_status = body.get("target_status_code") or body.get("status_code")
            message = str(body.get("message", ""))
            target_response = re.search(
                r"\b(?:server|origin|target|website|page)\b.{0,80}?\b[45][0-9]{2}\b", message, re.I)
            if failed and (page_status or target_response):
                return True
        exc = getattr(exc, "original", None) or exc.__cause__
    return False

def refused(exc):
    while exc is not None:
        if getattr(exc,"status_code",None) or getattr(getattr(exc,"response",None),"status_code",None):
            return True
        if getattr(exc,"kind",None) in ("auth","rate_limit","invalid_request"):
            return True
        exc = getattr(exc, "original", None) or exc.__cause__
    return False

class Build:
    def __init__(self, domain, at):
        self.domain = domain
        self.at = at
        self.started = time.monotonic()
        self.evidence = Evidence(domain)
        self.spent = self.reserved = 0
        self.success = False
        self.calls = []
        self.sources = []
        self.research_answer = None
        self.discovered = {}
        self.attempted = set()
        self.full = set()
        self.providers = [p for p in COST if os.getenv(p.upper() + "_API_KEY")]

    @property
    def missing(self):
        return [f for f in FIELDS if not self.evidence.candidates[f]]

    async def call(self, provider, method, args, invoke):
        cost = COST[provider][method]
        if self.spent + self.reserved + cost > 80 or time.monotonic()-self.started >= 250:
            return None
        self.reserved += cost
        entry = {"provider":provider,"method":method,"request":args,"units":0}
        self.calls.append(entry)
        try:
            response = await invoke()
        except ExtractFailedError:
            # A completed call with a page-level failure still bought an extract.
            self.success = True
            entry["outcome"] = "empty"
        except Exception as exc:
            entry["outcome"] = type(exc).__name__
            if provider == "nimble" and method == "extract" and completed_page_failure(exc):
                self.success = True
                entry["outcome"] = "empty"
            elif refused(exc):
                cost = 0
        else:
            self.success = True
            entry["outcome"] = "ok"
            return response
        finally:
            self.reserved -= COST[provider][method]
            self.spent += cost
            entry["units"] = cost

    def source(self, provider, url, text, **kwargs):
        if not text or not url:
            return
        self.sources.append({"provider":provider,"url":url,"text":text,**kwargs})
        self.evidence.add(url,text,provider,**kwargs)

    async def search(self, query, provider, depth="lite"):
        response = await self.call(provider,depth,query,lambda:router().search(
            query,provider=provider,search_depth=depth,max_results=10,timeout=65,data_apis=False))
        if response is None:
            return False
        for result in response.results:
            self.discovered.setdefault(result.url,provider)
            if depth == "deep" and result.content:
                self.full.add(result.url)
            self.source(provider,result.url,result.content)
            if result.description and result.description != result.content:
                self.source(provider,result.url,result.description)
        return True

    async def extract(self,url,provider):
        self.attempted.add((provider,url))
        response = await self.call(provider,"extract",url,lambda:router().extract(
            url,provider=provider,timeout=65,data_apis=False))
        if response:
            for doc in response.documents:
                if doc.content:
                    self.full.add(url)
                self.source(provider,doc.url,doc.content)

    async def full_pages(self,limit,provider=None):
        if not self.providers:
            return
        p = provider or self.providers[0]
        def priority(url):
            try:
                host = urlsplit(url).hostname or ""
            except ValueError:
                return 2
            return 0 if host == self.domain or host.endswith("."+self.domain) else 1
        urls = [u for u in sorted(self.discovered,key=priority) if u not in self.full and (p,u) not in self.attempted and u.startswith(("https://","http://"))]
        await asyncio.gather(*(self.extract(u,p) for u in urls[:limit]))

    async def research(self):
        query = (f"Research {self.domain}, the company operating that website. Identify its registered legal name, "
                 "headquarters city, current CEO, founding year, employee count range and total equity funding "
                 "in US dollars. Use original, dated sources. Quote exact sentences naming the company.")
        job = await self.call("nimble","research",query,lambda:router().submit_research(
            query,provider="nimble",output_schema=SCHEMA))
        if job is None:
            return
        try:
            await job.astatus()
            response = await job.aresult(timeout=160)
        except Exception:
            return
        claimed = response.structured if isinstance(response.structured,dict) else {}
        self.research_answer = {"values":claimed, "citations":[{
            "url":c.url,"field":c.field,"snippet":c.snippet,"excerpts":c.extra.get("excerpts",[])
        } for c in response.citations]}
        for cite in response.citations:
            self.discovered.setdefault(cite.url,"nimble")
            field = (cite.field or "").lstrip("$./")
            if field in FIELDS and claimed.get(field) is not None:
                for quote in cite.extra.get("excerpts") or [cite.snippet]:
                    self.source("nimble",cite.url,quote,claim=(field,claimed[field]))

    async def gather(self):
        if not self.providers:
            return
        answered = None
        for p in self.providers:
            depth = "lite" if p == "nimble" else "deep"
            if await self.search(self.domain,p,depth):
                answered = p
                break
        if self.missing and answered:
            await self.full_pages(10)
        if not self.missing:
            return
        provider = answered or self.providers[0]
        await asyncio.gather(*(self.search(f"{self.domain} {QUERIES[f]}",provider) for f in self.missing))
        if self.missing:
            # Spend the inexpensive search and extract units first. Leave enough room
            # for a research-only source, even if none of the targeted pages suffices.
            remaining = 80 - self.spent - (25 if "nimble" in self.providers else 0)
            await self.full_pages(max(0,min(22, remaining // COST[self.providers[0]]["extract"])))
        if self.missing and "nimble" in self.providers:
            await self.research()
        if self.missing and answered:
            # A deeper search remains available when page extraction was refused.
            if not any(c["method"]=="extract" and c.get("outcome")=="ok" for c in self.calls):
                await self.search(f"{self.domain} company profile about leadership",answered,"deep")
            if self.missing and len(self.providers)>1:
                await self.full_pages(10,self.providers[1])
            if self.missing:
                for path in ("/about","/company","/about-us"):
                    self.discovered.setdefault(f"https://{self.domain}{path}",provider)
                await self.full_pages(6)
        if not answered:
            # A transient refusal must not prevent a successful bare-domain search.
            for p in self.providers:
                if await self.search(self.domain,p):
                    break

    async def run(self):
        try:
            async with asyncio.timeout(285):
                await self.gather()
        except TimeoutError:
            pass
        return self.evidence.fields()

    def archive(self):
        return {"at":self.at,"calls":self.calls,"sources":self.sources,"research":self.research_answer}
