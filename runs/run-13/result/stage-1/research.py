"""One metered WebRouter research session per dossier build."""
import asyncio
import os
import re
from urllib.parse import urlsplit

from nimble_python import AsyncNimble
from web_router import AsyncWebRouter
from web_router.exceptions_typed import ExtractFailedError

from evidence import Evidence, PHRASES

QUESTIONS = {
    "legal_name": "legal name registered company terms of service",
    "hq_city": "headquarters headquartered in based in city",
    "ceo": "CEO chief executive officer leadership",
    "founded_year": "founded established incorporated history",
    "headcount_range": "employs employees workforce total headcount",
    "funding_total": "total equity funding raised to date investment",
}


class Providers:
    def __init__(self):
        self.available = [p for p in ("nimble", "tavily") if os.getenv(p.upper() + "_API_KEY")]
        config = {}
        self.client = None
        if "nimble" in self.available:
            self.client = AsyncNimble(max_retries=0, timeout=42)
            config["nimble"] = {"async_client": self.client}
        if os.getenv("TAVILY_BASE_URL"):
            config["tavily"] = {"api_base_url": os.environ["TAVILY_BASE_URL"]}
        self.router = AsyncWebRouter(provider_config=config, router=None)

    async def close(self):
        await self.router.aclose()
        if self.client:
            await self.client.close()


def own(url, domain):
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return False
    return host == domain or host.endswith("." + domain)


class Build:
    def __init__(self, domain, providers):
        self.domain = domain
        self.providers = providers
        self.evidence = Evidence(domain)
        self.units = 0
        self.reserved = 0
        self.success = False
        self.calls = []
        self.pages = []
        self.extracted = set()
        self.deadline = asyncio.get_running_loop().time() + 285

    async def call(self, provider, method, target, cost, invoke):
        remaining = self.deadline - asyncio.get_running_loop().time()
        if remaining < 30 or self.units + self.reserved + cost > 80:
            return None
        self.reserved += cost
        record = {"provider": provider, "method": method, "target": target, "cost": 0}
        self.calls.append(record)
        billed, ok = cost, False
        try:
            async with asyncio.timeout(min(remaining, 45)):
                result = await invoke()
            ok = True
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # An extract can return HTTP 200 and report that no page was obtained.
            if isinstance(exc, ExtractFailedError) and not exc.call_errors:
                ok = True
            else:
                error = next(iter(getattr(exc, "call_errors", ())), exc)
                if getattr(error, "status_code", None) or getattr(error, "kind", "") in {
                    "configuration", "invalid_request", "unsupported_parameter"
                }:
                    billed = 0
            record["outcome"] = type(exc).__name__
        finally:
            self.reserved -= cost
            self.units += billed
            record["cost"] = billed
            self.success |= ok

    def page(self, provider, url, text, method, date="", claim=None):
        if not isinstance(text, str) or not url:
            return
        self.pages.append({"url": url, "provider": provider, "text": text, "method": method,
                           "date": date, "claim": claim})
        self.evidence.add(provider, url, text, claim=claim, date=date, source=method)

    async def search(self, query, provider, deep=False):
        depth = "deep" if deep else "lite"
        cost = {"nimble": (15 if deep else 1), "tavily": (16 if deep else 8)}[provider]
        result = await self.call(provider, "search", query, cost, lambda: self.providers.router.search(
            query, provider=provider, search_depth=depth, max_results=10, timeout=42, data_apis=False))
        if result is None:
            return None
        for r in result.results:
            self.page(provider, r.url, r.content or r.description, "search", r.published_date or "")
            if deep:
                self.extracted.add(r.url)
        return [r.url for r in result.results if r.url.startswith(("http://", "https://"))]

    async def extract(self, url, provider):
        self.extracted.add(url)
        result = await self.call(provider, "extract", url, 1 if provider == "nimble" else 2,
                                  lambda: self.providers.router.extract(url, provider=provider, timeout=42, data_apis=False))
        if result:
            for doc in result.documents:
                self.page(provider, doc.url, doc.content, "extract")
        return bool(result)

    async def read_urls(self, urls, provider, limit):
        fresh = [url for url in dict.fromkeys(urls) if url not in self.extracted]
        fresh.sort(key=lambda url: not own(url, self.domain))
        if not fresh:
            return
        await asyncio.gather(*(self.extract(url, provider) for url in fresh[:limit]))

    async def research(self):
        schema = {"type": "object", "properties": {
            field: {"type": "integer" if field in ("founded_year", "funding_total") else "string",
                    "description": question} for field, question in QUESTIONS.items()}}
        query = (f"Research the company operating {self.domain}. Find its registered legal name, headquarters city, "
                 "current chief executive, founding year, total company employee count range and cumulative equity "
                 "funding in US dollars. Quote verbatim source sentences naming this company and stating each fact. "
                 "Prefer current official sources. Exclude partners' and customers' details.")
        job = await self.call("nimble", "research", query, 25, lambda: self.providers.router.submit_research(
            query, provider="nimble", output_schema=schema))
        if job is None:
            return []
        try:
            result = await job.aresult(timeout=min(140, self.deadline - asyncio.get_running_loop().time()))
        except Exception:
            return []
        structured = result.structured if isinstance(result.structured, dict) else {}
        urls = []
        for c in result.citations:
            if c.url:
                urls.append(c.url)
            field = (c.field or "").removeprefix("$.")
            self.page("nimble", c.url, c.snippet, "research", claim=[field, structured.get(field)])
        return urls

    async def gather(self):
        if not self.providers.available:
            return
        provider = self.providers.available[0]
        initial = await self.search(self.domain, provider, deep=provider == "tavily")
        if initial is None and len(self.providers.available) > 1:
            provider = "tavily"
            initial = await self.search(self.domain, provider, deep=True)
        initial = initial or []
        if not self.evidence.gaps():
            return
        await self.read_urls(initial, provider, 10)
        gaps = self.evidence.gaps()
        if not gaps:
            return
        queries = [self.search(f"{self.domain} {QUESTIONS[field]}", provider, deep=provider == "tavily") for field in gaps]
        if "nimble" in self.providers.available:
            queries.append(self.research())
        results = await asyncio.gather(*queries)
        if not self.evidence.gaps():
            return
        # Interleave ranks so every missing field gets a chance inside the allowance.
        found = [r or [] for r in results]
        urls = [row[i] for i in range(max(map(len, found), default=0)) for row in found if len(row) > i]
        common = [f"https://{self.domain}{path}" for path in ("/about", "/", "/company", "/terms", "/careers")]
        await self.read_urls(urls + common, provider, 40)

    async def run(self):
        try:
            async with asyncio.timeout_at(self.deadline):
                await self.gather()
        except Exception as exc:
            # Keep completed evidence if the provider returns an unexpected payload.
            print("Build interrupted:", type(exc).__name__, flush=True)
        return self.evidence.fields()
