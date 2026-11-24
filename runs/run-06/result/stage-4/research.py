"""Budgeted WebRouter research. Each Build owns its receipts and evidence."""
import asyncio
import os
import re
import time
from urllib.parse import urlsplit

from web_router import AsyncWebRouter
from web_router import ExtractFailedError

from candidates import Candidates, host_of, visible_text
from evidence import FIELDS, TITLES, sentences
from lineage import url_key


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
        self.cooldowns = {}
        self.router = AsyncWebRouter(provider="nimble", provider_config=config)

    async def close(self):
        await self.router.aclose()


class Build:
    def __init__(self, domain, providers, timestamp, batch_id=None, shared_remaining=None, checkpoint=None):
        self.batch_id = batch_id
        self.shared_remaining = shared_remaining
        self.checkpoint = checkpoint
        self.domain = domain
        self.providers = providers
        self.book = Candidates(domain, timestamp)
        self.succeeded = False
        self.spent = 0
        self.reserved = 0
        self.record = {"calls": [], "pages": [], "research": []}
        self.pages = {}
        self.attempted = set()
        self.discovered = {}
        self.research_urls = set()
        self.task = None
        self.last_start = float("inf")
        self.timer = None
        self.wait_until = 0

    @property
    def fields(self):
        return self.book.fields()

    def available_units(self):
        own = 80 - self.spent - self.reserved
        return min(own, self.shared_remaining()) if self.shared_remaining else own

    async def cooldown(self, key):
        until = self.providers.cooldowns.get(key, 0)
        now = time.monotonic()
        if until > now:
            if self.timer and not self.providers.live:
                # Count the union of overlapping backoffs only once per build.
                extra = max(0, until - max(now, self.wait_until))
                self.timer.reschedule(self.timer.when() + extra)
                self.wait_until = max(until, self.wait_until)
            await asyncio.sleep(until - now)

    async def call(self, provider, operation, argument, price, invoke):
        key = provider, operation, argument
        for attempt in range(4):
            await self.cooldown(key)
            if time.monotonic() > self.last_start or price > self.available_units():
                return None
            self.reserved += price
            receipt = {"provider": provider, "operation": operation, "argument": argument, "units": price, "outcome": "in_flight"}
            self.record["calls"].append(receipt)
            if price and self.checkpoint:
                self.checkpoint()
            try:
                result = await invoke()
            except asyncio.CancelledError:
                receipt["outcome"] = "interrupted"
                raise
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                kind = getattr(exc, "kind", None)
                if code == 429 or kind == "rate_limit":
                    receipt.update(units=0, outcome="refused", http_status=429)
                    self.providers.cooldowns[key] = time.monotonic() + 1.03
                    continue
                empty = operation.startswith("extract") and (
                    (isinstance(exc, ExtractFailedError) and not exc.call_errors) or code == 404
                )
                if empty:
                    receipt["outcome"] = "no_page"
                    self.succeeded = True
                elif code or kind in ("auth", "bad_request", "server"):
                    receipt.update(units=0, outcome="refused")
                else:
                    receipt["outcome"] = "connection_error"
                if code:
                    receipt["http_status"] = code
                return None
            else:
                receipt["outcome"] = "answered"
                self.providers.cooldowns.pop(key, None)
                self.succeeded = True
                return result
            finally:
                self.reserved -= price
                self.spent += receipt["units"]
                if price and self.checkpoint:
                    self.checkpoint()
        return None

    def page(self, provider, url, content, requested, evidence):
        if not url or not isinstance(content, str):
            return
        text = visible_text(content)
        page = {"provider": provider, "url": url, "text": text, "rendered": True,
                "lineage_only": not evidence}
        self.record["pages"].append(page)
        self.book.page(provider, url, text, evidence)
        for address in (requested, url):
            self.pages[address] = page
            self.book.sources[address] = self.book.sources[url]

    async def search(self, provider, query):
        cost = 1 if provider == "nimble" else 8
        result = await self.call(provider, "search_lite", query, cost, lambda: self.providers.router.search(
            query, max_results=10, search_depth="lite", provider=provider, data_apis=False,
        ))
        if result is None:
            return None
        for i, item in enumerate(result.results):
            if not item.url:
                continue
            self.discovered.setdefault(item.url, []).append((i, item.title or "", item.description or "", provider))
        return [item.url for item in result.results if item.url]

    async def extract(self, url, evidence=True):
        if not url_key(url):
            return
        cached = self.pages.get(url)
        if cached and evidence and cached["lineage_only"]:
            self.book.page(cached["provider"], cached["url"], cached["text"])
            cached["lineage_only"] = False
        if cached or url in self.attempted or self.available_units() < 3:
            return
        self.attempted.add(url)
        result = await self.call("nimble", "extract_rendered", url, 3, lambda: self.providers.router.extract(
            url, provider="nimble", data_apis=False, provider_options={"render": True},
        ))
        if result:
            for doc in result.documents:
                self.page("nimble", doc.url or url, doc.content, url, evidence)

    async def originals(self):
        frontier = {url: 3 for url in self.book.meta}
        visited = {}
        while frontier:
            targets = {}
            for url, depth in frontier.items():
                if depth <= visited.get(url, 0):
                    continue
                visited[url] = depth
                source = self.book.sources.get(url)
                if source and not source.publisher and source.original:
                    target = source.original
                    targets[target] = max(depth - 1, targets.get(target, 0))
            if not targets:
                break
            await asyncio.gather(*(self.extract(url, evidence=url in self.discovered or url in self.research_urls)
                                   for url in sorted(targets)))
            frontier = targets
            # A fetched original can independently be search or research evidence.
            # Its own origin then gets the full three links, even if found at depth three.
            frontier.update({url: 3 for url in self.book.meta if visited.get(url, 0) < 3})

    def render_order(self, pending, capacity):
        # Search previews can guide what to render, but never supply candidates.
        # When links compete for budget, rotate toward fields without coverage.
        leads = {}
        for url in pending:
            host = host_of(url)
            own = host == self.domain or host.endswith("." + self.domain)
            registry = host.endswith((".gov", ".gov.uk")) or "registry" in host or "filing" in host
            hits = self.discovered.get(url, [])
            topics = set()
            for _, title, description, _ in hits:
                for sentence in sentences(title + "\n" + description):
                    topics.update(self.book.support.parse(sentence))
            path = urlsplit(url).path.lower()
            profile = bool(re.search(r"(?:about|legal|terms|privacy|company|leadership|team|funding|investor)", path))
            rank = min((i for i, *_ in hits), default=10)
            leads[url] = (topics, own or registry, profile, rank)

        coverage = {f: int(bool(self.book.by_field.get(f))) for f in (*FIELDS, *TITLES, "investors")}
        chosen = []
        while leads and len(chosen) < capacity:
            def priority(url):
                topics, authoritative, profile, rank = leads[url]
                gain = sum(1 / (1 + coverage[f]) for f in topics)
                return (url not in self.research_urls, -gain, not authoritative, not profile, rank, url)
            url = min(leads, key=priority)
            topics, *_ = leads.pop(url)
            for field in topics:
                coverage[field] += 1
            chosen.append(url)
        return chosen

    async def gather_urls(self, urls, reserve=0):
        requested = set(urls)
        promoted = [url for url in requested if url in self.pages and self.pages[url]["lineage_only"]]
        for url in promoted:
            await self.extract(url)
        if promoted:
            await self.originals()
        pending = {u for u in requested if url_key(u) and u not in self.attempted}
        while pending:
            capacity = max(0, self.available_units() - reserve) // 3
            if not capacity:
                return
            order = self.render_order(pending, capacity) if len(pending) > capacity else sorted(pending)
            # Resolve newly found lineage before the next group consumes the allowance.
            group = order[:5]
            await asyncio.gather(*(self.extract(url) for url in group))
            await self.originals()
            pending.difference_update(group)

    def read_research(self, result):
        self.record["research"].append(result.model_dump(mode="json", include={"structured", "raw", "citations"}))
        # Research quotes can include material behind a disclosure control.
        # Use the links for discovery; only a page read can supply candidates.
        self.research_urls.update(citation.url for citation in result.citations if citation.url)
        if isinstance(result.structured, dict):
            for field in FIELDS:
                claim = result.structured.get(field)
                if not isinstance(claim, dict):
                    continue
                citations = claim.get("citations", [])
                for item in [claim, claim.get("citation"), *(citations if isinstance(citations, list) else [])]:
                    if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"]:
                        self.research_urls.add(item["url"])

    async def research(self):
        query = (f"Research the company operating {self.domain}. Identify the registered legal company name (look at "
                 "terms of service, privacy policies and regulatory filings), headquarters city, current CEO, "
                 "founding year, employee range, and cumulative equity funding in US dollars. Exclude similarly "
                 "named organizations and individual financing rounds. Cite a first-party source where possible. "
                 "For each value, return the source URL and one exact sentence explicitly naming the company and fact. "
                 "Use null for unsupported values.")
        job = await self.call("nimble", "research", query, 25, lambda: self.providers.router.submit_research(
            query, provider="nimble", output_schema=SCHEMA, effort="low",
        ))
        if job is None:
            return
        while not job.progress.is_terminal:
            progress = await self.call("nimble", "research_status", job.job_id, 0, job.astatus)
            if progress is None:
                # A lost poll or collection is free; replay the same handle once.
                progress = await self.call("nimble", "research_status", job.job_id, 0, job.astatus)
                if progress is None:
                    return
            if not job.progress.is_terminal:
                await asyncio.sleep(0.12 if not self.providers.live else 1)
        if job.progress.response:
            self.read_research(job.progress.response)

    async def exact_search(self):
        until = time.monotonic() + (20 if self.providers.live else 2.4)
        delay = 0.025
        while True:
            for provider in self.providers.available:
                hits = await self.search(provider, self.domain)
                if hits is not None:
                    return
            if time.monotonic() + delay >= until or self.available_units() < 1:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 0.3 if not self.providers.live else 2)

    async def discover(self):
        queries = {
            "legal_name": f'{self.domain} registered legal name legal entity terms of service legal notice registry',
            "hq_city": f'{self.domain} headquarters city head office',
            "ceo": f'{self.domain} current CEO chief executive leadership founders',
            "executives": f'{self.domain} management team CFO COO CTO chief financial operating technology officers',
            "founded_year": f'{self.domain} founded year corporate history established',
            "headcount_range": f'{self.domain} employees workforce headcount company team',
            "funding_total": f'{self.domain} cumulative total equity funding raised investors venture capital to date',
        }
        await asyncio.gather(*(self.search("nimble", q) for q in queries.values()))

    async def gather(self):
        available = self.providers.available
        if "nimble" not in available:
            return
        await self.exact_search()
        if self.batch_id and self.available_units() < 35:
            await self.gather_urls(self.discovered)
            if self.available_units() >= 4:
                more = await self.search("nimble", f"{self.domain} company profile executives investors funding")
                await self.gather_urls(more or [])
            return
        # Research and discovery can have very different latencies. Keep room for
        # the research citations before spending the remaining units on other pages.
        async with asyncio.TaskGroup() as group:
            group.create_task(self.research())
            discovery = group.create_task(self.discover())
            if "tavily" in available:
                group.create_task(self.search("tavily", f"{self.domain} company profile funding headquarters leadership"))
            await discovery
            await self.gather_urls(self.discovered, reserve=18)
        await self.gather_urls(self.research_urls | self.discovered.keys())
        if self.available_units() >= 4 and any(not self.book.by_field[f] for f in FIELDS):
            missing = " ".join(TOPICS[f] for f in FIELDS if not self.book.by_field[f])
            urls = await self.search("nimble", f"site:{self.domain} company about legal {missing}")
            await self.gather_urls(urls or [])

    async def run(self):
        if self.providers.live:
            self.last_start = time.monotonic() + 260
        try:
            async with asyncio.timeout(294 if self.providers.live else 9.4) as self.timer:
                await self.gather()
        except TimeoutError:
            self.record["deadline"] = True
