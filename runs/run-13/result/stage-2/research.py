"""One metered WebRouter research session per dossier build."""
import asyncio
from collections import Counter
import os
import re
from urllib.parse import urlsplit

from nimble_python import AsyncNimble
from web_router import AsyncWebRouter
from web_router.exceptions_typed import ExtractFailedError

from evidence import PHRASES, STATEMENTS, resolve

QUESTIONS = {
    "legal_name": "legal name registered company terms of service",
    "hq_city": "headquarters headquartered in based in city",
    "ceo": "CEO chief executive officer leadership",
    "founded_year": "founded established incorporated history",
    "headcount_range": "employs employees workforce total headcount people staff",
    "funding_total": "total equity funding raised to date investment",
}


class Providers:
    def __init__(self):
        self.available = [p for p in ("nimble", "tavily") if os.getenv(p.upper() + "_API_KEY")]
        config = {}
        self.client = None
        if "nimble" in self.available:
            self.client = AsyncNimble(max_retries=0, timeout=42)
            config["nimble"] = {"async_client": self.client}
        if os.getenv("TAVILY_BASE_URL"):
            config["tavily"] = {"api_base_url": os.environ["TAVILY_BASE_URL"]}
        self.router = AsyncWebRouter(provider_config=config, router=None)

    async def close(self):
        await self.router.aclose()
        if self.client:
            await self.client.close()


def own(url, domain):
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return False
    return host == domain or host.endswith("." + domain)


class Build:
    def __init__(self, domain, providers, started):
        self.domain = domain
        self.providers = providers
        self.started = started
        self.units = 0
        self.reserved = 0
        self.success = False
        self.calls = []
        self.pages = []
        self.extracted = set()
        self.deadline = asyncio.get_running_loop().time() + 285

    async def call(self, provider, method, target, cost, invoke):
        for attempt in range(4):
            result, retry = await self.attempt(provider, method, target, cost, invoke)
            if not retry or attempt == 3:
                return result
            await asyncio.sleep(1.03)

    async def attempt(self, provider, method, target, cost, invoke):
        remaining = self.deadline - asyncio.get_running_loop().time()
        if remaining < 30 or self.units + self.reserved + cost > 80:
            return None, False
        self.reserved += cost
        record = {"provider": provider, "method": method, "target": target, "cost": 0}
        self.calls.append(record)
        billed, ok = cost, False
        try:
            async with asyncio.timeout(min(remaining, 45)):
                result = await invoke()
            ok = True
            return result, False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # An extract can return HTTP 200 and report that no page was obtained.
            if isinstance(exc, ExtractFailedError) and not exc.call_errors:
                ok = True
            else:
                error = next(iter(getattr(exc, "call_errors", ())), exc)
                if getattr(error, "status_code", None) or getattr(error, "kind", "") in {
                    "configuration", "invalid_request", "unsupported_parameter"
                }:
                    billed = 0
            record["outcome"] = type(exc).__name__
            return None, getattr(exc, "status_code", None) == 429
        finally:
            self.reserved -= cost
            self.units += billed
            record["cost"] = billed
            self.success |= ok

    def page(self, provider, url, text, method, date="", claim=None, *, plain=False):
        if not isinstance(text, str) or not url:
            return
        self.pages.append({"url": url, "provider": provider, "text": text, "method": method,
                           "date": date, "claim": claim, "plain": plain})


    async def search(self, query, provider, depth):
        cost = {"nimble": {"lite": 1, "fast": 5, "deep": 15}, "tavily": {"lite": 8, "deep": 16}}[provider][depth]
        result = await self.call(provider, "search", query, cost, lambda: self.providers.router.search(
            query, provider=provider, search_depth=depth, max_results=10, timeout=42, data_apis=False))
        if result is None:
            return None
        for row in result.results:
            self.page(provider, row.url, row.content or row.description, depth, row.published_date or "")
        return [r.url for r in result.results if r.url.startswith(("http://", "https://"))]

    async def extract(self, url, provider, render):
        method = "render" if render else "extract"
        cost = 3 if render else (1 if provider == "nimble" else 2)
        # Ask the provider browser for the text its reader sees, in the same
        # rendered extract. An optional read does not interact with the page.
        options = {"render": True, "browser_actions": [
            {"eval": {"code": "document.body.innerText", "required": False}}
        ]} if render else {}
        result = await self.call(provider, method, url, cost, lambda: self.providers.router.extract(
            url, provider=provider, timeout=42, data_apis=False, provider_options=options))
        if result:
            self.extracted.add(url)
            for doc in result.documents:
                actions = (doc.extra or {}).get("browser_actions") or {}
                visible = next((row.get("result") for row in actions.get("results", [])
                                if row.get("name") == "eval" and row.get("status") == "done"
                                and isinstance(row.get("result"), str)), None)
                if visible is None:
                    self.page(provider, doc.url, doc.content, method)
                else:
                    self.page(provider, doc.url, doc.content, "serialized")
                    self.page(provider, doc.url, visible, method, plain=True)
        return bool(result)

    async def research(self):
        schema = {"type": "object", "properties": {
            field: {"type": "integer" if field in ("founded_year", "funding_total") else "string",
                    "description": question} for field, question in QUESTIONS.items()}}
        query = (f"Research the company operating {self.domain}. Find its registered legal name, headquarters city, "
                 "current chief executive, founding year, total company employee count range and cumulative equity "
                 "funding in US dollars. Quote verbatim source sentences naming this company and stating each fact. "
                 "Prefer current official sources. Exclude partners' and customers' details.")
        job = await self.call("nimble", "research", query, 25, lambda: self.providers.router.submit_research(
            query, provider="nimble", output_schema=schema))
        if job is None:
            return []
        try:
            result = await job.aresult(timeout=min(140, self.deadline - asyncio.get_running_loop().time()))
        except Exception:
            return []
        structured = result.structured if isinstance(result.structured, dict) else {}
        urls = []
        for c in result.citations:
            if c.url:
                urls.append(c.url)
            field = (c.field or "").removeprefix("$.")
            self.page("nimble", c.url, c.snippet, "research", claim=[field, structured.get(field)])
        return urls

    async def gather(self):
        if not self.providers.available:
            return
        provider = self.providers.available[0]
        initial = await self.search(self.domain, provider, "fast" if provider == "nimble" else "deep")
        if initial is None and "tavily" in self.providers.available and provider != "tavily":
            provider = "tavily"
            initial = await self.search(self.domain, provider, "deep")
        initial = initial or []

        # Each field search can uncover contrary evidence even when a value
        # already exists. Research may cite pages that search cannot return.
        tasks = []
        if provider == "nimble":
            tasks = [self.search(f"{self.domain} {terms}", provider, "lite") for terms in QUESTIONS.values()]
        else:
            tasks = [self.search(f"{self.domain} headquarters leadership funding company profile", provider, "deep")]
        do_research = "nimble" in self.providers.available
        if do_research:
            tasks.append(self.research())
        responses = list(await asyncio.gather(*tasks))
        claims = responses.pop() if do_research else []
        if provider == "nimble" and initial:
            # Search for corroboration using the actual wording found so far.
            # A news story and its republications may mention a person's name
            # but use different role vocabulary from the original field search.
            early = resolve(self.domain, self.started, self.pages, discovery=True)
            queries = []
            for field, answer in early.items():
                if not answer["candidates"]:
                    continue
                values = list(dict.fromkeys(str(c["value"]) for c in answer["candidates"]))[:3]
                if field == "headcount_range":
                    query = "work employs people employees staff workforce"
                else:
                    query = " ".join(values) + " " + PHRASES[field].split("|")[0]
                queries.append(self.search(f"{self.domain} {query}", provider, "lite"))
            responses.extend(await asyncio.gather(*queries))
        ranked = [initial] + [r or [] for r in responses]
        urls = [row[i] for i in range(max(map(len, ranked), default=0)) for row in ranked if len(row) > i]
        urls = list(dict.fromkeys(claims + urls))
        if not urls:
            urls = [f"https://{self.domain}{p}" for p in ("/about", "/", "/company", "/terms")]
        provider = "nimble" if "nimble" in self.providers.available else "tavily"
        await self.read_pages(urls, claims, provider)

    async def read_pages(self, urls, claims, provider):
        if provider != "nimble":
            return
        # Prioritize promising pages before spending on rendering. Evidence
        # used for ranking URLs never enters the published candidate set.
        early = resolve(self.domain, self.started, self.pages, discovery=True)
        supported = {c["url"] for answer in early.values() for c in answer["candidates"]}
        # With a finite render budget, give every field a chance to obtain a
        # full page for its strongest discovery lead. Corroboration is used
        # only to schedule extracts; final selection obeys the fixed rank.
        leads = set()
        for answer in early.values():
            candidates = answer["candidates"]
            if candidates:
                sources = {(c["value"], c["url"]) for c in candidates}
                support = Counter(value for value, _ in sources)
                best = max(candidates, key=lambda c: (c["kind"] in ("own", "filing"), support[c["value"]]))
                leads.add(best["url"])
        samples = {}
        for p in self.pages:
            samples.setdefault(p["url"], []).append(p["text"][:3000])

        def priority(url):
            text = " ".join(samples.get(url, []))
            dynamic = re.search(r"(?i)javascript|enable scripting|loading[. …]|load(?:ing)? (?:the )?(?:profile|data)", text)
            official = own(url, self.domain)
            profile = re.search(r"/(?:company|about|leadership|press|legal|terms|investors|newsroom)(?:[/?#-]|$)", url, re.I)
            return (not dynamic, url not in claims, url not in leads, url not in supported, not (official and profile),
                    not official, not any(p.search(text) for p in STATEMENTS.values()))

        ordered = sorted(urls, key=priority)
        while ordered:
            count = min(len(ordered), (80 - self.units) // 3)
            if count == 0 or self.deadline - asyncio.get_running_loop().time() < 30:
                break
            batch, ordered = ordered[:count], ordered[count:]
            await asyncio.gather(*(self.extract(url, provider, True) for url in batch))

    async def run(self):
        try:
            async with asyncio.timeout_at(self.deadline):
                await self.gather()
        except Exception as exc:
            # Keep completed evidence if the provider returns an unexpected payload.
            print("Build interrupted:", type(exc).__name__, flush=True)
        return resolve(self.domain, self.started, self.pages)
