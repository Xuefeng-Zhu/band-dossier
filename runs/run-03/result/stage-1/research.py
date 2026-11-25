"""One budget and one evidence set per background build."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit
import os
import re

from web_router import WebRouter
from web_router.exceptions import ProviderError

from evidence import FIELDS, PHRASES, empty_fields, sentences, values

ROUTER = WebRouter("nimble", provider_config={"nimble": {"max_retries": 0, "timeout": 45}})
if os.environ.get("NIMBLE_API_KEY"):
    ROUTER.get_provider()
    ROUTER.get_extract_provider()
    ROUTER.get_research_provider()
IO = ThreadPoolExecutor(max_workers=64)
TOPICS = {
    "legal_name": "registered company legal name registered as",
    "hq_city": "headquarters headquartered in head office registered seat",
    "ceo": "CEO chief executive officer leadership",
    "founded_year": "founded incorporated established company history",
    "headcount_range": "employees headcount workforce employs staff",
    "funding_total": "total funding raised investment dollars",
}
SCHEMA = {"type": "object", "properties": {
    f: {"type": ["integer" if f in ("founded_year", "funding_total") else "string", "null"]}
    for f in FIELDS}}


class Build:
    def __init__(self, domain, active, charge):
        self.domain = domain
        self.active = active
        self.charge = charge
        self.started = monotonic()
        self.fields = empty_fields()
        self.founding_sources = {}
        self.lock = Lock()
        self.used = 0
        self.reserved = 0
        self.success = False
        self.calls = []
        self.pages = []
        self.claims = []
        self.urls = {}
        self.attempted = set()

    def call(self, method, target, price, action):
        with self.lock:
            if not self.active() or self.used + self.reserved + price > 80 or monotonic() - self.started > 245:
                return None
            self.reserved += price
        answered = False
        cost = 0
        result = None
        try:
            result = action()
            answered, cost = True, price
        except ProviderError as exc:
            cause = exc.original or exc.__cause__
            if getattr(cause, "status_code", None) is not None:
                cost = 0
            elif cause is not None:
                cost = price
            elif method == "extract":
                # WebRouter raises on a 200 extract with zero documents.
                answered, cost = True, price
        except (OSError, TimeoutError):
            cost = price
        except Exception:
            # Invalid local configuration/arguments never dispatched a request.
            pass
        finally:
            with self.lock:
                self.reserved -= price
                self.used += cost
                self.success |= answered
                self.calls.append({"method": method, "target": target, "units": cost, "answered": answered})
                self.charge(cost)
        return result

    def search(self, query, deep=False):
        return self.call("search", query, 15 if deep else 1, lambda: ROUTER.search(
            query, max_results=10, search_depth="deep" if deep else "lite"))

    def add_page(self, url, text, kind, *, field=None, claim=None):
        if not text or not url or urlsplit(url).scheme not in ("http", "https"):
            return
        self.pages.append({"url": url, "text": text, "kind": kind, "provider": "nimble"})
        # A snippet ending at the provider's character cap can truncate a fact.
        excerpts = list(sentences(text))
        if kind == "research" and len(excerpts) != 1:
            return
        for sentence in excerpts:
            if kind == "snippet" and len(text) >= 300 and text.rstrip().endswith(sentence) and sentence[-1:] not in '.!?”")':
                continue
            for name, value in values(self.domain, sentence).items():
                if field and (name != field or str(claim) != str(value)):
                    continue
                citation = {"url": url, "excerpt": sentence, "provider": "nimble"}
                if name == "founded_year":
                    self.add_founding_source(value, citation)
                    continue
                current = self.fields[name]
                if current["value"] is None:
                    current.update(value=value, status="known")
                if current["value"] == value and citation not in current["citations"]:
                    current["citations"].append(citation)

    def add_founding_source(self, year, citation):
        # Only Appendix A-eligible statements reach this method. A local
        # incorporation date can disagree with the company's founding date.
        sources = self.founding_sources.setdefault(year, [])
        if citation in sources:
            return
        sources.append(citation)

        def strength(candidate):
            pages = self.founding_sources[candidate]
            hosts = {(urlsplit(p["url"]).hostname or "").removeprefix("www.") for p in pages}
            primary = any(h == self.domain or h.endswith("." + self.domain) for h in hosts)
            direct = any(re.search(r"\b(founded|founding|established)\b", p["excerpt"], re.I) for p in pages)
            return (primary and len(hosts) > 1, primary and direct, direct, len(hosts), primary)

        winner = max(self.founding_sources, key=strength)
        self.fields["founded_year"] = {"value": winner, "status": "known", "citations": self.founding_sources[winner]}

    def add_results(self, response, deep=False):
        if response is None:
            return
        for index, result in enumerate(response.results):
            self.urls[result.url] = self.urls.get(result.url, 0) + 1 / (index + 1)
            self.add_page(result.url, result.content or result.description, "full" if deep else "snippet")

    def missing(self):
        return [name for name, data in self.fields.items() if data["value"] is None]

    def extract(self, url):
        return self.call("extract", url, 1, lambda: ROUTER.extract(url, format="markdown"))

    def gather_urls(self, reserve=0):
        available = max(0, 80 - reserve - self.used - self.reserved)
        urls = [u for u in sorted(self.urls, key=self.urls.get, reverse=True) if u not in self.attempted][:available]
        self.attempted.update(urls)
        for response in IO.map(self.extract, urls):
            if response:
                for doc in response.documents:
                    self.add_page(doc.url, doc.content, "full")

    def research(self):
        query = f"For {self.domain} provide the registered legal name, headquarters city, CEO, founding year, employee range and total equity funding in whole US dollars. Quote a supporting sentence for each field."
        job = self.call("research", query, 25, lambda: ROUTER.submit_research(query, output_schema=SCHEMA))
        if job:
            try:
                job.poll_interval = 0.1
                return job.result(timeout=max(1, 280 - (monotonic() - self.started)))
            except Exception:
                return None

    def run(self):
        response = self.search(self.domain)
        if response is None and self.active():
            # Refusals and transport failures are both unanswered. The budget
            # accounts for their different costs independently of this retry.
            response = self.search(self.domain)
        self.add_results(response)
        if self.missing():
            self.gather_urls(reserve=32)
        missing = self.missing()
        if missing and self.active():
            research = IO.submit(self.research)
            queries = [f"{self.domain} {TOPICS[name]}" for name in missing]
            for response in IO.map(self.search, queries):
                self.add_results(response)
            if self.missing():
                self.gather_urls(reserve=25 if self.used < 25 and self.reserved < 25 else 0)
            answer = research.result()
            if answer and isinstance(answer.structured, dict):
                for citation in answer.citations:
                    field = (citation.field or "").removeprefix("$.")
                    if field in FIELDS and (claim := answer.structured.get(field)) is not None:
                        self.claims.append({"field": field, "value": claim, "url": citation.url, "excerpt": citation.snippet})
                        self.add_page(citation.url, citation.snippet, "research", field=field, claim=claim)
            # Search by the company name as well. Some pages mention only its
            # name, and different wording can surface them above the ten-hit cap.
            if self.missing() and self.urls:
                name = self.domain.split(".")[0].replace("-", " ")
                queries = [f"{name} {' '.join(PHRASES[field])}" for field in self.missing()]
                for response in IO.map(self.search, queries):
                    self.add_results(response)
                if self.missing():
                    self.gather_urls()
            # When extracts did not deliver every result, deep search is
            # another source for the full prose.
            full = {p["url"] for p in self.pages if p["kind"] == "full"}
            if self.missing() and self.urls.keys() - full:
                topics = " ".join(TOPICS[f] for f in self.missing())
                self.add_results(self.search(f"{self.domain} {topics} company profile", deep=True), deep=True)
        return self.fields
