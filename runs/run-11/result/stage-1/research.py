"""A single event loop shares provider connections across background builds."""
import asyncio
import contextvars
import os
import time
from urllib.parse import urlsplit

import httpx
from nimble_python import AsyncNimble
from web_router import AsyncWebRouter

from evidence import Evidence, PHRASES

CALL = contextvars.ContextVar("provider_call", default=None)
TARGETS = {
    "legal_name": "legal name registered company registered as legal entity",
    "hq_city": "headquarters headquartered based in registered office",
    "ceo": "CEO chief executive officer leadership",
    "founded_year": "founded founding established incorporated year",
    "headcount_range": "employs employees workforce headcount staff people",
    "funding_total": "total equity funding raised investment dollars",
}


async def requested(request):
    call = CALL.get()
    if call is not None and request.method == "POST" and not call["sent"]:
        call["sent"] = True
        call["cost"] = call["units"]


async def responded(response):
    call = CALL.get()
    if call is not None and response.request.method == "POST":
        call["status"] = response.status_code
        absent_page = call["method"] == "extract" and response.status_code in (404, 410)
        call["accepted"] = response.is_success or absent_page
        if response.is_error and not absent_page:
            call["cost"] = 0


def create_router():
    if not os.getenv("NIMBLE_API_KEY"):
        return None
    transport = httpx.AsyncClient(timeout=60, event_hooks={"request": [requested], "response": [responded]},
                                  limits=httpx.Limits(max_connections=256, max_keepalive_connections=50))
    sdk = AsyncNimble(http_client=transport, max_retries=0, timeout=60)
    return AsyncWebRouter(provider="nimble", provider_config={"nimble": {"async_client": sdk}})


class Build:
    def __init__(self, domain, router, active, account):
        self.domain = domain
        self.router = router
        self.active = active
        self.account = account
        self.evidence = Evidence(domain)
        self.calls = []
        self.research_answer = None
        self.spent = 0
        self.reserved = 0
        self.success = False
        self.seen = set()
        self.owned_extracted = False
        self.deadline = time.monotonic() + 290

    async def call(self, method, argument, units, function):
        if (not self.active() or self.spent + self.reserved + units > 80
                or self.deadline - time.monotonic() < 30):
            return None
        self.reserved += units
        call = dict(method=method, argument=argument, units=units, cost=0, sent=False, status=None)
        self.calls.append(call)
        token = CALL.set(call)
        try:
            async with asyncio.timeout(self.deadline - time.monotonic()):
                result = await function()
            self.success = True
            return result
        except Exception as exc:
            # The transport records HTTP acceptance even for an empty extract, or when
            # a research run was accepted but collecting its result subsequently failed.
            call["error"] = type(exc).__name__
            if call.get("accepted"):
                self.success = True
            return None
        finally:
            CALL.reset(token)
            self.reserved -= units
            self.spent += call["cost"]
            self.account(call["cost"])

    async def search(self, query):
        answer = await self.call("search", query, 1, lambda: self.router.search(
            query, provider="nimble", max_results=10, search_depth="lite"))
        if answer is None:
            return []
        urls = []
        for row in answer.results:
            if row.url.startswith(("http://", "https://")):
                self.evidence.add("nimble", row.url, row.content or row.description, row.title, row.published_date)
                urls.append(row.url)
        return urls

    async def extract(self, url, confirmation=False):
        response = await self.call("extract", url, 1, lambda: self.router.extract(url, provider="nimble"))
        if response:
            for doc in response.documents:
                self.evidence.full_text[url] = doc.content
                self.evidence.full_text[doc.url] = doc.content
                if confirmation:
                    self.evidence.pages.append(dict(provider="nimble", url=doc.url, text=doc.content,
                                                    role="research citation source"))
                else:
                    self.evidence.add("nimble", doc.url, doc.content)
                if doc.content and self.owned(doc.url):
                    self.owned_extracted = True

    async def fetch_new(self, urls, reserve=0):
        unique = list(dict.fromkeys(url for url in urls if url not in self.seen))
        unique.sort(key=lambda url: not self.owned(url))
        chosen = unique[:max(0, 80 - reserve - self.spent - self.reserved)]
        self.seen.update(chosen)
        await asyncio.gather(*(self.extract(url) for url in chosen))

    def owned(self, url):
        host = (urlsplit(url).hostname or "").lower()
        return host == self.domain or host.endswith("." + self.domain)

    async def research(self):
        schema = {"type": "object", "properties": {
            f: {"type": "integer" if f in ("funding_total", "founded_year") else "string"}
            for f in PHRASES}}
        query = (f"Research the company operating {self.domain}. Report the registered legal name, headquarters city, "
                 "current CEO, founding year, company-wide employee range and total USD equity raised. "
                 "For each field quote a verbatim sentence naming the company and stating its value. "
                 "Prefer dated company sources. Exclude namesakes, clients, partners and investors.")
        job = await self.call("research", query, 25, lambda: self.router.submit_research(
            query, provider="nimble", output_schema=schema))
        if job is None:
            return
        try:
            result = await job.aresult(timeout=max(1, self.deadline - time.monotonic()))
        except Exception:
            return
        self.research_answer = {
            "structured": result.structured, "answer": result.answer,
            "citations": [{"url": c.url, "title": c.title, "field": c.field, "snippet": c.snippet}
                          for c in result.citations],
        }
        data = result.structured if isinstance(result.structured, dict) else {}
        confirmations = {
            c.url for c in result.citations
            if c.url.startswith(("https://", "http://")) and c.url not in self.seen
            and c.url not in self.evidence.full_text and data.get((c.field or "").removeprefix("$.")) is not None
        }
        await asyncio.gather(*(self.extract(url, confirmation=True) for url in sorted(confirmations)))
        for cite in result.citations:
            field = (cite.field or "").removeprefix("$.")
            claim = data.get(field)
            if field in PHRASES and claim is not None:
                if field in ("funding_total", "founded_year") and isinstance(claim, str) and claim.isdecimal():
                    claim = int(claim)
                self.evidence.add("nimble", cite.url, cite.snippet, cite.title, claim=(field, claim))

    async def run(self):
        if self.router is None:
            return
        urls = await self.search(self.domain)
        # Resolve the required domain search before scheduling other queries. A
        # transport failure is ambiguous: only an explicit refusal is safe to retry.
        for _ in range(3):
            if not self.calls or not self.active():
                break
            status = self.calls[-1]["status"]
            if status != 429 and (status is None or not 500 <= status < 600):
                break
            await asyncio.sleep(1)
            urls = await self.search(self.domain)
        missing = lambda: [f for f, options in self.evidence.candidates.items() if not options]
        if missing():
            await self.fetch_new(urls)
        fields = missing()
        if fields:
            groups = await asyncio.gather(*(self.search(self.domain + " " + TARGETS[field]) for field in fields))
            if missing():
                await self.fetch_new([url for group in groups for url in group], reserve=25 + len(PHRASES))
        if missing() and urls and not self.owned_extracted:
            await self.fetch_new([f"https://{self.domain}/{path}" for path in ("", "about", "company")], reserve=25 + len(PHRASES))
        if missing():
            await self.research()
