"""Nimble-only discovery, provenance and per-build spending (R2, R14–R17, R19, R21)."""

import asyncio
import logging
import math
import os
import re
import time
import warnings
from datetime import date
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from evidence import Appendix, FIELDS, is_header, unknown_fields


BUDGET = 80
SEARCH_COST = {"lite": 1, "fast": 5, "deep": 15}
RESEARCH_COST = 25
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
        self.credentials = tuple(sorted(
            {key for name in ("NIMBLE_API_KEY", "TAVILY_API_KEY") if (key := os.environ.get(name))},
            key=len, reverse=True,
        ))

    def text(self, value):
        for key in self.credentials:
            if len(key) >= 4 or value == key:
                value = value.replace(key, "[redacted]")
        return URL_IN_TEXT.sub(lambda match: safe_url(match[0]) or match[0], value)

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
        self.appendix = Appendix(domain)
        self.provenance = Provenance()
        self.fields = unknown_fields()
        self.candidates = {field: {} for field in FIELDS}
        self.urls_seen = set()
        self.texts_read = set()

    def remaining(self):
        return self.finished_by - time.monotonic()

    def allowed(self, cost):
        enough_time = self.remaining() >= (30 if self.live else 0.1)
        return self.spent + cost <= BUDGET and enough_time and self.current()

    def call_timeout(self):
        return min(self.remaining(), 38 if self.live else 2.3)

    def record(self, operation, target, started, units, outcome, **metadata):
        self.spent += units
        self.any_success |= outcome in ("answered", "no_page", "started")
        self.observe(self.provenance.scrub({
            "operation": operation, "target": target, "provider": "nimble",
            "units": units, "outcome": outcome, "elapsed_seconds": time.monotonic() - started,
            **metadata,
        }))

    def add_citation(self, field, value, url, excerpt):
        citation = {"url": url, "provider": "nimble", "excerpt": excerpt}
        competing = self.candidates[field].setdefault(value, [])
        if citation not in competing:
            competing.append(citation)
        result = self.fields[field]
        if result["value"] is not None and result["value"] != value:
            return
        result["value"] = value
        result["status"] = "known"
        result["citations"] = competing

    def read(self, page):
        url, text = page["url"], page["text"]
        if not text or not safe_url(url) or self.provenance.text(url) != url or not self.current():
            return
        key = (url, text)
        if key in self.texts_read:
            return
        self.texts_read.add(key)
        for field, value, excerpt in self.appendix.excerpts(text):
            if self.provenance.text(excerpt) == excerpt:
                self.add_citation(field, value, url, excerpt)

    def gaps(self):
        return [field for field, result in self.fields.items() if result["value"] is None]

    async def search(self, router, query, depth):
        cost = SEARCH_COST[depth]
        if not self.allowed(cost):
            return None, "unavailable", None
        started = time.monotonic()
        try:
            # Bound the actual call. WebRouter's timeout also applies a latency-based
            # admission rule, which can skip fast local providers using live estimates.
            async with asyncio.timeout(self.call_timeout()):
                response = await router.search(
                    query, provider="nimble", search_depth=depth, max_results=10, data_apis=False,
                )
        except Exception as exc:
            outcome, status = failure(exc, "search")
            retry_after = getattr(exc, "retry_after", None)
            self.record("search", query, started, cost if outcome == "no_answer" else 0, outcome,
                        depth=depth, http_status=status, retry_after_seconds=retry_after)
            return None, outcome, retry_after
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
            async with asyncio.timeout(self.call_timeout()):
                response = await router.extract(url, provider="nimble", format="markdown", data_apis=False)
        except Exception as exc:
            outcome, status = failure(exc, "extract")
            self.record("extract", url, started, int(outcome in ("no_answer", "no_page")), outcome,
                        http_status=status)
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
        self.record("extract", url, started, 1, "answered" if pages else "no_page",
                    request_id=response.request_id, pages=pages, metadata=metadata)
        return pages

    async def read_results(self, router, pages, depth):
        fetches = []
        for page in pages:
            url = page["url"]
            if page["full_text"]:
                self.urls_seen.add(url)
            elif safe_url(url) == url and url not in self.urls_seen:
                fetches.append(url)
                self.urls_seen.add(url)

        count = min(len(fetches), BUDGET - self.spent)
        if count and self.allowed(count):
            versions = await asyncio.gather(*(self.extract(router, url) for url in fetches[:count]))
            for group in versions:
                for version in group:
                    self.read(version)
        # A deep search's fallback description can legitimately hold served prose. A
        # lite title/snippet does not identify which portion of the page it came from.
        for page in pages:
            if depth != "lite" or page["full_text"]:
                self.read(page)

    def read_claims(self, answer):
        if not isinstance(answer.structured, dict):
            return
        for field, kind in FIELDS.items():
            claim = answer.structured.get(field)
            value = claim.get("value") if isinstance(claim, dict) else claim
            if type(value) is not kind:
                continue
            citations = []
            if isinstance(claim, dict):
                nested = claim.get("citation")
                if isinstance(nested, dict):
                    citations.append((nested.get("url"), nested.get("excerpt")))
                more = claim.get("citations")
                if isinstance(more, list):
                    citations.extend((item.get("url"), item.get("excerpt"))
                                     for item in more if isinstance(item, dict))
                citations.append((claim.get("url"), claim.get("excerpt")))
            for citation in answer.citations:
                if citation.field in (field, f"$.{field}", f"/{field}", f"$.{field}.value", f"/{field}/value"):
                    citations.append((citation.url, citation.snippet))
                    more = citation.extra.get("excerpts") or []
                    if isinstance(more, list):
                        citations.extend((citation.url, quote) for quote in more)
            for url, original in citations:
                if not isinstance(url, str) or safe_url(url) != url or not isinstance(original, str):
                    continue
                excerpt = " ".join(original.split())
                if (1 <= len(excerpt) <= 500 and not is_header(excerpt)
                        and self.provenance.text(url) == url and self.provenance.text(excerpt) == excerpt
                        and self.appendix.claim_supports(excerpt, field, value)):
                    self.add_citation(field, value, url, excerpt)

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
            async with asyncio.timeout(self.call_timeout()):
                job = await router.submit_research(query, provider="nimble", output_schema=research_schema())
        except Exception as exc:
            outcome, status = failure(exc, "research")
            self.record("research", query, started, RESEARCH_COST if outcome == "no_answer" else 0, outcome,
                        http_status=status)
            return
        self.record("research", query, started, RESEARCH_COST, "started", job_id=job.job_id)
        if not self.current():
            return
        started = time.monotonic()
        try:
            limit = min(self.remaining(), 105 if self.live else 2.8)
            if limit < (30 if self.live else 0.1):
                return
            async with asyncio.timeout(limit):
                answer = await job.aresult(timeout=limit)
        except Exception as exc:
            outcome, status = failure(exc, "research")
            self.record("research_result", job.job_id, started, 0, outcome, http_status=status)
            return
        self.record("research_result", job.job_id, started, 0, "answered",
                    request_id=answer.request_id, structured=answer.structured, answer=answer.answer,
                    citations=[citation.model_dump(mode="json") for citation in answer.citations],
                    metadata=answer.raw)
        self.read_claims(answer)

    async def run(self, router):
        # Keep retries on the original query until one search succeeds; even an empty
        # successful result discharges the exact-domain search requirement.
        for attempt in range(5):
            pages, outcome, retry_after = await self.search(router, self.domain, "lite")
            if pages is not None:
                await self.read_results(router, pages, "lite")
                break
            if outcome == "unavailable" or not self.allowed(1):
                break
            if attempt < 4:
                backoff = min(0.15 * 2**attempt, 0.55)
                if isinstance(retry_after, (int, float)) and math.isfinite(retry_after):
                    backoff = max(backoff, min(retry_after, 10 if self.live else 2))
                time_needed = 30 if self.live else 0.1
                if self.remaining() < backoff + time_needed:
                    break
                await asyncio.sleep(backoff)

        if self.gaps() and self.allowed(15):
            terms = ", ".join(SOURCE_FIELDS[field] for field in self.gaps())
            pages, _, _ = await self.search(router, f"{self.domain} {terms}", "deep")
            if pages is not None:
                await self.read_results(router, pages, "deep")

        if self.gaps() and self.any_success and self.allowed(RESEARCH_COST):
            await self.research(router)

        candidates = {
            field: [{"value": value, "citations": citations} for value, citations in matches.items()]
            for field, matches in self.candidates.items()
        }
        return self.any_success, self.fields, candidates


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
