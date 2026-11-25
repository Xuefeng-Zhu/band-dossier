"""WebRouter research pipeline. Reservations precede every concurrent billable operation."""
import asyncio
import json
import os
import re
from itertools import zip_longest

from web_router import AsyncWebRouter
from web_router.exceptions_typed import ExtractFailedError

from evidence import Evidence
from state import FIELDS, uid


PROMPTS = {
    "legal_name": "legal name registered as legal entity terms of service",
    "hq_city": "headquartered in headquarters location head office city",
    "ceo": "who is the current chief executive officer CEO leadership founder press kit",
    "founded_year": "was founded in established company history",
    "headcount_range": "current worldwide workforce employs total number of employees latest annual report 10-K company headcount",
    "funding_total": "has raised a total of equity funding to date in billion or million dollars",
}
SEARCH_COST = {"nimble": {"lite": 1, "fast": 5, "deep": 15}, "tavily": {"lite": 8, "fast": 16, "deep": 16}}
CALL_TIMEOUT = 45


def make_router():
    config = {"nimble": {"timeout": CALL_TIMEOUT, "max_retries": 0}}
    if os.environ.get("TAVILY_API_KEY"):
        config["tavily"] = {"timeout": CALL_TIMEOUT}
        if url := os.environ.get("TAVILY_BASE_URL"):
            config["tavily"]["api_base_url"] = url
    return AsyncWebRouter("nimble", provider_config=config, router=None)


def claim_schema():
    fields = {}
    for key in FIELDS:
        kind = "integer" if key in ("founded_year", "funding_total") else "string"
        fields[key] = {
            "type": "object", "description": PROMPTS[key],
            "properties": {
                "value": {"type": [kind, "null"]},
                "url": {"type": "string", "description": "Page URL of the excerpt"},
                "excerpt": {"type": "string", "description": "One verbatim source sentence naming the company and stating the value"},
            }, "required": ["value", "url", "excerpt"],
        }
    return {"type": "object", "properties": fields, "required": list(FIELDS)}


def error_outcome(exc, operation):
    # WebRouter reports a successful extract with zero documents as ExtractFailedError, including
    # the target page's error status. An outer HTTP refusal is instead the individual call's error.
    if isinstance(exc, ExtractFailedError) and not exc.call_errors:
        return "no_page"
    status = getattr(exc, "status_code", None)
    if operation == "extract" and status in (404, 410):
        return "no_page"
    if status:
        return "refused"
    if getattr(exc, "kind", "") in ("auth", "bad_request", "rate_limit", "server_error"):
        return "refused"
    cause = exc
    while cause:
        name = type(cause).__name__.lower()
        if any(word in name for word in ("timeout", "deadline", "connection", "transport", "network", "remoteprotocol")):
            return "unanswered"
        cause = getattr(cause, "original", None) or cause.__cause__
    return "refused"


class Research:
    def __init__(self, domain, router, build):
        self.domain = domain
        self.router = router
        self.build = build
        self.proof = Evidence(domain, int(build.started[:4]))
        self.record = {"id": uid("b_"), "started": build.started, "calls": [], "pages": [], "research": []}
        self.succeeded = False
        self.reserved = 0
        self.full = set()
        self.extracted = set()
        self.dates = {}
        self.leads = {}
        self.nimble = bool(os.environ.get("NIMBLE_API_KEY"))
        self.tavily = bool(os.environ.get("TAVILY_API_KEY"))

    @property
    def remaining(self):
        return 80 - self.build.spent - self.reserved

    def record_issue(self, name):
        self.record.setdefault("issues", []).append(name)

    def fields(self):
        return self.proof.fields()

    async def call(self, provider, operation, price, info, invoke):
        if price > self.remaining or asyncio.get_running_loop().time() > self.deadline - 31:
            return None
        self.reserved += price
        row = {"provider": provider, "operation": operation, **info}
        self.record["calls"].append(row)
        outcome = "unanswered"
        try:
            async with asyncio.timeout(CALL_TIMEOUT + 1):
                result = await invoke()
            outcome = "ok"
            return result
        except Exception as exc:
            outcome = error_outcome(exc, operation)
            row["error"] = type(exc).__name__
            return None
        finally:
            self.reserved -= price
            units = 0 if outcome == "refused" else price
            self.build.spent += units
            self.succeeded |= outcome in ("ok", "no_page")
            row.update(outcome=outcome, units=units)

    def page(self, provider, url, title, text, published, source):
        if not url or not isinstance(text, str):
            return
        date = published if isinstance(published, str) else self.dates.get(url)
        if date:
            self.dates[url] = date
        self.record["pages"].append({"url": url, "provider": provider, "title": title, "text": text,
                                     "published": date, "source": source})
        self.proof.observe(url, provider, text, date)

    async def search(self, provider, query, depth="lite"):
        price = SEARCH_COST[provider][depth]
        result = await self.call(provider, "search", price, {"query": query, "depth": depth},
                                 lambda: self.router.search(query, provider=provider, search_depth=depth,
                                                            max_results=10, data_apis=False, timeout=CALL_TIMEOUT))
        if result is None:
            return None
        urls = []
        for hit in result.results:
            if not hit.url:
                continue
            urls.append(hit.url)
            for text in dict.fromkeys([hit.content, hit.description]):
                if text:
                    self.page(provider, hit.url, hit.title, text, hit.published_date, "search")
            if depth == "deep" and hit.content and hit.content != hit.description:
                self.full.add((provider, hit.url))
        return urls

    async def extract(self, provider, url):
        if (provider, url) in self.extracted or (provider, url) in self.full:
            return
        self.extracted.add((provider, url))
        result = await self.call(provider, "extract", 1 if provider == "nimble" else 2, {"url": url},
                                 lambda: self.router.extract(url, provider=provider, format="markdown",
                                                             data_apis=False, timeout=CALL_TIMEOUT))
        if result:
            for doc in result.documents:
                self.page(provider, doc.url, doc.title, doc.content, self.dates.get(url), "extract")
                if doc.content:
                    self.full.add((provider, url))

    async def extract_pages(self, provider, groups, cap, reserve=0):
        # Take one result per query per pass before considering lower-ranked pages.
        ordered = dict.fromkeys(url for group in zip_longest(*groups) for url in group if url)
        todo = [url for url in ordered if (provider, url) not in self.extracted and (provider, url) not in self.full]
        count = min(cap, max(0, self.remaining - reserve) // (1 if provider == "nimble" else 2))
        if todo and count and self.proof.missing():
            await asyncio.gather(*(self.extract(provider, url) for url in todo[:count]))

    def read_claims(self, result):
        # SDK raw run metadata may contain parsed datetime objects. Keep the JSON form the
        # portable snapshot contract requires, together with every returned claim and citation.
        wire = result.model_dump(mode="json")
        data = wire["structured"]
        if not isinstance(data, dict) and result.answer:
            try:
                data = json.loads(result.answer)
            except (ValueError, TypeError):
                pass
        citations = wire["citations"]
        self.record["research"].append({"answer": result.answer, "structured": data, "citations": citations,
                                       "raw": wire["raw"]})
        if not isinstance(data, dict):
            return
        for f in FIELDS:
            raw = data.get(f)
            value = raw.get("value") if isinstance(raw, dict) else raw
            if value is None:
                continue
            sources = []
            if isinstance(raw, dict):
                sources.append(raw)
                for key in ("citation", "citations", "source", "sources"):
                    entries = raw.get(key, [])
                    sources.extend(entries if isinstance(entries, list) else [entries])
            for cite in citations:
                path = cite.get("field") or ""
                if f in re.findall(r"[A-Za-z_]+", path):
                    sources.append(cite)
                    sources.extend(dict(cite, excerpt=s) for s in cite.get("extra", {}).get("excerpts", []))
            for source in sources:
                if isinstance(source, dict):
                    url = source.get("url") or source.get("source_url")
                    quote = source.get("excerpt") or source.get("snippet") or source.get("quote")
                    if (isinstance(quote, str) and isinstance(url, str)
                            and self.proof.support.subject.search(quote)):
                        self.leads[f] = (value, url)
                    self.proof.observe(url, "nimble", quote, source.get("published_at"), (f, value))

    async def confirm(self, provider):
        missing = self.proof.missing()
        searches = {}
        if "headcount_range" in missing and self.proof.staff_observations:
            observations = self.proof.staff_observations
            count = max(observations, key=observations.get)
            searches["headcount_range"] = f'"{count:,} employees" worldwide workforce'
        if "ceo" in missing and "ceo" in self.leads:
            person = self.leads["ceo"][0]
            if isinstance(person, str):
                searches["ceo"] = f'"{person[:100]}" chief executive officer CEO leadership'
        if "funding_total" in missing and "funding_total" in self.leads:
            amount = self.leads["funding_total"][0]
            if type(amount) is int and amount > 0:
                if amount >= 10**9:
                    money = f"{amount/10**9:g} billion"
                elif amount >= 10**6:
                    money = f"{amount/10**6:g} million"
                else:
                    money = f"{amount:,}"
                searches["funding_total"] = f'"{money}" "raised" total equity funding to date'
        price = SEARCH_COST[provider]["lite"]
        queries = list(searches.values())[:self.remaining // price]
        urls = [self.leads[f][1] for f in missing if f in self.leads]
        results = await asyncio.gather(*(self.search(provider, f"{self.domain} {query}") for query in queries))
        await self.extract_pages(provider, [urls, *(r for r in results if r)], 6)

    async def research_run(self):
        name = self.proof.support.name
        query = (f"Research the company at {self.domain} ({name}). Find its registered legal name, city of global "
                 "headquarters, current CEO, year founded, worldwide employee count as a headcount range, and "
                 "cumulative equity funding in whole US dollars. For each field give the value, URL and one "
                 "verbatim sentence from the page naming the company and explicitly stating the fact. "
                 "Use null if unavailable. Prefer recent first-party evidence. For headcount use 1-10, 11-50, "
                 "51-200, 201-500, 501-1000, 1001-5000, 5001-10000 or 10001+.")
        job = await self.call("nimble", "research", 25, {"query": query},
                              lambda: self.router.submit_research(query, provider="nimble", effort="low",
                                                                  output_schema=claim_schema()))
        if job is not None:
            job.poll_interval = 0.2
            job.poll_max_interval = 3
            try:
                result = await job.aresult(timeout=max(1, self.deadline - asyncio.get_running_loop().time() - 1))
            except Exception as exc:
                self.record_issue(type(exc).__name__)
            else:
                self.read_claims(result)

    async def gather(self):
        providers = [p for p, enabled in (("nimble", self.nimble), ("tavily", self.tavily)) if enabled]
        if not providers:
            return
        primary = providers[0]
        base = None
        for provider in providers:
            base = await self.search(provider, self.domain)
            if base is not None:
                primary = provider
                break
        if base is None:
            # Retry a refused anchor once; other operations can work even when search is unavailable.
            base = await self.search(primary, self.domain)
        if base:
            await self.extract_pages(primary, [base], 10)
        if not self.proof.missing():
            return
        reserve = 25 if self.nimble else 0
        queries = [f"{self.domain} {PROMPTS[f]} {f}" for f in self.proof.missing()]
        if primary == "tavily":
            # Group queries where the higher price would otherwise crowd out retrieval.
            queries = [f"{self.domain} " + " ".join(PROMPTS[f] for f in self.proof.missing())]
        results = await asyncio.gather(*(self.search(primary, q) for q in queries))
        groups = [r for r in results if r]
        await self.extract_pages(primary, groups, 18, reserve)
        if self.nimble and self.proof.missing():
            await self.research_run()
        if self.proof.missing() and (self.leads or self.proof.staff_observations):
            await self.confirm(primary)
        if not self.proof.missing():
            return
        other = "tavily" if primary == "nimble" and self.tavily else primary
        missing = self.proof.missing()
        query = f"{self.domain} company profile " + " ".join(PROMPTS[f] for f in missing)
        # Ranked URL/snippet results have already been examined. Request page bodies even when
        # those searches found links: extraction may have been refused, or the snippets truncated.
        depth = "deep" if other == "tavily" else "fast"
        supplemental = await self.search(other, query, depth) or []
        await self.extract_pages(other, [supplemental, *groups, base or []], 10)
        if self.proof.missing() and self.remaining:
            # Providers can index a company's policy, about and team pages separately from its homepage.
            query = f"site:{self.domain} about company leadership legal " + " ".join(PROMPTS[f] for f in self.proof.missing())
            depth = "deep" if self.remaining >= SEARCH_COST[primary]["deep"] else "lite"
            official = await self.search(primary, query, depth) or []
            await self.extract_pages(primary, [official, *groups], 10)

    async def run(self):
        self.deadline = asyncio.get_running_loop().time() + 285
        try:
            async with asyncio.timeout_at(self.deadline):
                await self.gather()
        except TimeoutError:
            self.record_issue("Build deadline")
