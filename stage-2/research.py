"""Nimble discovery, spending ledger, and private source observations."""

import asyncio
import logging
import math
import os
import re
import time
from urllib.parse import urlsplit

from evidence import PHRASES, REDACTED, candidate_score, page_headers, public_url, select_fields, words


PROVIDER = "nimble"
BUDGET = 80
RENDER_COST = 3
SENSITIVE_KEYS = {
    "authorization", "apikey", "accesstoken", "password", "secret", "token",
    "nimbleapikey", "tavilyapikey", "cookie", "setcookie",
}
IDENTITY_EXCERPT = words(("total", "cumulative", "to date", "across rounds", "overall"))
FINANCING_EXCERPT = words(("debt", "loan", "credit facility", "series", "round"))


class Redactor:
    def __init__(self):
        secrets = {os.environ.get(name) for name in (
            "NIMBLE_API_KEY", "TAVILY_API_KEY", "KERNEL_API_KEY", "BROWSERBASE_API_KEY",
        )}
        secrets.discard(None)
        secrets.discard("")
        patterns = [
            re.escape(key) if len(key) >= 8 else rf"(?<![A-Za-z0-9]){re.escape(key)}(?![A-Za-z0-9])"
            for key in sorted(secrets, key=len, reverse=True)
        ]
        self.pattern = re.compile("|".join(patterns)) if patterns else None

    def clean(self, value):
        if isinstance(value, str):
            return self.pattern.sub(REDACTED, value) if self.pattern else value
        if isinstance(value, dict):
            return {
                self.clean(key): self.clean(item) for key, item in value.items()
                if re.sub(r"[^a-z]", "", key.lower()) not in SENSITIVE_KEYS
            }
        if isinstance(value, (list, tuple)):
            return [self.clean(item) for item in value]
        if value is None or isinstance(value, (int, bool)):
            return value
        return value if isinstance(value, float) and math.isfinite(value) else None


def is_live():
    origin = os.environ.get("NIMBLE_BASE_URL")
    return not origin or urlsplit(origin).hostname == "sdk.nimbleway.com"


class Build:
    def __init__(self, domain, record, observed):
        self.domain = domain
        self.record = record
        self.observed = observed
        self.redactor = Redactor()
        self.live = is_live()
        self.success = False
        self.client = None
        self.searches = set()
        self.extracted = set()
        self.started = time.monotonic()
        self.reserved = 0

    def can_call(self, cost):
        return (self.record["spent_units"] + self.reserved + cost <= BUDGET
                and (not self.live or self.seconds_left() >= 31)
                and self.observed())

    def seconds_left(self):
        return max(0, 292 - (time.monotonic() - self.started))

    def observe_page(self, url, text, title, metadata, call, complete, rendered=False):
        if not public_url(url) or not isinstance(text, str):
            return
        clean = self.redactor.clean(text)
        self.record["pages"].append({
            "url": self.redactor.clean(url), "text": clean, "title": self.redactor.clean(title),
            "metadata": self.redactor.clean(metadata), "headers": page_headers(clean),
            "provider": PROVIDER, "call": call, "complete": complete, "rendered": rendered,
        })

    async def run_call(self, op, arg, cost, invoke):
        for attempt in range(4):
            result, index = await self.attempt(op, arg, cost, invoke)
            if index is None or self.record["calls"][index]["response"] != "rate_limited":
                return result, index
            if attempt < 3:
                await asyncio.sleep(1.05)
        return result, index

    async def attempt(self, op, arg, cost, invoke):
        if not self.can_call(cost):
            return None, None
        index = len(self.record["calls"])
        self.record["calls"].append(None)
        self.reserved += cost
        result = None
        try:
            result = await invoke()
            response, charged = "answered", cost
        except Exception as error:
            response, charged = classify_error(error, op, cost)
        if response in ("answered", "empty"):
            self.success = True
        self.record["calls"][index] = {
            "provider": PROVIDER, "operation": op, "argument": self.redactor.clean(arg),
            "response": response, "spent_units": charged,
        }
        self.reserved -= cost
        self.record["spent_units"] += charged
        self.observed(charged)
        return result, index

    async def search(self, query):
        if query in self.searches or not self.can_call(1):
            return False
        result, index = await self.run_call("search", {"query": query, "depth": "lite"}, 1,
                                            lambda: self.client.search(query, self.seconds_left()))
        if index is None or self.record["calls"][index]["response"] != "answered":
            return False
        self.searches.add(query)
        for url, text, title, metadata, complete in search_pages(result, "lite"):
            self.observe_page(url, text, title, metadata, index, complete)
        return True

    async def extract(self, url):
        if url in self.extracted or not self.can_call(RENDER_COST):
            return
        self.extracted.add(url)
        result, index = await self.run_call("extract", {"url": url, "render": True}, RENDER_COST,
                                            lambda: self.client.extract(url, self.seconds_left()))
        if result is not None:
            for page_url, text, title, metadata in extract_pages(result, url):
                self.observe_page(page_url, text, title, metadata, index, True, rendered=True)

    async def investigate(self):
        domain = self.domain
        for _ in range(3):
            if await self.search(domain) or not self.can_call(1):
                break
            if self.record["calls"][-1]["response"] == "rate_limited":
                break
        await self.render_pages(page["url"] for page in self.record["pages"])

        fields = self.fields()
        queries = []
        if self.needs_legal(fields):
            queries.append(f"{domain} registered legal name legal entity name of record company registry")
        if self.needs_funding(fields):
            queries.append(
                f"{domain} total equity funding raised cumulative USD dollars all rounds to date"
            )
        if any(fields[field]["status"] == "unknown" for field in
               ("hq_city", "ceo", "founded_year", "headcount_range")):
            queries.append(
                f"{domain} company profile chief executive CEO headquarters founded employees workforce",
            )
        if domain not in self.searches and self.record["calls"][-1]["response"] != "rate_limited":
            queries.append(domain)
        await asyncio.gather(*(self.search(query) for query in queries))
        await self.render_pages(page["url"] for page in self.record["pages"])

        fields = self.fields()
        if self.can_call(25 + RENDER_COST) and any(item["status"] == "unknown" for item in fields.values()):
            await self.research()
            await self.render_pages(claim.get("url") for claim in self.record["claims"])
        return self.fields() if self.success else None

    def fields(self):
        return select_fields(self.domain, self.record["pages"], self.record["started_at"])

    def needs_legal(self, fields):
        return not any(self.source_score(candidate, "legal_name") >= 4
                       for candidate in fields["legal_name"]["candidates"])

    def needs_funding(self, fields):
        return not any(
            self.source_score(citation, "funding_total") >= 4
            and IDENTITY_EXCERPT.search(citation["excerpt"])
            and (not FINANCING_EXCERPT.search(citation["excerpt"]) or words(("equity",)).search(citation["excerpt"]))
            for citation in fields["funding_total"]["candidates"]
        )

    def source_score(self, citation, field):
        source = next((page for page in self.record["pages"]
                       if page["url"] == citation["url"] and page["rendered"]), citation)
        return candidate_score(self.domain, source, citation["excerpt"], field)

    async def render_pages(self, urls):
        pending = dict.fromkeys(url for url in urls if public_url(url) and url not in self.extracted)
        await asyncio.gather(*(self.extract(url) for url in pending))

    async def research(self):
        query = (
            f"Research the company identified by {self.domain}. Find its registered legal name, "
            "headquarters city, current CEO, founding year, employee range, and total cumulative "
            "equity funding raised in whole USD across rounds. Cite a complete, attributable "
            "sentence for every value. Use null for unsupported values."
        )
        schema = {
            "type": "object",
            "properties": {
                field: {"type": ["null", "integer" if field in ("funding_total", "founded_year") else "string"]}
                for field in PHRASES
            },
        }
        job, index = await self.run_call(
            "research", {"query": query, "fields": list(PHRASES)}, 25,
            lambda: self.client.start_research(query, schema, self.seconds_left()),
        )
        if job is None or not self.observed():
            return
        event = self.record["calls"][index]
        event["job_id"] = self.redactor.clean(job.job_id)
        result, _ = await self.run_call(
            "research_result", {"research_call": index}, 0,
            lambda: self.client.research_result(job, self.seconds_left()),
        )
        if result is None:
            return
        event["request_id"] = self.redactor.clean(result.request_id)
        event["answer"] = self.redactor.clean(result.structured)
        for claim in research_claims(result):
            self.record["claims"].append(self.redactor.clean(claim | {"provider": PROVIDER, "call": index}))


def gather(domain, record, observed):
    async def run():
        build = Build(domain, record, observed)
        if not os.environ.get("NIMBLE_API_KEY"):
            return None
        async with Provider(build.live) as client:
            build.client = client
            return await build.investigate()

    # Provider SDKs may log upstream bodies or credentials at debug level. The
    # opaque ledger records only classified failures and sanitized observations.
    logging.disable(logging.CRITICAL)
    return asyncio.run(run())


class Provider:
    def __init__(self, live):
        from web_router import AsyncWebRouter

        self.live = live
        self.router = AsyncWebRouter(
            PROVIDER, provider_config={PROVIDER: {"timeout": 45 if live else 3, "max_retries": 0}}
        )

    async def __aenter__(self):
        await self.router.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.router.__aexit__(*args)

    def timeout(self, seconds_left):
        return min(45 if self.live else 3, seconds_left)

    async def search(self, query, seconds_left):
        return await asyncio.wait_for(self.router.search(
            query, provider=PROVIDER, max_results=10, search_depth="lite",
            data_apis=False,
        ), timeout=self.timeout(seconds_left))

    async def extract(self, url, seconds_left):
        return await asyncio.wait_for(self.router.extract(
            url, provider=PROVIDER, format="markdown",
            data_apis=False, provider_options={"render": True},
        ), timeout=self.timeout(seconds_left))

    async def start_research(self, query, schema, seconds_left):
        return await asyncio.wait_for(self.router.submit_research(
            query, provider=PROVIDER, output_schema=schema, effort="low",
        ), timeout=self.timeout(seconds_left))

    async def research_result(self, job, seconds_left):
        return await job.aresult(timeout=min(120 if self.live else 4.5, seconds_left))


def classify_error(error, operation, cost):
    # Extract can wrap a refused HTTP call or a successful "no page" reply.
    # The nested call exception contains any provider HTTP status.
    if getattr(error, "call_errors", None):
        return classify_error(error.call_errors[0], operation, cost)
    if operation == "extract" and getattr(error, "url_failures", None):
        if getattr(error, "original", None) is None:
            return "empty", cost
        return classify_error(error.original, operation, cost)
    status = getattr(error, "status_code", None)
    if status == 429:
        return "rate_limited", 0
    if status is not None and status >= 400:
        return "refused", 0
    if getattr(error, "kind", None) == "local" or isinstance(error, (TypeError, ValueError, AttributeError)):
        return "local_error", 0
    return "unanswered", cost


def search_pages(result, depth):
    request_id = result.request_id
    raw = result.raw or {}
    # Use the original body, including whitespace and unused evidence. The
    # normalized search result can substitute a snippet for a missing body.
    if isinstance(raw.get("results"), list):
        for item in raw["results"]:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            body = item.get("content")
            metadata = {key: value for key, value in item.items() if key not in ("url", "title", "content")}
            metadata["request_id"] = request_id
            if isinstance(body, str) and body:
                yield item.get("url"), body, title, metadata, depth == "deep"
            else:
                snippet = item.get("description") or ""
                yield item.get("url"), snippet, title, metadata, False
        return
    for item in result.results:
        yield item.url, item.content, item.title, item.extra | {"request_id": request_id}, (
            depth == "deep" and bool(item.content) and item.content != item.description
        )


def extract_pages(result, requested_url):
    for item in result.documents:
        yield item.url or requested_url, item.content, item.title, item.extra | {
            "request_id": result.request_id, "status_code": item.status_code, "format": item.format,
        }


def research_claims(result):
    structured = result.structured if isinstance(result.structured, dict) else {}
    # Raw provenance retains every excerpt, including excerpts the normalized
    # Citation model omits when it presents one result per source and field.
    found = False
    for response in result.raw or []:
        output = response.get("output") or {}
        trust = output.get("trust") or {}
        for claim in trust.get("claims") or []:
            field = (claim.get("path") or "").removeprefix("$.")
            if field not in PHRASES:
                continue
            for citation in claim.get("citations") or []:
                for excerpt in citation.get("excerpts") or []:
                    if isinstance(excerpt, str):
                        found = True
                        yield {
                            "field": field, "value": structured.get(field), "url": citation.get("url", ""),
                            "excerpt": excerpt, "title": citation.get("title", ""),
                            "metadata": {
                                "request_id": result.request_id, "path": claim.get("path"),
                                "confidence": claim.get("confidence"), "reasoning": claim.get("reasoning"),
                                "source": {key: value for key, value in citation.items() if key != "excerpts"},
                            },
                        }
    if not found:
        for citation in result.citations:
            field = (citation.field or "").removeprefix("$.")
            if field in PHRASES:
                yield {"field": field, "value": structured.get(field), "url": citation.url,
                       "excerpt": citation.snippet, "title": citation.title,
                       "metadata": citation.extra | {"request_id": result.request_id, "path": citation.field}}
