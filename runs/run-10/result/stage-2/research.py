"""One research transaction. Reserve worst-case units before each outbound dispatch."""
import asyncio
import os
import re
import time
from urllib.parse import urlsplit
from web_router import AsyncWebRouter
from web_router.exceptions_typed import ExtractFailedError
from evidence import Evidence, FIELDS

QUERIES = {
    "legal_name": "legal name registered company legal entity",
    "hq_city": "where is headquartered headquarters based in",
    "ceo": "CEO chief executive officer",
    "founded_year": "when was company founded established incorporated",
    "headcount_range": "number of employees people headcount workforce",
    "funding_total": "total equity funding raised investment dollars",
}
SCHEMA = {"type":"object","properties":{
    k: {"type":["integer" if k in ("funding_total","founded_year") else "string","null"]}
    for k in FIELDS}, "required":list(FIELDS)}
COST = {"nimble":{"lite":1,"deep":15,"extract":1,"render":3,"research":25},
        "tavily":{"lite":8,"deep":16,"extract":2}}
_router = None

def router():
    global _router
    if _router is None:
        config = {"nimble":{"timeout":65, "max_retries":0}}
        if os.getenv("TAVILY_BASE_URL"):
            config["tavily"] = {"api_base_url":os.environ["TAVILY_BASE_URL"]}
        _router = AsyncWebRouter(provider="nimble",provider_config=config)
    return _router

# WebRouter wraps the provider's task outcome in the SDK HTTP exception.
# Only evidence of a target response or an attempted download is chargeable.
NOT_DISPATCHED = re.compile(
    r"\b(?:before (?:any |the )?(?:dispatch|schedul|fetch|download)|"
    r"(?:not|never) (?:been |yet )?(?:scheduled|dispatched|submitted|started|attempted)|"
    r"no (?:request|fetch|download|task) (?:was |has been )?(?:scheduled|dispatched|started|attempted)|"
    r"(?:provider|service) (?:has )?(?:refused|rejected|declined) (?:admission|the request|to )|"
    r"insufficient (?:balance|credits)|(?:quota|credits|capacity) (?:is |was )?exhausted)", re.I)
TARGET_STATUS = re.compile(
    r"\b(?:server|origin|target(?: page)?|website|page) (?:returned|responded with|sent) "
    r"(?:http(?: status)? |status(?: code)? )?[45][0-9]{2}\b", re.I)
FAILED_RETRIEVAL = re.compile(
    r"\b(?:can['’]t|cannot|could(?: not|n['’]t)|failed to|unable to) (?:download|fetch|retrieve|load) "
    r"(?:the |a )?(?:query response|target|remote|origin|page|website|url|resource|content|response)\b",
    re.I)

def exception_chain(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = getattr(exc, "original", None) or exc.__cause__ or exc.__context__

def failure_outcome(exc):
    # Retain typed causes, HTTP status and OS errno. Exception messages can
    # contain request data, so the archive only records these fixed attributes.
    parts = []
    for cause in exception_chain(exc):
        name = type(cause).__name__
        status = getattr(cause, "status_code", None)
        errno = getattr(cause, "errno", None)
        if isinstance(status, int):
            name += f"(HTTP {status})"
        if isinstance(errno, int):
            name += f"(errno {errno})"
        parts.append(name)
    return " <- ".join(parts)

def completed_page_failure(exc):
    for cause in exception_chain(exc):
        body = getattr(cause, "body", None)
        if isinstance(body, dict) and body.get("task_id"):
            stage = str(body.get("stage", "")).lower()
            message = str(body.get("message", ""))
            if stage in {"admission", "validation", "scheduling"} or NOT_DISPATCHED.search(message):
                return False
            failed = (str(body.get("status", "")).lower() in {"failed", "error", "blocked"}
                      or str(body.get("success")).lower() == "false")
            if failed and (body.get("target_status_code") or TARGET_STATUS.search(message)
                           or FAILED_RETRIEVAL.search(message)):
                return True
    return False

def refused(exc):
    for cause in exception_chain(exc):
        if getattr(cause,"status_code",None) or getattr(getattr(cause,"response",None),"status_code",None):
            return True
        if getattr(cause,"kind",None) in ("auth","rate_limit","invalid_request"):
            return True
    return False

class Throttled(Exception):
    pass

class Build:
    def __init__(self, domain, at):
        self.domain = domain
        self.at = at
        self.started = time.monotonic()
        self.evidence = Evidence(domain,at)
        self.spent = self.reserved = 0
        self.success = False
        self.calls = []
        self.sources = []
        self.research_answer = None
        self.discovered = {}
        self.attempted = set()
        self.full = set()
        self.rendered = set()
        self.cited = set()
        self.relevance = {}
        self.providers = [p for p in COST if os.getenv(p.upper() + "_API_KEY")]

    @property
    def missing(self):
        return [f for f in FIELDS if not self.evidence.candidates[f]]

    async def call(self,provider,method,args,invoke):
        for attempt in range(4):
            try:
                return await self.once(provider,method,args,invoke)
            except Throttled:
                if attempt<3:
                    await asyncio.sleep(1.05)
        return None

    async def once(self, provider, method, args, invoke):
        cost = COST[provider][method]
        if self.spent + self.reserved + cost > 80 or time.monotonic()-self.started >= 250:
            return None
        self.reserved += cost
        entry = {"provider":provider,"method":method,"request":args,"units":0}
        self.calls.append(entry)
        try:
            response = await invoke()
        except ExtractFailedError:
            # A completed call with a page-level failure still bought an extract.
            self.success = True
            entry["outcome"] = "empty"
        except Exception as exc:
            entry["outcome"] = failure_outcome(exc)
            if getattr(exc,"status_code",None)==429:
                cost = 0
                raise Throttled from exc
            if provider == "nimble" and method in ("extract","render") and completed_page_failure(exc):
                self.success = True
                entry["outcome"] = "empty"
            elif refused(exc):
                cost = 0
        else:
            self.success = True
            entry["outcome"] = "ok"
            return response
        finally:
            self.reserved -= COST[provider][method]
            self.spent += cost
            entry["units"] = cost

    def source(self, provider, url, text, mode="snippet", **kwargs):
        if not text or not url:
            return
        self.sources.append({"provider":provider,"url":url,"text":text,"mode":mode,**kwargs})
        self.evidence.add(url,text,provider,**kwargs)

    async def search(self, query, provider, depth="lite"):
        response = await self.call(provider,depth,query,lambda:router().search(
            query,provider=provider,search_depth=depth,max_results=10,timeout=65,data_apis=False))
        if response is None:
            return False
        for position,result in enumerate(response.results):
            self.discovered.setdefault(result.url,provider)
            subject = self.evidence.subject.search(result.title+" "+result.description)
            score = (20 if subject else 0) + (10-position) + (3 if query==self.domain else 0)
            self.relevance[result.url] = max(self.relevance.get(result.url,0),score)
            if depth == "deep" and result.content:
                self.full.add(result.url)
            self.source(provider,result.url,result.content,"page" if depth=="deep" else "snippet")
            if result.description and result.description != result.content:
                self.source(provider,result.url,result.description)
        return True

    async def extract(self,url,provider,render=False):
        method = "render" if render else "extract"
        self.attempted.add((provider,method,url))
        options = {"render":True} if render else None
        response = await self.call(provider,method,url,lambda:router().extract(
            url,provider=provider,provider_options=options,timeout=65,data_apis=False))
        if response:
            for doc in response.documents:
                if doc.content:
                    self.full.add(url)
                    if render:
                        self.rendered.update((url,doc.url))
                    self.source(provider,doc.url,doc.content,method)

    def urls(self):
        def priority(url):
            try:
                host = (urlsplit(url).hostname or "").lower().removesuffix(".").removeprefix("www.")
            except ValueError:
                host = ""
            return (url not in self.cited,host!=self.domain,-self.relevance.get(url,0),url)
        return sorted((u for u in self.discovered if u.startswith(("http://","https://"))),key=priority)

    async def research(self):
        query = (f"Research {self.domain}, the company operating that website. Identify its registered legal name, "
                 "headquarters city, current CEO, founding year, employee count range and total equity funding "
                 "in US dollars. Use original, dated sources. Quote exact sentences naming the company.")
        job = await self.call("nimble","research",query,lambda:router().submit_research(
            query,provider="nimble",output_schema=SCHEMA))
        if job is None:
            return
        try:
            await job.astatus()
            response = await job.aresult(timeout=160)
        except Exception:
            return
        claimed = response.structured if isinstance(response.structured,dict) else {}
        self.research_answer = {"values":claimed, "citations":[{
            "url":c.url,"field":c.field,"snippet":c.snippet,"excerpts":c.extra.get("excerpts",[])
        } for c in response.citations]}
        for cite in response.citations:
            self.discovered.setdefault(cite.url,"nimble")
            self.cited.add(cite.url)
            # Research identifies evidence pages. Only independently retrieved
            # page prose may supply the excerpts displayed as candidates.

    async def discover(self):
        for p in self.providers:
            if await self.search(self.domain,p,"lite" if p=="nimble" else "deep"):
                if p=="nimble":
                    await asyncio.gather(*(self.search(f"{self.domain} {terms}",p) for terms in QUERIES.values()))
                return p
        return None

    async def gather(self):
        if not self.providers:
            return
        if "nimble" in self.providers:
            primary,_ = await asyncio.gather(self.discover(),self.research())
        else:
            primary = await self.discover()
        p = self.providers[0]
        urls = self.urls()
        if p=="nimble":
            # Render research citations and high-relevance pages. Reserve one unit
            # per remaining discovered page when the budget can cover a plain extract.
            available = 80-self.spent
            count = min(len(urls),available//3,max(min(len(self.cited)+3,available//3),(available-len(urls))//2))
            await asyncio.gather(*(self.extract(u,p,True) for u in urls[:count]))
        remaining = [u for u in urls if u not in self.full]
        count = (80-self.spent)//COST[p]["extract"]
        await asyncio.gather(*(self.extract(u,p) for u in remaining[:count]))
        if self.missing and primary and not self.full:
            await self.search(f"{self.domain} company profile about leadership",primary,"deep")
        if self.missing and primary:
            for path in ("/about","/company","/about-us"):
                url = f"https://{self.domain}{path}"
                if url not in self.discovered:
                    self.discovered[url]=p
            extras = [u for u in self.urls() if u not in self.full and (p,"extract",u) not in self.attempted]
            await asyncio.gather(*(self.extract(u,p) for u in extras[:6]))

    def fields(self):
        evidence = Evidence(self.domain,self.at)
        for source in self.sources:
            url,mode = source["url"],source["mode"]
            if url in self.rendered and mode!="render":
                continue
            evidence.add(url,source["text"],source["provider"],claim=source.get("claim"))
        return evidence.fields()

    async def run(self):
        try:
            async with asyncio.timeout(285):
                await self.gather()
        except TimeoutError:
            pass
        return self.fields()

    def archive(self):
        return {"at":self.at,"calls":self.calls,"sources":self.sources,"research":self.research_answer}
