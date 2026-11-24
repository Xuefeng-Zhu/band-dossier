"""Bounded asynchronous research. Provider calls go through WebRouter only."""

import asyncio
import os
import re
import time
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from web_router import AsyncWebRouter, ProviderError

from evidence import PHRASES, STATEMENT, subject_patterns, claim_matches, empty_fields, page_text, sentences, values

QUERIES = {
    "legal_name": '"legal name" OR "registered name" OR "registered as" company registrant filing',
    "hq_city": "headquarters headquartered in head office registered seat city location",
    "ceo": "CEO chief executive officer leadership appointed",
    "founded_year": "founded founding established incorporated year history",
    "headcount_range": "employees workforce employs staff headcount people",
    "funding_total": "total equity funding raised investment dollars",
}
FOLLOW_UP = {
    "legal_name": 'corporate legal notice LEI entity registration "legal name" registered company',
    "hq_city": 'principal head office headquartered in city company profile',
    "ceo": 'current CEO chief executive officer company leadership biography',
    "founded_year": 'company history was founded in establishment original incorporation date',
    "headcount_range": 'total full-time employees worldwide employs current workforce annual report',
    "funding_total": 'total equity funding raised to date venture capital investment dollars',
}
WORKFORCE = re.compile(
    r"\b(?:employs|workforce of|headcount (?:of|was|is)|staff of)\s+"
    r"(?:(?:about|approximately|roughly|over|nearly|more than|around)\s+)?[0-9]"
    r"|[0-9][0-9,]*(?:\s*[-–]\s*[0-9,]+)?\s+"
    r"(?:(?:full[- ]time|worldwide|permanent|global|total|active)\s+)*(?:employees|people|staff)\b", re.I)
FOUNDATION = re.compile(r"\b(?:founded|founding|established)\b", re.I)


def specificity(field, excerpt, domain):
    # Appendix A determines admissibility. Prefer an explicit relationship when
    # several admissible statements use a field's vocabulary in different senses.
    if field == "funding_total":
        if re.search(r"\b(total|cumulatively|to date|overall|across|over .* rounds)\b", excerpt, re.I):
            return 2
        if re.search(r"\b(round|series [a-z]|tranche)\b", excerpt, re.I):
            return 0
    if field == "headcount_range":
        return 2 if WORKFORCE.search(excerpt) else 0
    if field == "hq_city":
        place = STATEMENT[field].search(excerpt)
        company = subject_patterns(domain)[0].search(excerpt)
        if place and company and place.end() < company.start():
            between = excerpt[place.end():company.start()]
            if "," in between and between.partition(",")[2].strip():
                return 0
    if field == "founded_year":
        return 2 if FOUNDATION.search(excerpt) else 1
    return 2


SCHEMA = {
    "type": "object",
    "properties": {
        name: {"type": ["integer" if name in ("founded_year", "funding_total") else "string", "null"]}
        for name in PHRASES
    },
    "required": list(PHRASES),
}


def make_router():
    config = {"nimble": {"max_retries": 0, "timeout": 55}}
    if endpoint := os.getenv("TAVILY_BASE_URL"):
        config["tavily"] = {"api_base_url": endpoint}
    router = AsyncWebRouter("nimble", provider_config=config)
    # Instantiate clients before the first build. This only constructs connection pools.
    for provider in ("nimble", "tavily"):
        if os.getenv(provider.upper() + "_API_KEY"):
            router.get_provider(provider)
            router.get_extract_provider(provider)
            if provider == "nimble":
                router.get_research_provider(provider)
    return router


def error_outcome(exc, method):
    """A refusal is free. A lost answer is billable. Empty extracts are answered calls."""
    original = getattr(exc, "original", None)
    if method == "extract" and isinstance(exc, ProviderError) and original is None:
        if "no URL could be extracted" in str(exc):
            return "empty"
    chain = exc
    seen = set()
    while chain is not None and id(chain) not in seen:
        seen.add(id(chain))
        if isinstance(chain, (TimeoutError, httpx.TransportError, ConnectionError)):
            return "unanswered"
        if type(chain).__name__ in {"APIConnectionError", "APITimeoutError", "TimeoutError"}:
            return "unanswered"
        if getattr(chain, "status_code", None) or isinstance(chain, httpx.HTTPStatusError):
            return "refused"
        chain = getattr(chain, "original", None) or chain.__cause__ or chain.__context__
    return "refused"


class Build:
    def __init__(self, domain, router):
        self.domain = domain
        self.started = time.monotonic()
        self.router = router
        self.providers = [p for p in ("nimble", "tavily") if os.getenv(p.upper() + "_API_KEY")]
        self.spent = 0
        self.reserved = 0
        self.succeeded = False
        self.calls = []
        self.pages = []
        self.claims = []
        self.candidates = {f: {} for f in PHRASES}
        self.strength = {}
        self.hints = {}
        self.linked_pages = set()
        self.organization_names = {}
        name = re.escape(domain.split(".")[0].replace("-", " "))
        self.organization_pattern = re.compile(
            r"(?<!\w)(?i:" + name + r") ((?:[A-Z][a-z]+ ){0,3}[A-Z][a-z]+),? "
            r"(?:Corporation|Company|Inc\.|Corp\.|LLC|Ltd|Limited)\b")
        self.fields = empty_fields()
        self.attempted = set()
        self.urls = {}
        self.full_pages = set()
        self.page_versions = set()

    @property
    def missing(self):
        return [f for f in PHRASES if self.strength.get(f, 0) < 2 or
                (f in self.hints and not claim_matches(f, self.hints[f], self.fields[f]["value"]))]

    @property
    def remaining(self):
        return 80 - self.spent - self.reserved

    async def call(self, provider, method, target, cost, operation):
        # All budget mutations run on one event loop with no intervening await.
        if cost > self.remaining or time.monotonic() - self.started > 250:
            return None
        self.reserved += cost
        outcome = "unanswered"
        try:
            result = await operation()
            outcome = "answered"
            return result
        except Exception as exc:
            outcome = error_outcome(exc, method)
            return None
        finally:
            self.reserved -= cost
            actual = 0 if outcome == "refused" else cost
            self.spent += actual
            self.succeeded |= outcome in {"answered", "empty"}
            self.calls.append({"provider": provider, "method": method, "target": target,
                               "outcome": outcome, "units": actual})

    def remember(self, url, provider, excerpt, supported, date=""):
        try:
            published = datetime.fromisoformat(date).date().toordinal()
        except (TypeError, ValueError, OverflowError):
            published = 0
        try:
            host = urlsplit(url).hostname or ""
        except ValueError:
            return
        own = host == self.domain or host.endswith("." + self.domain)
        citation = {"url": url, "excerpt": excerpt, "provider": provider}
        for field, value in supported.items():
            candidates = self.candidates[field]
            sources = candidates.setdefault(value, {})
            key = (host.removeprefix("www."), url, excerpt, provider)
            score = specificity(field, excerpt, self.domain)
            # A foreign company's own leadership page may describe a namesake.
            # Seek corroboration from the requested domain or a linked source.
            if field == "ceo" and not own and url not in self.linked_pages:
                if re.search(r"/(?:management|leadership|team)(?:[-/]|$)", urlsplit(url).path, re.I):
                    score = min(score, 1)
            rank = (score, own, published)
            if key not in sources or rank > sources[key][0]:
                sources[key] = (rank, citation)

            self.select(field)

    def select(self, field):
        candidates = self.candidates[field]
        if not candidates:
            return
        hint = self.hints.get(field)

        def priority(item):
            value, entries = item
            expected = str(self.hints.get("legal_name", "")).casefold()
            def same_entity(url):
                qualifiers = self.organization_names.get(url, ())
                return not expected or not qualifiers or any(part in expected for part in qualifiers)
            best = max((same_entity(k[1]), rank[0], rank[1] or k[1] in self.linked_pages, rank[2])
                       for k, (rank, _) in entries.items())
            hosts = {k[0] for k, (rank, _) in entries.items() if rank[0] == best[1]}
            return best[0], best[1], best[2], claim_matches(field, hint, value), best[3], len(hosts)

        winner, entries = max(candidates.items(), key=priority)
        ordered = sorted(entries.values(), key=lambda pair: pair[0], reverse=True)
        strength = ordered[0][0][0]
        cites = [cite for score, cite in ordered if score[0] == strength][:3]
        self.strength[field] = strength
        self.fields[field] = {"value": winner, "status": "known", "citations": cites}

    def page(self, url, provider, text, full, published=""):
        if not url or not isinstance(text, str) or not text:
            return
        version = (url, provider, text, full)
        if version in self.page_versions:
            return
        self.page_versions.add(version)
        self.pages.append({"url": url, "provider": provider, "text": text, "full": full})
        if full:
            self.full_pages.add(url)
        domain_link = r"(?<![a-z0-9.-])(?:www\.)?" + re.escape(self.domain) + r"(?![a-z0-9.-])"
        if re.search(domain_link, text, re.I):
            self.linked_pages.add(url)
        qualifiers = self.organization_pattern.findall(text)
        if qualifiers:
            self.organization_names.setdefault(url, set()).update(q.casefold() for q in qualifiers)
        header, prose = page_text(text)
        for excerpt in sentences(prose):
            if not full and not excerpt.rstrip('"”’)').endswith((".", "?", "!")):
                # A clipped sentence might omit a qualifier or another value.
                continue
            if supported := values(self.domain, excerpt):
                self.remember(url, provider, excerpt, supported, header.get("Published", published))

    async def search(self, provider, query, depth="lite", field=None):
        cost = {"nimble": {"lite": 1, "fast": 5, "deep": 15}, "tavily": {"lite": 8, "deep": 16}}[provider][depth]
        result = await self.call(provider, "search", query, cost, lambda: self.router.search(
            query, provider=provider, search_depth=depth, max_results=10))
        if result is None:
            return False
        for index, item in enumerate(result.results):
            # Preserve the provider ranking for each field-specific result set.
            scores = self.urls.setdefault(item.url, {})
            scores[field] = max(scores.get(field, 0), 10 - index)
            # Tavily's lite adapter can add a truncation mark. Its original snippet is verbatim.
            text = item.content
            if provider == "tavily" and depth == "lite":
                for raw in (result.raw or {}).get("results", []):
                    if raw.get("url") == item.url:
                        text = raw.get("content") or ""
                        break
            self.page(item.url, provider, text, depth == "deep", item.published_date)
        return True

    async def extract(self, provider, url):
        self.attempted.add((provider, url))
        result = await self.call(provider, "extract", url, 1 if provider == "nimble" else 2,
                                 lambda: self.router.extract(url, provider=provider))
        if result:
            for document in result.documents:
                self.page(document.url, provider, document.content, True, document.published_date)
            self.full_pages.add(url)

    async def extract_results(self, reserve=0, limit=80):
        for provider in self.providers:
            if not self.missing:
                return
            available = max(0, self.remaining - reserve)
            urls = [url for url in self.urls if url.startswith(("https://", "http://"))
                    and url not in self.full_pages and (provider, url) not in self.attempted]
            wanted = set(self.missing)
            urls.sort(key=lambda url: max((score for field, score in self.urls[url].items()
                                          if field in wanted), default=0), reverse=True)
            n = min(limit, available // (1 if provider == "nimble" else 2))
            await asyncio.gather(*(self.extract(provider, url) for url in urls[:n]))

    async def research(self):
        query = (f"Find company profile facts for {self.domain}. Provide each field with a verbatim sentence "
                 "from the cited source that names the company and states that fact. Use null when unknown.")
        job = await self.call("nimble", "research", query, 25, lambda: self.router.submit_research(
            query, provider="nimble", output_schema=SCHEMA))
        if job is None:
            return
        try:
            response = await job.aresult(timeout=165)
        except Exception:
            return
        structured = response.structured if isinstance(response.structured, dict) else {}
        # Unverified claims guide verification searches. Only prose that passes
        # Appendix A can enter the candidate set or supply a response citation.
        self.hints = {f: v for f, v in structured.items() if f in PHRASES and
                      type(v) in (int, float, str) and len(str(v)) <= 150}
        for f in self.hints:
            self.select(f)
        for citation in response.citations:
            field = (citation.field or "").removeprefix("$.")
            excerpt = " ".join((citation.snippet or "").split())
            claimed = structured.get(field)
            self.claims.append({"field": field, "value": claimed, "url": citation.url,
                                "excerpt": citation.snippet, "provider": "nimble"})
            if field not in PHRASES or claimed is None or not citation.url:
                continue
            value = values(self.domain, excerpt).get(field)
            if value is not None and claim_matches(field, claimed, value):
                self.remember(citation.url, "nimble", excerpt, {field: value})

    def confirmation_query(self, field):
        hint = self.hints.get(field)
        target = ""
        if hint is not None and field != "headcount_range":
            target = f' "{hint}"'
        elif field in {"ceo", "hq_city", "founded_year"}:
            target = f" site:{self.domain}"
        if field == "ceo" and target and hint:
            return f'{self.domain}{target} CEO of {self.domain.split(".")[0].replace("-", " ")}'
        return f"{self.domain}{target} {FOLLOW_UP[field]}"

    async def run(self):
        source = None
        for provider in self.providers:
            if await self.search(provider, self.domain, "lite" if provider == "nimble" else "deep"):
                source = provider
                break
        await self.extract_results(reserve=25, limit=6)
        if not self.missing:
            return
        if source:
            # Each unresolved field gets its own inexpensive search. Run independent searches together.
            if source == "nimble":
                await asyncio.gather(*(self.search(source, f"{self.domain} {QUERIES[f]}", field=f) for f in self.missing))
            else:
                terms = " ".join(QUERIES[f] for f in self.missing)
                await self.search(source, f"{self.domain} {terms}", "deep")
            if self.missing and "nimble" in self.providers:
                # Independent verification can run while relevant search results are fetched.
                await asyncio.gather(self.research(), self.extract_results(reserve=14, limit=14))
            else:
                await self.extract_results(reserve=10)
        elif self.missing and "nimble" in self.providers:
            await self.research()
        if not source:
            # A transient refusal may have prevented the required exact-domain search.
            for provider in self.providers:
                if await self.search(provider, self.domain):
                    source = provider
                    break
        if self.missing and source:
            if source == "nimble":
                await asyncio.gather(*(self.search(source, self.confirmation_query(f),
                                                   "fast" if f in {"ceo", "legal_name"} else "lite", field=f)
                                       for f in self.missing))
            await self.extract_results()
            if self.missing:
                terms = " ".join(QUERIES[f] for f in self.missing)
                # If extraction works, buy only newly discovered bodies. A deep search
                # also provides an independent route to bodies when extraction fails.
                depth = "deep" if self.urls.keys() - self.full_pages else "lite"
                await self.search(source, f"{self.domain} company profile {terms}", depth)
                if depth == "lite" and self.missing:
                    await self.extract_results()
