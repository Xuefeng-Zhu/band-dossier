"""A budget and an evidence collection belong to exactly one build."""
import asyncio
import os
from urllib.parse import urlsplit

from web_router import AsyncWebRouter
from web_router.exceptions import ProviderError
from web_router.exceptions_typed import ExtractFailedError
from web_router.types import ExtractRequest, ResearchRequest, SearchRequest

from evidence import Evidence, PHRASES

QUERIES = {
    "legal_name": 'legal name registered as legal entity terms of service',
    "hq_city": 'company headquartered in headquarters based in',
    "ceo": 'CEO chief executive officer leadership',
    "founded_year": 'company founded established incorporated history year',
    "headcount_range": 'total employees employs staff global headcount workforce',
    "funding_total": 'total equity funding raised to date cumulative dollars',
}
PROVIDERS = [p for p in ("nimble", "tavily") if os.environ.get(p.upper() + "_API_KEY")]
router = AsyncWebRouter("nimble", router=None, provider_config={
    "nimble": {"max_retries": 0, "timeout": 43},
    "tavily": {"api_base_url": os.getenv("TAVILY_BASE_URL"), "timeout": 43},
})


NO_PAGE = object()


class Build:
    def __init__(self, domain, timestamp):
        self.domain = domain
        self.timestamp = timestamp
        self.evidence = Evidence(domain)
        self.spent = 0
        self.reserved = 0
        self.succeeded = False
        self.calls = []
        self.sources = []
        self.urls = {}
        self.requested = set()
        self.target_hits = {}

    @property
    def missing(self):
        return [field for field in PHRASES if field not in self.evidence.ranks or self.evidence.ranks[field][0] < 2]

    async def call(self, method, provider, argument, cost, request):
        if self.spent + self.reserved + cost > 80:
            return None
        self.reserved += cost
        record = {"provider": provider, "method": method, "argument": argument, "units": cost}
        self.calls.append(record)
        try:
            async with asyncio.timeout(45):
                result = await request()
            self.succeeded = True
            return result
        except ExtractFailedError as error:
            if not error.call_errors:
                # The provider answered, even though the requested page was missing.
                self.succeeded = True
                return NO_PAGE
            elif error.status_code:
                record["units"] = 0
        except ProviderError as error:
            if error.status_code or error.kind in ("rate_limit", "bad_request", "auth"):
                record["units"] = 0
        except TimeoutError:
            pass
        finally:
            self.reserved -= cost
            self.spent += record["units"]
        return None

    def ingest(self, provider, url, text, date="", claim=None, snippet=False):
        self.sources.append({"provider": provider, "url": url, "text": text, "date": date, "claim": claim})
        self.evidence.add(provider, url, text, date=date, claim=claim, snippet=snippet)

    async def search(self, query, providers, field=None):
        for p in providers:
            request = SearchRequest(query=query, search_depth="lite", max_results=10)
            result = await self.call("search", p, query, 1 if p == "nimble" else 8,
                                     lambda: router.get_provider(p).asearch(request))
            if result is None:
                continue
            for hit in result.results:
                if hit.url:
                    self.urls.setdefault(hit.url, hit.title or "")
                    if field:
                        self.target_hits.setdefault(field, []).append(hit.url)
                    self.ingest(p, hit.url, hit.content or hit.description, str(hit.published_date or ""), snippet=True)
            return True
        return False

    async def extract(self, url):
        for p in PROVIDERS:
            request = ExtractRequest(urls=[url])
            result = await self.call("extract", p, url, 1 if p == "nimble" else 2,
                                     lambda: router.get_extract_provider(p).aextract(request))
            if result is NO_PAGE:
                return
            if result is not None:
                for doc in result.documents:
                    self.ingest(p, doc.url, doc.content)
                return

    def own(self, url):
        try:
            host = (urlsplit(url).hostname or "").lower()
            return host == self.domain or host.endswith("." + self.domain)
        except ValueError:
            return False

    async def extract_pages(self, urls, limit):
        selected = []
        for url in dict.fromkeys(urls):
            if url not in self.requested and url.startswith(("https://", "http://")):
                self.requested.add(url)
                selected.append(url)
                if len(selected) == limit:
                    break
        await asyncio.gather(*(self.extract(url) for url in selected))

    async def research(self):
        if "nimble" not in PROVIDERS:
            return
        properties = {k: {"type": ["integer" if k in ("founded_year", "funding_total") else "string", "null"],
                          "description": QUERIES[k]} for k in PHRASES}
        query = (f"Research the company at {self.domain}. Identify its current company-wide facts. "
                 "Cite the original source with a verbatim sentence naming this company for each fact. "
                 "For funding give cumulative equity raised across rounds in whole US dollars.")
        request = ResearchRequest(query=query, output_schema={"type": "object", "properties": properties})
        job = await self.call("research", "nimble", query, 25,
                              lambda: router.get_research_provider("nimble").asubmit(request))
        if job is None:
            return
        try:
            answer = await job.aresult(timeout=160)
        except (ProviderError, TimeoutError):
            return
        structured = answer.structured if isinstance(answer.structured, dict) else {}
        follow = []
        for citation in answer.citations:
            field = (citation.field or "").strip("$. /").split("/")[-1]
            if field in structured and citation.snippet:
                self.ingest("nimble", citation.url, citation.snippet, claim=(field, structured[field]))
            if citation.url and (not field or field in self.missing):
                follow.append(citation.url)
        if self.missing:
            await self.extract_pages(follow, 8)

    async def gather(self):
        if not PROVIDERS:
            return
        exact = await self.search(self.domain, PROVIDERS)
        if not exact:
            # A refused search does not claim the exact-domain query.
            await self.search(self.domain, PROVIDERS)
        if not self.missing:
            return
        hits = list(self.urls)
        own = [url for url in hits if self.own(url)]
        if not own:
            own = ["https://" + self.domain + "/"]
        await self.extract_pages(own, 6)
        if not self.missing:
            return
        await self.extract_pages(hits, 10)
        if not self.missing:
            return

        # Each targeted query names the subject. The expensive agent run is
        # needed only when the cheaper search and page evidence leaves gaps.
        await asyncio.gather(*(self.search(f"{self.domain} {QUERIES[f]}", PROVIDERS, f) for f in self.missing))
        if not self.missing:
            return
        paths = [f"https://{self.domain}/{path}" for path in ("about", "about-us", "company", "legal", "leadership")]
        # Targeted search results compete for the same extraction allowance.
        # Visit top-ranked hits across fields before deeper results for one field.
        targeted = [self.target_hits.get(f, []) for f in self.missing]
        prioritized = [urls[i] for i in range(10) for urls in targeted if i < len(urls)]
        ordered = list(dict.fromkeys(prioritized + sorted(self.urls, key=lambda url: not self.own(url))))
        limit = min(18, max(1, 54 - self.spent))
        await asyncio.gather(self.research(), self.extract_pages(ordered + paths, limit))
        if self.missing and "nimble" in PROVIDERS:
            brand = self.domain.split(".")[0].replace("-", " ")
            confirmation = {
                "legal_name": 'legal name company registered name legal entity identifier LEI',
                "hq_city": 'company profile headquartered in headquarters city',
                "ceo": 'current CEO chief executive leadership biography',
                "founded_year": 'company history was founded in year',
                "headcount_range": 'total employees worldwide full-time employees company headcount',
                "funding_total": 'total equity funding across all rounds raised to date',
            }
            await asyncio.gather(*(self.search(f'"{brand}" {self.domain} {confirmation[f]}', ["nimble"], f)
                                   for f in self.missing))
        if self.missing:
            follow = [url for f in self.missing for url in self.target_hits.get(f, [])[-10:]]
            await self.extract_pages(follow + paths + ordered, 12)
