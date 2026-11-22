"""Nimble-only discovery, provenance and per-build spending (R2, R14–R17, R19, R21)."""

import asyncio
import logging
import math
import os
import re
import threading
import time
import warnings
from datetime import date
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from candidates import Candidates, page_headers
from evidence import FIELDS
from lineage import Origins, url_key


BUDGET = 80
MAX_RESULTS = 10
SEARCH_COST = {"lite": 1, "fast": 5, "deep": 15}
RESEARCH_COST = 25
RENDER_COST = 3
RATE_LOCK = threading.Lock()
RETRY_AFTER = {}
SOURCE_FIELDS = {
    "legal_name": "registered legal name",
    "hq_city": "company headquarters location",
    "ceo": "CEO chief executive",
    "founded_year": "founding date",
    "headcount_range": "employees headcount",
    "funding_total": "total equity funding raised in US dollars",
}
SENSITIVE_NAMES = {
    "authorization", "proxyauthorization", "cookie", "setcookie", "key", "apikey",
    "session", "sessionid", "sessiontoken", "token", "authtoken", "accesstoken", "bearertoken",
    "refreshtoken", "idtoken", "password", "passwd", "secret", "clientsecret", "credential",
    "credentials", "signature", "sig", "accesskeyid", "apikeyid", "securitytoken",
    "providerkey", "privatekey", "secretkey", "authkey", "passwordhash",
}
URL_IN_TEXT = re.compile(r"""https?://[^\s<>"']+""", re.IGNORECASE)


def sensitive(name):
    name = re.sub(r"[^a-z0-9]", "", name.lower())
    return (name in SENSITIVE_NAMES or name.endswith(
        ("apikey", "authtoken", "accesstoken", "sessiontoken", "securitytoken", "password",
         "signature", "secret")
    ))


def safe_url(value):
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.hostname or any(char.isspace() for char in value):
        return ""

    def public_parameters(parameters):
        return "&".join(
            part for part in parameters.split("&")
            if not sensitive(unquote_plus(part.partition("=")[0]))
        )

    query = public_parameters(parts.query)
    fragment = public_parameters(parts.fragment) if "=" in parts.fragment else parts.fragment
    origin = parts.netloc.rsplit("@", 1)[-1]
    if (origin, query, fragment) == (parts.netloc, parts.query, parts.fragment):
        return value
    return urlunsplit((parts.scheme, origin, parts.path, query, fragment))


class Provenance:
    def __init__(self):
        keys = sorted(
            {key for name in ("NIMBLE_API_KEY", "TAVILY_API_KEY", "KERNEL_API_KEY", "BROWSERBASE_API_KEY")
             if (key := os.environ.get(name))},
            key=len, reverse=True,
        )
        self.credential_pattern = re.compile("|".join(map(re.escape, keys))) if keys else None
        # A separator absent from every key cannot form another match when inserted.
        separator = 0x2588
        while any(chr(separator) in key for key in keys):
            separator += 1
        self.redaction = chr(separator)

    def text(self, value):
        value = URL_IN_TEXT.sub(lambda match: safe_url(match[0]) or match[0], value)
        if self.credential_pattern is not None:
            value = self.credential_pattern.sub(self.redaction, value)
        return value

    def scrub(self, value):
        if isinstance(value, dict):
            return {self.text(key): self.scrub(item) for key, item in value.items()
                    if isinstance(key, str) and not sensitive(key)}
        if isinstance(value, (tuple, list)):
            return [self.scrub(item) for item in value]
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, date):
            return value.isoformat()
        return self.text(str(value))


def failure(exc, operation):
    """Recognize provider refusals separately from network failures and extract misses."""
    status = getattr(exc, "status_code", None)
    reported_missing = getattr(exc, "failures", None) and not getattr(exc, "call_errors", None)
    body = getattr(getattr(exc, "original", exc), "body", None)
    reported_missing = reported_missing or (
        isinstance(body, dict) and isinstance(body.get("url"), str)
        and body.get("status") in ("skipped", "fatal", "error", "rejected", "blocked")
        and not body.get("data")
    )
    if operation == "extract" and (status in (404, 410) or reported_missing):
        return "no_page", status
    if status is not None and status >= 400:
        return "refused", status
    if type(exc).__name__ in {
        "ConfigurationError", "ProviderNotFoundError", "ProviderNotInstalledError", "UnsupportedFormatError",
        "UnsupportedParameterError", "MissingParameterError", "BudgetExceededError", "ValidationError", "ValueError",
    }:
        return "unavailable", None
    return "no_answer", None


def research_schema():
    def field(kind):
        return {
            "type": "object",
            "properties": {
                "value": {"type": ["integer" if kind is int else "string", "null"]},
                "citation": {"type": ["object", "null"], "properties": {
                    "url": {"type": "string"}, "excerpt": {"type": "string"},
                }, "required": ["url", "excerpt"], "additionalProperties": False},
            },
            "required": ["value", "citation"], "additionalProperties": False,
        }
    return {
        "type": "object", "properties": {name: field(kind) for name, kind in FIELDS.items()},
        "required": list(FIELDS), "additionalProperties": False,
    }


class Build:
    def __init__(self, domain, current, observe, *, live):
        self.domain = domain
        self.current = current
        self.observe = observe
        self.live = live
        self.started = time.monotonic()
        self.finished_by = self.started + (290 if live else 9.6)
        self.spent = 0
        self.any_success = False
        self.provenance = Provenance()
        self.candidates = Candidates(domain, executives=True, independent=True)
        self.origins = Origins(domain)
        self.seeds = {}
        self.urls_seen = set()
        self.rate_waiters = 0
        self.wait_started = 0.0

    def remaining(self):
        now = time.monotonic()
        paused = now - self.wait_started if self.rate_waiters and not self.live else 0
        return self.finished_by - now + paused

    def allowed(self, cost):
        enough_time = self.remaining() >= (30 if self.live else 0.1)
        return self.spent + cost <= BUDGET and enough_time and self.current()

    def call_timeout(self):
        return min(self.remaining(), 38 if self.live else 2.3)

    async def pause_for_rate(self, delay):
        if self.live:
            await asyncio.sleep(min(delay, max(0, self.remaining())))
            return
        if not self.rate_waiters:
            self.wait_started = time.monotonic()
        self.rate_waiters += 1
        try:
            await asyncio.sleep(delay)
        finally:
            self.rate_waiters -= 1
            if not self.rate_waiters:
                self.finished_by += time.monotonic() - self.wait_started

    async def provider_call(self, operation, target, call, *, key, cost=0, timeout=None, **details):
        """Use one shared cooldown for identical Nimble operations across builds."""
        for attempt in range(4):
            while self.allowed(0):
                with RATE_LOCK:
                    delay = RETRY_AFTER.get(key, 0) - time.monotonic()
                    if delay <= 0:
                        RETRY_AFTER.pop(key, None)
                if delay <= 0:
                    break
                await self.pause_for_rate(delay)
            if not self.allowed(0):
                return None
            reserve = getattr(self.observe, "reserve", None)
            if reserve and cost:
                target_key = self.provenance.text(target) if operation == "extract" else target
                while self.allowed(cost):
                    claim = reserve(operation, target_key, cost, details)
                    if claim == "reserved":
                        break
                    if claim == "exhausted":
                        return None
                    await asyncio.sleep(0.015)
                else:
                    return None
            started = time.monotonic()
            try:
                limit = self.call_timeout() if timeout is None else min(timeout, self.remaining())
                async with asyncio.timeout(limit):
                    return await call()
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if (isinstance(status, int) and status >= 500 and attempt < 2
                        and (operation != "search" or target != self.domain)
                        and failure(exc, operation)[0] == "refused"):
                    self.record(operation, target, started, 0, "refused", http_status=status, **details)
                    await asyncio.sleep(0.12 * (attempt + 1))
                    continue
                if status != 429:
                    raise
                with RATE_LOCK:
                    now = time.monotonic()
                    for stale in [name for name, expiry in RETRY_AFTER.items() if expiry <= now]:
                        RETRY_AFTER.pop(stale, None)
                    RETRY_AFTER[key] = now + 1.01
                self.record(operation, target, started, 0, "refused", http_status=429, **details)
        return None

    def record(self, operation, target, started, units, outcome, **metadata):
        self.spent += units
        self.any_success |= outcome in ("answered", "no_page", "started")
        # Provider data is sanitized without rewriting this service's record schema
        # when an opaque key happens to match part of a field name or enum.
        pages = metadata.pop("pages", None)
        details = {key: self.provenance.scrub(item) for key, item in metadata.items()}
        if pages is not None:
            details["pages"] = [
                {key: self.provenance.scrub(item) if key != "provider" else item
                 for key, item in page.items()}
                for page in pages
            ]
        if operation in ("extract", "research_result"):
            target = self.provenance.text(target)
        self.observe({
            "operation": operation, "target": target, "provider": "nimble",
            "units": units, "outcome": outcome, "elapsed_seconds": time.monotonic() - started,
            **details,
        })

    def read(self, page):
        url = page["url"]
        if safe_url(url) == url and url and self.provenance.text(url) == url and self.current():
            self.candidates.add(page, text_is_safe=lambda text: self.provenance.text(text) == text)
            self.origins.add(url, page_headers(page["text"]))

    def evidence(self):
        return {
            field: [{**item, "origin": self.origins.resolve(item["url"])[0]} for item in items]
            for field, items in self.candidates.serialized().items()
        }

    def gaps(self):
        return self.candidates.gaps()

    async def search(self, router, query, depth):
        cost = SEARCH_COST[depth]
        if not self.allowed(cost):
            return None, "unavailable", None
        started = time.monotonic()
        try:
            response = await self.provider_call(
                "search", query,
                lambda: router.search(
                    query, provider="nimble", search_depth=depth, max_results=MAX_RESULTS, data_apis=False,
                ), key=("search", query, depth), cost=cost, depth=depth,
            )
        except Exception as exc:
            outcome, status = failure(exc, "search")
            retry_after = getattr(exc, "retry_after", None)
            self.record("search", query, started, cost if outcome == "no_answer" else 0, outcome,
                        depth=depth, http_status=status, retry_after_seconds=retry_after)
            return None, outcome, retry_after
        if response is None:
            return None, "unavailable", None
        raw = response.raw or {}
        raw_results = raw.get("results") or []
        pages = []
        for index, result in enumerate(response.results):
            item = raw_results[index] if index < len(raw_results) else {}
            pages.append({
                "url": result.url, "provider": "nimble", "title": result.title,
                "text": result.content, "description": result.description,
                "published_date": result.published_date, "score": result.score,
                "metadata": result.extra,
                "provider_metadata": {k: v for k, v in item.items()
                                      if k not in ("url", "title", "content", "description")},
                "full_text": bool(item.get("content")) and depth != "fast",
            })
        self.record("search", query, started, cost, "answered", depth=depth, request_id=response.request_id,
                    pages=pages, metadata={key: value for key, value in raw.items() if key != "results"})
        return pages, "answered", None

    async def extract(self, router, url):
        if not self.current():
            return []
        started = time.monotonic()
        try:
            response = await self.provider_call(
                "extract", url, lambda: router.extract(
                    url, provider="nimble", format="markdown", provider_options={"render": True}, data_apis=False,
                ), key=("render", url), cost=RENDER_COST, rendered=True,
            )
        except Exception as exc:
            outcome, status = failure(exc, "extract")
            units = RENDER_COST if outcome in ("no_answer", "no_page") else 0
            self.record("extract", url, started, units, outcome, http_status=status, rendered=True)
            return []
        if response is None:
            return []
        raw = response.raw or []
        pages = [{
            "url": document.url, "provider": "nimble", "title": document.title,
            "text": document.content, "format": document.format, "status_code": document.status_code,
            "published_date": document.published_date, "warnings": document.warnings, "metadata": document.extra,
        } for document in response.documents]
        metadata = [
            {key: value for key, value in item.items() if key != "data"}
            for item in raw
        ]
        self.record("extract", url, started, RENDER_COST, "answered" if pages else "no_page",
                    request_id=response.request_id, pages=pages, metadata=metadata, rendered=True)
        return pages

    async def read_urls(self, router, urls, *, canonical=False):
        planned = {}
        for url in urls:
            key = url_key(url)
            if key and safe_url(url) == url and self.provenance.text(url) == url:
                if not canonical:
                    self.seeds.setdefault(key, url)
                if key not in self.urls_seen:
                    planned.setdefault(key, url)
        fetches = list(planned.items())
        count = min(len(fetches), (BUDGET - self.spent) // RENDER_COST)
        if count and self.allowed(count * RENDER_COST):
            queued = fetches[:count]
            self.urls_seen.update(key for key, _ in queued)
            versions = await asyncio.gather(*(self.extract(router, url) for _, url in queued))
            for (requested, _), group in zip(queued, versions):
                for version in group:
                    served = url_key(version["url"])
                    self.urls_seen.add(served)
                    self.read(version)
                    if served in self.origins.pages:
                        self.origins.link_redirect(requested, served)
                        if not canonical:
                            self.seeds.setdefault(served, version["url"])

    async def gather_originals(self, router):
        for _ in range(3):
            needed = [original for url in self.seeds.values()
                      if (original := self.origins.resolve(url)[1])
                      and url_key(original) not in self.urls_seen]
            if not needed or not self.allowed(RENDER_COST):
                break
            await self.read_urls(router, needed, canonical=True)

    @staticmethod
    def claim_urls(answer):
        urls = [citation.url for citation in answer.citations]
        structured = answer.structured if isinstance(answer.structured, dict) else {}
        for field in FIELDS:
            claim = structured.get(field)
            if isinstance(claim, dict):
                nested = claim.get("citation")
                if isinstance(nested, dict):
                    urls.append(nested.get("url"))
                if isinstance(items := claim.get("citations"), list):
                    urls.extend(item.get("url") for item in items if isinstance(item, dict))
                urls.append(claim.get("url"))
        return [url for url in urls if isinstance(url, str)]

    async def research(self, router):
        if not self.allowed(RESEARCH_COST):
            return
        query = (
            f"Company dossier for {self.domain}. Find the registered legal name, headquarters city, "
            "chief executive, founding year, headcount range, and total equity funding in whole US dollars. "
            "For each value return a page URL and a verbatim sentence naming the company and supporting "
            "the reported value. Leave unsupported values null."
        )
        started = time.monotonic()
        try:
            job = await self.provider_call(
                "research", query, lambda: router.submit_research(query, provider="nimble",
                                                                 output_schema=research_schema()),
                key=("research", query), cost=RESEARCH_COST,
            )
        except Exception as exc:
            outcome, status = failure(exc, "research")
            self.record("research", query, started, RESEARCH_COST if outcome == "no_answer" else 0, outcome,
                        http_status=status)
            return
        if job is None:
            return
        self.record("research", query, started, RESEARCH_COST, "started", job_id=job.job_id)
        if not self.current():
            return
        started = time.monotonic()
        try:
            limit = min(self.remaining(), 105 if self.live else 2.8)
            if limit < (30 if self.live else 0.1):
                return
            answer = await self.provider_call(
                "research_result", job.job_id, lambda: job.aresult(timeout=limit),
                key=("research_result", job.job_id), timeout=limit,
            )
        except Exception as exc:
            outcome, status = failure(exc, "research")
            self.record("research_result", job.job_id, started, 0, outcome, http_status=status)
            return
        if answer is None:
            return
        self.record("research_result", job.job_id, started, 0, "answered",
                    request_id=answer.request_id, structured=answer.structured, answer=answer.answer,
                    citations=[citation.model_dump(mode="json") for citation in answer.citations],
                    metadata=answer.raw)
        await self.read_urls(router, self.claim_urls(answer))
        await self.gather_originals(router)

    async def search_exact(self, router):
        # Keep retries on the original query until one search succeeds; even an empty
        # successful result discharges the exact-domain search requirement. If the
        # provider never answers within the time and cost limits, leave the build failed.
        backoff = 0.15
        time_needed = 30 if self.live else 0.1
        while self.allowed(1):
            pages, outcome, retry_after = await self.search(router, self.domain, "lite")
            if pages is not None:
                return pages
            if outcome == "unavailable":
                break
            wait = backoff
            if isinstance(retry_after, (int, float)) and math.isfinite(retry_after):
                wait = max(wait, min(retry_after, 10 if self.live else 2))
            if self.remaining() < wait + time_needed:
                break
            await asyncio.sleep(wait)
            backoff = min(backoff * 2, 0.55)
        return None

    async def run(self, router):
        exact = await self.search_exact(router)
        if exact is None:
            return False, self.candidates.dates, self.evidence()
        await self.read_urls(router, (page["url"] for page in exact))
        await self.gather_originals(router)

        queries = []
        gaps = self.gaps()
        if gaps:
            queries.append(", ".join(SOURCE_FIELDS[field] for field in gaps))
        if len(exact) == MAX_RESULTS:
            # A full search response can conceal further sources even when every
            # field is covered. Use different query terms to surface competing pages.
            queries.extend((
                "registration filing registry legal entity registered company headquarters",
                "company profile leadership CFO COO CTO founding workforce equity funding investors",
            ))
        for terms in queries:
            if not self.allowed(1 + RENDER_COST):
                break
            pages, _, _ = await self.search(router, f"{self.domain} {terms}", "lite")
            if pages is not None:
                await self.read_urls(router, (page["url"] for page in pages))
                await self.gather_originals(router)

        if self.gaps() and self.any_success and self.allowed(RESEARCH_COST + RENDER_COST):
            await self.research(router)

        return self.any_success, self.candidates.dates, self.evidence()


async def gather_async(domain, current, observe):
    # Importing the SDK here keeps readiness and all non-build routes independent
    # of provider configuration and initialization.
    from web_router import AsyncWebRouter

    # Provider diagnostics can include response bodies or authenticated URLs.
    for logger_name in ("web_router", "nimble_python", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL + 1)
    warnings.filterwarnings("ignore", message="Pydantic serializer warnings:",
                            category=UserWarning, module=r"pydantic\..*")
    endpoint = os.environ.get("NIMBLE_BASE_URL", "")
    live = not endpoint or urlsplit(endpoint).hostname == "sdk.nimbleway.com"
    build = Build(domain, current, observe, live=live)
    config = {"nimble": {"max_retries": 0, "timeout": 38 if live else 2.3}}
    async with AsyncWebRouter("nimble", provider_config=config, router=None) as router:
        return await build.run(router)


def gather(domain, current, observe):
    # A cancelled DNS lookup may still have an OS resolver thread in flight.
    # Retire the build on its deadline without joining that worker.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(gather_async(domain, current, observe))
    finally:
        loop.close()
