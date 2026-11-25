import asyncio
import os
import re
from web_router import AsyncWebRouter
from web_router.exceptions import ProviderError
from evidence import Evidence, PHRASES, own

QUERIES = {
    "legal_name": "registered legal name company terms of service",
    "hq_city": "headquarters headquartered in city",
    "ceo": "current CEO chief executive officer leadership",
    "founded_year": "year founded established company history",
    "headcount_range": "employees headcount workforce size",
    "funding_total": "total equity funding raised to date",
}
SCHEMA = {"type": "object", "properties": {
    f: {"type": ["integer" if f in ("funding_total", "founded_year") else "string", "null"]} for f in PHRASES
}, "required": list(PHRASES)}

# Space starts across dossiers so concurrent discovery batches do not overflow
# a provider's connection accept queue. In-flight calls still run concurrently.
next_start = {}

async def provider_turn(provider):
    loop = asyncio.get_running_loop()
    now = loop.time()
    start = max(now, next_start.get(provider, now))
    next_start[provider] = start + 0.005
    if start > now:
        await asyncio.sleep(start-now)

def initialize():
    settings = {"nimble": {"max_retries": 0, "timeout": 42}, "tavily": {"timeout": 42}}
    if os.environ.get("TAVILY_BASE_URL"):
        settings["tavily"]["api_base_url"] = os.environ["TAVILY_BASE_URL"]
    router = AsyncWebRouter("nimble", provider_config=settings)
    for name in ("nimble", "tavily"):
        if os.getenv(name.upper() + "_API_KEY"):
            router.get_provider(name)
            router.get_extract_provider(name)
            if name == "nimble":
                router.get_research_provider(name)
    return router

def error_chain(exc):
    while exc:
        yield exc
        exc = getattr(exc, "original", None) or exc.__cause__

def http_status(exc):
    for error in error_chain(exc):
        status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
        if isinstance(status, int) and status >= 400:
            return status
        match = re.search(r"(?:Error code: |status(?: code)?[ :=]+|HTTP[/\w.]* )([45]\d\d)", str(error), re.I)
        if match:
            return int(match[1])
    return None

def missing_page(exc, requested, status):
    if isinstance(exc, ProviderError) and exc.original is None and "no URL could be extracted" in str(exc):
        return True
    if status is None:
        return False
    for error in error_chain(exc):
        payload = getattr(error, "body", None)
        if not isinstance(payload, dict):
            continue
        if payload.get("url") == requested and (
            payload.get("status") in ("failed", "fatal", "error") or payload.get("status_code") in (404, 410)
        ):
            return True
        message = str(payload.get("message", "")) + " " + str(payload.get("warnings", ""))
        if re.search(r"(?:no page|page not found|page (?:is |was )?(?:missing|gone)|URL not found)", message, re.I):
            return True
    return False

class Build:
    def __init__(self, domain, router, on_spend):
        self.domain, self.router = domain, router
        self.on_spend = on_spend
        self.started = asyncio.get_running_loop().time()
        self.deadline = self.started + 284
        self.slow_provider = False
        self.recovering_exact = False
        self.used = self.reserved = 0
        self.success = False
        self.log = []
        self.evidence = Evidence(domain)
        self.urls = {}
        self.tried = set()
        self.exact_retry_after = {}
        self.providers = [p for p in ("nimble", "tavily") if os.getenv(p.upper() + "_API_KEY")]

    async def call(self, provider, method, request, units, invoke, reserve=0):
        if self.recovering_exact and (method != "search" or request != self.domain):
            reserve += 1 if "nimble" in self.providers else 8
        if self.used + self.reserved + units + reserve > 80 or self.deadline - asyncio.get_running_loop().time() < 32:
            return None
        self.reserved += units
        started = asyncio.get_running_loop().time()
        cost, outcome = 0, "queued"
        try:
            await provider_turn(provider)
            started = asyncio.get_running_loop().time()
            cost, outcome = units, "unanswered"
            result = await invoke()
            outcome = "answered"
            self.success = True
            return result
        except Exception as exc:
            status = http_status(exc)
            if method == "extract" and missing_page(exc, request, status):
                outcome = "empty"
                self.success = True
            elif status is not None or any(type(e).__module__.startswith("tavily") and "Error" in type(e).__name__ for e in error_chain(exc)):
                cost, outcome = 0, "refused"
                if status == 429 and method == "search" and request == self.domain:
                    self.exact_retry_after[provider] = asyncio.get_running_loop().time() + 1
            return None
        finally:
            if asyncio.get_running_loop().time() - started > 1.05:
                self.slow_provider = True
            self.reserved -= units
            self.used += cost
            self.on_spend(cost)
            self.log.append(dict(provider=provider, method=method, request=request, cost=cost, outcome=outcome))

    async def search(self, query, provider, reserve=0):
        cost = 1 if provider == "nimble" else 8
        result = await self.call(provider, "search", query, cost, lambda: self.router.search(query, provider=provider, max_results=10, search_depth="lite"), reserve)
        if result is None:
            return False
        for hit in result.results:
            self.urls.setdefault(hit.url, (hit.title, hit.published_date or ""))
            self.evidence.add(hit.url, hit.content, provider, "snippet", hit.title, hit.published_date or "")
        return True

    async def extract(self, url, provider, reserve=0):
        if (url,provider) in self.tried:
            return
        self.tried.add((url,provider))
        result = await self.call(provider, "extract", url, 1 if provider == "nimble" else 2,
                                 lambda: self.router.extract(url, provider=provider), reserve)
        if result:
            for doc in result.documents:
                title, date = self.urls.get(url, ("", ""))
                self.evidence.add(doc.url, doc.content, provider, "page", doc.title or title, doc.published_date or date)

    async def research(self):
        query = (f"Research {self.domain}. Provide its six company profile fields with verbatim, single-sentence "
                 "source excerpts naming the company and explicitly stating each fact. Prefer dated first-party "
                 "statements. For funding, report total equity raised, in whole US dollars.")
        job = await self.call("nimble", "research", query, 25, lambda: self.router.submit_research(query, provider="nimble", output_schema=SCHEMA))
        if job is None:
            return
        try:
            result = await job.aresult(timeout=min(150, self.deadline - asyncio.get_running_loop().time()))
        except Exception:
            return
        for cite in result.citations:
            f = (cite.field or "").removeprefix("$.")
            if not isinstance(result.structured, dict) or f not in PHRASES or result.structured.get(f) is None:
                continue
            for quote in cite.extra.get("excerpts") or [cite.snippet]:
                if isinstance(quote, str):
                    self.evidence.add(cite.url, quote, "nimble", "research", cite.title, claim=[f, result.structured[f]])

    def missing(self):
        return [f for f, field in self.evidence.fields().items() if field["value"] is None]

    def ranked_urls(self):
        label = self.domain.split(".")[0]
        def priority(url):
            title, _ = self.urls[url]
            return (own(url, self.domain), label in url.lower() or label.replace("-", " ") in title.lower())
        return sorted(self.urls, key=priority, reverse=True)

    async def recover_exact(self, other_work):
        # Endpoint recovery follows the actual response time and the build's
        # remaining allowance. Field gathering can proceed during backoff.
        loop = asyncio.get_running_loop()
        backoff = 0.05
        while self.used + self.reserved < 80:
            stop = self.deadline - 32 if self.slow_provider else self.started + 7
            if loop.time() >= stop:
                break
            for provider in self.providers:
                delay = max(backoff, self.exact_retry_after.get(provider, 0) - loop.time())
                if loop.time() + delay >= stop:
                    await asyncio.sleep(max(0,stop-loop.time()))
                    return None
                await asyncio.sleep(delay)
                if await self.search(self.domain, provider):
                    return provider
            if other_work.done() and not self.success:
                break
            if stop - loop.time() <= backoff:
                break
            backoff = min(backoff * 1.7, 0.5)
        return None

    async def collect(self):
        if not self.providers:
            return
        for provider in self.providers:
            if await self.search(self.domain, provider):
                await self.collect_pages(provider)
                return
        self.recovering_exact = True
        try:
            async with asyncio.TaskGroup() as group:
                gather = group.create_task(self.collect_pages(self.providers[0]))
                recovery = group.create_task(self.recover_exact(gather))
        finally:
            self.recovering_exact = False
        provider = recovery.result()
        if provider and self.missing():
            await asyncio.gather(*(self.extract(u, provider) for u in self.ranked_urls()))

    async def collect_pages(self, provider):
        root = "https://" + self.domain
        home = [url for url in self.urls if own(url, self.domain)]
        seed = list(dict.fromkeys(home + ([root + "/"] if not home else [])))
        reserve = 25 if "nimble" in self.providers else 0
        await asyncio.gather(*(self.extract(url, provider, reserve) for url in seed))
        if not self.missing():
            # A result snippet may end in the middle of a fact. Obtain the
            # full page of any leading candidate still known only from search.
            winners = self.evidence.fields()
            selected = {field["citations"][0]["url"] for field in winners.values()}
            await asyncio.gather(*(self.extract(u, provider, reserve) for u in selected))
            return
        # Discover full pages behind the snippets before paying for further searches.
        await asyncio.gather(*(self.extract(u, provider, reserve) for u in self.ranked_urls()))
        missing = self.missing()
        if not missing:
            return
        await asyncio.gather(
            *(self.search(self.domain + " " + QUERIES[f], provider, reserve) for f in missing),
            *(self.extract(root + path, provider, reserve) for path in ["/about","/company","/leadership","/legal"]),
        )
        await asyncio.gather(*(self.extract(u, provider, reserve) for u in self.ranked_urls()))
        if self.missing() and "nimble" in self.providers:
            await self.research()
