"""Per-build discovery, evidence selection, and atomic budget reservations."""
import asyncio
import os
import re
from urllib.parse import urlsplit

from web_router import AsyncWebRouter
from web_router.exceptions_typed import ExtractFailedError

from evidence import PHRASES, prose, supported, unknown_fields


SEARCH_TERMS = {
    "legal_name": "registered legal entity name incorporated",
    "hq_city": "headquarters headquartered in location city",
    "ceo": "leadership CEO chief executive officer",
    "founded_year": "company founded founding year history",
    "headcount_range": "workforce number of employees global headcount",
    "funding_total": "total equity funding raised to date",
}
SCHEMA = {"type": "object", "properties": {
    field: {"type": ["integer" if field in ("founded_year", "funding_total") else "string", "null"],
            "description": SEARCH_TERMS[field]} for field in PHRASES
}}


class Providers:
    def __init__(self):
        self.order = [name for name in ("nimble", "tavily") if os.getenv(name.upper() + "_API_KEY")]
        config = {"nimble": {"timeout": 45, "max_retries": 0}}
        if os.getenv("TAVILY_BASE_URL"):
            config["tavily"] = {"api_base_url": os.environ["TAVILY_BASE_URL"]}
        self.router = AsyncWebRouter("nimble", provider_config=config, router=None)


def own_page(domain, url):
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host == domain or host.endswith("." + domain)


class Build:
    def __init__(self, domain, providers):
        self.domain = domain
        self.providers = providers
        self.calls = []
        self.sources = []
        self.spent = 0
        self.reserved = 0
        self.succeeded = False
        self.candidates = {field: [] for field in PHRASES}
        self.full = set()
        self.tried = set()
        self.links = {}

    def missing(self):
        return [f for f, candidates in self.candidates.items() if not candidates]

    def fields(self):
        fields = unknown_fields()
        for f, choices in self.candidates.items():
            if choices:
                _, value, cite = max(choices, key=lambda c: c[0])
                fields[f] = {"value": value, "status": "known", "citations": [cite]}
        return fields

    def source(self, provider, url, text, kind, title="", date="", claim=None):
        if not (url and isinstance(text, str) and text):
            return
        self.sources.append({"provider": provider, "url": url, "text": text, "kind": kind,
                             "title": title, "date": date, "claim": claim})
        if kind == "page":
            self.full.add(url)
        # Search snippets and research excerpts already contain selected prose.
        lines, headers = prose(text) if kind == "page" else (text.splitlines(), [])
        metadata = dict(line.split(": ", 1) for line in headers if ": " in line)
        dated = str(metadata.get("Published", date) or "")[:10]
        own = own_page(self.domain, url)
        for field, value, excerpt in supported(self.domain, lines):
            if kind == "snippet" and text.rstrip().endswith(excerpt) and not re.search(r"""[.!?]["”’)]*$""", excerpt):
                continue
            if claim is not None and (claim[0] != field or claim[1] != value):
                continue
            # Prefer clear whole-company statements when a sentence also mentions another party or a round.
            weak = bool(re.search(r"(?i)\b(?:quoted|according to|client|customer|subsidiary|division)\b", excerpt))
            if field == "funding_total" and re.search(r"(?i)\b(?:series [a-z]|valuation|tender offer)\b", excerpt):
                weak = True
            rank = (not weak, dated if re.fullmatch(r"\d{4}-\d\d-\d\d", dated) else "",
                    own, kind == "page", -len(excerpt))
            self.candidates[field].append((rank, value, {"provider": provider, "url": url, "excerpt": excerpt}))

    async def call(self, provider, method, target, cost, send):
        if self.spent + self.reserved + cost > 80:
            return None
        self.reserved += cost
        entry = {"provider": provider, "method": method, "target": target, "units": cost, "outcome": "sent"}
        self.calls.append(entry)
        try:
            response = await send()
            self.succeeded = True
            entry["outcome"] = "answered"
            return response
        except asyncio.CancelledError:
            entry["outcome"] = "interrupted"
            raise
        except Exception as err:
            status = getattr(err, "status_code", None)
            kind = getattr(err, "kind", "")
            # A refusal is free. A response reporting an extraction failure paid for the requested URL.
            missing_page = method == "extract" and isinstance(err, ExtractFailedError) and not err.call_errors
            if missing_page:
                self.succeeded = True
                entry["outcome"] = "no_page"
            elif status is not None and status >= 400 or kind in ("auth", "rate_limit", "bad_request", "server_error"):
                entry.update(units=0, outcome="refused", status=status)
            else:
                entry["outcome"] = "no_answer"
            return None
        finally:
            self.spent += entry["units"]
            self.reserved -= cost

    async def search(self, query, provider):
        depth = "lite" if provider == "nimble" else "deep"
        router = self.providers.router
        result = await self.call(provider, "search", query, 1 if provider == "nimble" else 16,
                                 lambda: router.search(query, provider=provider, search_depth=depth,
                                                       max_results=10, data_apis=False, timeout=48))
        if result is None:
            return False
        for page in result.results:
            if not page.url:
                continue
            self.links.setdefault(page.url, (page.title, page.published_date))
            self.source(provider, page.url, page.content or page.description, "page" if depth == "deep" else "snippet",
                        page.title, page.published_date)
        return True

    async def extracts(self, urls, provider="nimble", leave=0):
        cost = 1 if provider == "nimble" else 2
        todo = [u for u in dict.fromkeys(urls) if u not in self.full and (provider, u) not in self.tried]
        todo.sort(key=lambda u: not own_page(self.domain, u))
        available = max(0, (80 - self.spent - self.reserved - leave)//cost)
        async def fetch(url):
            self.tried.add((provider, url))
            result = await self.call(provider, "extract", url, cost, lambda: self.providers.router.extract(
                url, provider=provider, format="markdown", data_apis=False, timeout=48))
            if result:
                for doc in result.documents:
                    title, date = self.links.get(url, ("", ""))
                    self.source(provider, doc.url, doc.content, "page", title, date)
        await asyncio.gather(*(fetch(url) for url in todo[:available]))

    async def research(self):
        query = (f"Find the registered company operating {self.domain}, its headquarters city, current CEO, "
                 "founding year, worldwide headcount range and total equity funding in USD. Cite verbatim "
                 "sentences that name the subject and state each fact. Distinguish namesakes, customers and "
                 "individual financing rounds. Use null when unsupported.")
        job = await self.call("nimble", "research", query, 25, lambda: self.providers.router.submit_research(
            query, provider="nimble", output_schema=SCHEMA))
        if not job:
            return
        try:
            result = await job.aresult(timeout=165)
        except Exception:
            return
        claims = result.structured or {}
        if not isinstance(claims, dict):
            return
        for cite in result.citations:
            field = (cite.field or "").removeprefix("$.")
            if cite.url:
                self.links.setdefault(cite.url, (cite.title, ""))
            if field in PHRASES:
                for excerpt in (cite.extra.get("excerpts") or [cite.snippet]):
                    self.source("nimble", cite.url, excerpt, "research", cite.title, claim=[field, claims.get(field)])

    async def gather(self):
        order = self.providers.order
        provider = None
        if not order:
            return
        # Finish exact-domain discovery before the extraction stage so a recovered
        # search takes the same full-text path as a successful first attempt.
        for attempt in range(2):
            if attempt and any(c.get("status") == 429 for c in self.calls):
                await asyncio.sleep(1.05)
            for backend in order:
                if await self.search(self.domain, backend):
                    provider = backend
                    break
            if provider:
                break
        if provider == "nimble":
            await self.extracts(self.links)
        if not self.missing():
            return
        if "nimble" in order:
            # Explore missing fields concurrently and deduplicate all returned pages before fetching.
            missing = self.missing()
            async with asyncio.TaskGroup() as group:
                group.create_task(self.research())
                for field in missing:
                    group.create_task(self.search(self.domain + " " + SEARCH_TERMS[field], "nimble"))
            await self.extracts(self.links)
            if self.missing() and provider is not None:
                paths = ("/", "/about", "/company", "/about-us", "/leadership", "/legal")
                await self.extracts(["https://" + self.domain + p for p in paths])
        if self.missing() and "tavily" in order and provider != "tavily":
            query = self.domain + " " + " ".join(SEARCH_TERMS[f] for f in self.missing())
            await self.search(query, "tavily")
