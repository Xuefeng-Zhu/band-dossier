"""Gather and audit evidence through WebRouter, then choose supported values."""

import asyncio
from datetime import date
from itertools import zip_longest
import math
import os
from urllib.parse import parse_qsl, urlsplit

from web_router import AsyncWebRouter
from web_router.exceptions import ConfigurationError, ProviderNotInstalledError

from candidates import candidates_from_pages
from evidence import FIELDS, INTEGER_FIELDS


PROVIDER = "nimble"
LIMIT = 80
SCHEMA = {
    "type": "object",
    "properties": {
        field: {"type": ["integer" if field in INTEGER_FIELDS else "string", "null"]}
        for field in FIELDS
    },
    "required": list(FIELDS),
    "additionalProperties": False,
}


def secret_key(name):
    key = "".join(c for c in name.lower() if c.isalnum())
    return (key in {"account", "accountid", "accountemail", "auth", "cookie", "cookies", "setcookie",
                    "key", "secret", "signature", "token", "username", "sessionid", "userid", "clientid"}
            or any(word in key for word in ("authorization", "authentication", "apikey", "password", "credential",
                                            "accesstoken", "refreshtoken", "bearertoken", "clientsecret")))


def public_url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username is not None:
            return None
        if any(secret_key(key) for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
            return None
    except ValueError:
        return None
    return value


class Audit:
    def __init__(self, active, charge):
        self.active = active
        self.charge = charge
        self.pending = 0
        self.spent = 0
        self.calls = []
        self.pages = []
        self.research_answers = []
        self.keys = [key for name in ("NIMBLE_API_KEY", "TAVILY_API_KEY") if (key := os.getenv(name))]

    def safe(self, value):
        if isinstance(value, dict):
            return {key: self.safe(item) for key, item in value.items()
                    if isinstance(key, str) and not secret_key(key)
                    and not self.contains_key(key)}
        if isinstance(value, list):
            return [self.safe(item) for item in value]
        if isinstance(value, str) and self.contains_key(value):
            return None
        if isinstance(value, str) and value.startswith(("https://", "http://")) and not public_url(value):
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, date):
            return value.isoformat()
        return value if value is None or isinstance(value, (str, int, float)) else None

    def contains_key(self, text):
        return any(secret == text or (len(secret) >= 16 and secret in text) for secret in self.keys)

    async def call(self, kind, cost, request, operation):
        if not self.active() or self.spent + self.pending + cost > LIMIT:
            return None, None
        self.pending += cost
        try:
            for attempt in range(4):
                if not self.active():
                    return None, None
                result, call_id = await self.attempt(kind, cost, request, operation)
                if self.calls[call_id].get("status_code") != 429 or attempt == 3:
                    return result, call_id
                await asyncio.sleep(1.05)
        finally:
            self.pending -= cost

    async def attempt(self, kind, cost, request, operation):
        call_id = len(self.calls)
        call = {"provider": PROVIDER, "kind": kind, "request": self.safe(request)}
        self.calls.append(call)
        result = None
        units = cost
        try:
            result = await operation()
            call["outcome"] = "success"
        except asyncio.CancelledError:
            call["outcome"] = "cancelled"
            raise
        except (ConfigurationError, ProviderNotInstalledError):
            units = 0
            call["outcome"] = "unavailable"
        except Exception as error:
            units, outcome, status = failed_call(kind, cost, error)
            call.update(outcome=outcome, status_code=status, error_type=type(error).__name__)
        finally:
            self.spent += units
            call["spent_units"] = units
            self.charge(units)
        return result, call_id

    def page(self, call_id, url, title, text, metadata, scope):
        url = self.safe(public_url(url))
        if url is None:
            return
        original = self.safe(text)
        if not isinstance(original, str):
            return
        self.pages.append({
            "call_id": call_id, "provider": PROVIDER, "url": url, "title": self.safe(title),
            "text": original, "metadata": self.safe(metadata), "scope": scope,
        })

    def output(self):
        return {"calls": self.calls, "pages": self.pages, "research_answers": self.research_answers}


def failed_call(kind, cost, error):
    status = getattr(error, "status_code", None)
    originals = getattr(error, "call_errors", ())
    if originals:
        original = originals[0]
        request_status = getattr(original, "status_code", None)
        if request_status is not None:
            status = request_status
    if kind == "extract" and (status in {404, 410} or (not originals and getattr(error, "failures", None))):
        return cost, "no_page", status
    if status is not None:
        return 0, "refused", status
    job_id = getattr(error, "job_id", None)
    if kind == "research_result" and job_id:
        return 0, "timeout", None
    outcome = "timeout" if isinstance(error, TimeoutError) or getattr(error, "kind", None) == "timeout" else "no_answer"
    return cost, outcome, None


async def gather_search(router, audit, query, *, exact=False):
    async def search():
        return await router.search(query, provider=PROVIDER, search_depth="lite", max_results=10, data_apis=False)

    request = {"query": query, "depth": "lite"}
    result, call = await audit.call("search", 1, request, search)
    if exact and result is None and call is not None:
        refusal = audit.calls[call].get("status_code")
        if refusal is not None and refusal >= 500:
            result, call = await audit.call("search", 1, request, search)
    urls = []
    if result is not None:
        raw = (result.raw or {}).get("results") or []
        audit.calls[call]["request_id"] = audit.safe(result.request_id)
        for index, item in enumerate(result.results):
            original = raw[index] if index < len(raw) else item.model_dump(mode="json")
            text = original.get("content") or original.get("description") or item.content or item.description
            audit.page(call, item.url, item.title, text, original, "search_snippet")
            if url := audit.safe(public_url(item.url)):
                urls.append(url)
    return urls


def provider_claims(result):
    """Keep all excerpts, including those omitted by normalized citations."""
    seen = set()

    def record(field, url, title, excerpt):
        key = (field, url, excerpt)
        if key in seen:
            return
        seen.add(key)
        return {"field": field, "url": url, "title": title, "excerpt": excerpt}

    for payload in result.raw or []:
        output = payload.get("output") or {}
        trust = output.get("trust") or {}
        for claim in trust.get("claims") or []:
            for item in claim.get("citations") or []:
                for excerpt in item.get("excerpts") or []:
                    if isinstance(excerpt, str) and (found := record(
                            claim.get("path"), public_url(item.get("url")), item.get("title"), excerpt)):
                        yield found
    for citation in result.citations:
        if found := record(citation.field, public_url(citation.url), citation.title, citation.snippet):
            yield found


async def gather_research(router, audit, domain, timeout):
    query = (f"Research {domain} and report its legal name, headquarters city, current CEO, "
             "founding year, employee range and total equity funding raised in US dollars. "
             "Use the requested schema, with a verbatim supporting source excerpt for each field. "
             "Return null for unverified fields.")
    job, submit_id = await audit.call(
        "research_start", 25, {"query": query, "fields": list(FIELDS)},
        lambda: router.submit_research(query, provider=PROVIDER, output_schema=SCHEMA, effort="low"),
    )
    if job is None:
        return
    audit.calls[submit_id]["request_id"] = audit.safe(job.job_id)
    result, call = await audit.call(
        "research_result", 0, {"start_call_id": submit_id}, lambda: job.aresult(timeout=timeout),
    )
    if result is not None:
        audit.research_answers.append({
            "provider": PROVIDER, "call_id": call, "start_call_id": submit_id,
            "request_id": audit.safe(result.request_id),
            "outcome": result.outcome, "structured": audit.safe(result.structured),
            "claims": audit.safe(list(provider_claims(result))),
            "metadata": audit.safe(result.raw),
        })


async def gather_page(router, audit, url):
    result, call = await audit.call(
        "extract", 3, {"url": url, "render": True},
        lambda: router.extract(url, provider=PROVIDER, format="markdown", provider_options={"render": True},
                               data_apis=False),
    )
    if result is not None:
        audit.calls[call]["request_id"] = audit.safe(result.request_id)
        for item in result.documents:
            audit.page(call, item.url, item.title, item.content,
                       {"document": item.model_dump(mode="json"), "response": result.raw}, "rendered")


async def gather(domain, audit, retrieved_at):
    host = urlsplit(os.getenv("NIMBLE_BASE_URL") or "https://sdk.nimbleway.com").hostname
    live = host == "sdk.nimbleway.com"
    call_window, run_window = (40, 200) if live else (2.5, 3.5)
    queries = (
        domain,
        f"{domain} registered name headquarters CEO founded",
        f"{domain} employees workforce total equity funding raised investment",
    )
    try:
        async with asyncio.timeout(280 if live else 20):
            async with AsyncWebRouter(PROVIDER, provider_config={
                PROVIDER: {"timeout": call_window, "max_retries": 0}
            }) as router:
                *searches, _ = await asyncio.gather(
                    *(gather_search(router, audit, query, exact=query == domain)
                      for query in (*queries, f"{domain} headcount")),
                    gather_research(router, audit, domain, run_window),
                )
                cited = [claim["url"] for answer in audit.research_answers for claim in answer["claims"]
                         if claim["url"] and claim["field"]]
                # Each query contributes its first result before any lower-ranked
                # results. Research citations get priority under the same budget.
                searched = (url for row in zip_longest(*searches) for url in row if url)
                ordered = dict.fromkeys((*cited, *searched))
                remaining = list(ordered)
                while remaining and audit.spent + 3 <= LIMIT:
                    count = (LIMIT - audit.spent) // 3
                    await asyncio.gather(*(gather_page(router, audit, url) for url in remaining[:count]))
                    del remaining[:count]
    except TimeoutError:
        pass
    return candidates_from_pages(domain, audit.pages, retrieved_at, answers=audit.research_answers,
                                 include_executives=True)
