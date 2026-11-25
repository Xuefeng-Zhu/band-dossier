import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
from urllib.parse import unquote, urlsplit
from datetime import datetime, timezone

from aiohttp import web

from evidence import PHRASES, empty_fields, sentences, values
from research import Build, create_router


class Error(Exception):
    def __init__(self, status=422, code="validation_failed"):
        self.status = status
        self.code = code


def require(condition):
    if not condition:
        raise Error()


def typed(value, kind):
    if type(value) is not kind:
        raise Error(400, "malformed_request")
    return value


def field(body, name, kind=str):
    require(name in body)
    return typed(body[name], kind)


def domain(value):
    normalized = value.strip().lower().removesuffix(".").removeprefix("www.")
    require(len(normalized) <= 253 and "." in normalized)
    require(all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in normalized.split(".")))
    return normalized


def timestamp(value):
    require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value))
    try:
        date = datetime.fromisoformat(value.replace("z", "+00:00").replace("Z", "+00:00"))
        fraction = re.search(r"\.([0-9]+)", value)
        # A normalized decimal fraction compares lexically, including digits beyond
        # datetime's microsecond precision. Keep the input string for API timestamps.
        return date.replace(microsecond=0), fraction[1].rstrip("0") if fraction else ""
    except ValueError:
        raise Error()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt),
                            n=16384, r=8, p=1)
    return salt + ":" + digest.hex()


def identity(body, fixture=False):
    email, password, name = (field(body, key) for key in ("email", "password", "display_name"))
    require(re.fullmatch(r"[^\s@]+@[^\s@]+", email) and len(password) >= 8 and 0 < len(name) <= 100)
    uid = field(body, "id") if fixture else secrets.token_hex(16)
    require(0 < len(uid) <= 64)
    return email, password, {"id": uid, "display_name": name}


def fresh():
    return dict(users={}, tokens={}, dossiers={}, keys={}, history={})


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def opaque_id(value):
    return type(value) is str and 0 < len(value) <= 64


def validate_field(key, name, record):
    require(type(record) is dict and set(record) == {"value", "status", "citations"})
    value, citations = record["value"], record["citations"]
    require(type(citations) is list)
    if record["status"] == "unknown":
        require(value is None and not citations)
        return
    numeric = name in ("founded_year", "funding_total")
    require(record["status"] == "known" and citations and type(value) is (int if numeric else str))
    for citation in citations:
        require(type(citation) is dict and set(citation) == {"url", "provider", "excerpt"})
        require(citation["provider"] in ("nimble", "tavily"))
        url = urlsplit(citation["url"])
        require(url.scheme in ("http", "https") and url.hostname)
        excerpt = citation["excerpt"]
        require(type(excerpt) is str and 1 <= len(excerpt) <= 500)
        require(list(sentences(excerpt)) == [excerpt] and values(key, excerpt).get(name) == value)


def validate_history(history):
    require(type(history) is list)
    total = 0
    for build in history:
        require(type(build) is dict and type(build["calls"]) is list and type(build["pages"]) is list)
        timestamp(build["at"])
        spend = 0
        for call in build["calls"]:
            require(type(call) is dict and call["method"] in ("search", "extract", "research"))
            require(type(call["argument"]) is str and type(call["cost"]) is int)
            price = 25 if call["method"] == "research" else 1
            require(type(call["units"]) is int and call["units"] == price and call["cost"] in (0, price))
            spend += call["cost"]
        require(spend <= 80)
        total += spend
        for page in build["pages"]:
            require(type(page) is dict and page["provider"] in ("nimble", "tavily")
                    and type(page["url"]) is str and type(page["text"]) is str)
    return total


def validate_data(data):
    require(type(data) is dict and all(type(data.get(k)) is dict for k in fresh()))
    ids = set()
    for email, u in data["users"].items():
        require(re.fullmatch(r"[^\s@]+@[^\s@]+", email) and type(u) is dict and opaque_id(u["id"])
                and u["id"] not in ids and type(u["display_name"]) is str and 0 < len(u["display_name"]) <= 100
                and re.fullmatch(r"[a-f0-9]{32}:[a-f0-9]{128}", u["hash"]))
        ids.add(u["id"])
    require(all(token and uid in ids for token, uid in data["tokens"].items()))
    require(data["history"].keys() <= data["dossiers"].keys())
    dossier_ids = set()
    for key, dossier in data["dossiers"].items():
        require(domain(key) == key == dossier["domain"] and dossier["state"] in ("ready", "failed"))
        require(type(dossier["spent_units"]) is int and dossier["spent_units"] == validate_history(data["history"].get(key, [])))
        require(opaque_id(dossier["dossier_id"]) and dossier["dossier_id"] not in dossier_ids)
        dossier_ids.add(dossier["dossier_id"])
        if dossier["researched_at"] is None:
            require(dossier["state"] == "failed" and dossier["fields"] == empty_fields())
        else:
            timestamp(dossier["researched_at"])
        require(type(dossier["fields"]) is dict and dossier["fields"].keys() == PHRASES.keys())
        for name, record in dossier["fields"].items():
            validate_field(key, name, record)
    for scope, entry in data["keys"].items():
        uid, path, key = json.loads(scope)
        require(uid in ids and type(path) is str and type(key) is str and 1 <= len(key) <= 255)
        require(scope == encode([uid, path, key]).decode() and type(entry["body"]) is dict)
        decoded = unquote(path)
        if decoded == "/dossiers":
            require(set(entry["body"]) == {"domain"} and type(entry["body"]["domain"]) is str)
            normalized = domain(entry["body"]["domain"])
        else:
            require(decoded.startswith("/dossiers/") and decoded.endswith("/refresh") and not entry["body"])
            normalized = domain(decoded[len("/dossiers/"):-len("/refresh")])
        saved = entry["response"]
        require(type(saved) is dict and set(saved) == {"domain", "dossier_id", "state"}
                and saved["domain"] == normalized and saved["dossier_id"] == data["dossiers"][normalized]["dossier_id"]
                and saved["state"] in ("building", "ready", "failed"))


async def body(request):
    try:
        value = await request.json(loads=lambda s: json.loads(s, parse_constant=lambda _: invalid_json()))
    except (ValueError, UnicodeError, RecursionError):
        raise Error(400, "malformed_request")
    return typed(value, dict)


def invalid_json():
    raise ValueError()


def response(value, status=200):
    return web.Response(body=encode(value), status=status, content_type="application/json", charset="utf-8")


def page_parameter(query, key, default, low, high=None):
    if key not in query:
        return default
    digits = query[key]
    require(re.fullmatch("[0-9]+", digits))
    digits = digits.lstrip("0") or "0"
    if len(digits) > 20:
        require(high is None)
        return 10**20
    value = int(digits)
    require(value >= low and (high is None or value <= high))
    return value


class Service:
    def __init__(self):
        self.data = fresh()
        self.clock = None
        self.running = {}
        self.router = create_router()
        self.tasks = set()
        self.hash_slots = asyncio.Semaphore(4)

    async def hash(self, password, salt=None):
        async with self.hash_slots:
            return await asyncio.to_thread(password_hash, password, salt)

    def now(self):
        return self.clock or datetime.now(timezone.utc).isoformat()

    def replace(self, data):
        self.data = data
        self.running = {}
        for task in tuple(self.tasks):
            task.cancel()

    def login(self, user, status):
        token = secrets.token_urlsafe(32)
        self.data["tokens"][token] = user["id"]
        return response(dict(user_id=user["id"], display_name=user["display_name"], token=token), status)

    async def authenticate(self, path, request):
        params = await body(request)
        if path == "/auth/signup":
            email, password, user = identity(params)
            user["hash"] = await self.hash(password)
            if email in self.data["users"]:
                raise Error(409, "email_taken")
            self.data["users"][email] = user
            return self.login(user, 201)
        email, password = field(params, "email"), field(params, "password")
        user = self.data["users"].get(email)
        if user:
            expected = user["hash"]
            actual = await self.hash(password, expected.split(":")[0])
            if self.data["users"].get(email) is user and hmac.compare_digest(expected, actual):
                return self.login(user, 200)
        raise Error(401, "unauthenticated")

    def snapshot(self):
        data = dict(self.data, dossiers={**self.data["dossiers"], **self.running})
        # Serialize while the event loop owns all mutable records. The checksum detects
        # damage to deeply nested historical evidence before it reaches the live state.
        checksum = hashlib.sha256(encode(data)).hexdigest()
        return dict(track="dossier", format_version=1, state=dict(data=data, checksum=checksum))

    async def control(self, path, request):
        if path == "/_test/export" and request.method == "GET":
            return response(self.snapshot())
        if request.method != "POST":
            raise Error(404, "not_found")
        params = await body(request)
        if path == "/_test/clock":
            value = field(params, "now")
            require(timestamp(value) >= timestamp(self.now()))
            self.clock = value
        elif path == "/_test/reset":
            clock = field(params, "now")
            timestamp(clock)
            data = fresh()
            members = typed(params.get("users", []), list)
            identities = [identity(typed(m, dict), fixture=True) for m in members]
            require(len({x[0] for x in identities}) == len(identities))
            require(len({x[2]["id"] for x in identities}) == len(identities))
            digests = await asyncio.gather(*(self.hash(pw) for _, pw, _ in identities))
            for (email, _, u), digest in zip(identities, digests):
                data["users"][email] = dict(u, hash=digest)
            self.replace(data)
            self.clock = clock
        elif path == "/_test/import":
            try:
                require(params.get("track") == "dossier" and type(params.get("format_version")) is int
                        and params["format_version"] == 1)
                state = params["state"]
                data = state["data"]
                require(hashlib.sha256(encode(data)).hexdigest() == state["checksum"])
                validate_data(data)
            except (KeyError, ValueError, TypeError, AttributeError, Error):
                raise Error()
            self.replace(data)
        else:
            raise Error(404, "not_found")
        return web.Response(status=204)

    def identify(self, request):
        parts = request.headers.get("Authorization", "").split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            uid = self.data["tokens"].get(parts[1])
            if uid is not None:
                return uid
        raise Error(401, "unauthenticated")

    def begin(self, key, at):
        d = self.data["dossiers"][key]
        self.running[key] = dict(d)
        d["state"] = "building"
        store = self.data

        def account(cost):
            if self.data is store:
                d["spent_units"] += cost

        async def finish():
            build = Build(key, self.router, lambda: self.data is store, account)
            try:
                await build.run()
            finally:
                if self.data is store:
                    d["state"] = "ready" if build.success else "failed"
                    if build.success:
                        d["fields"] = build.evidence.fields()
                        d["researched_at"] = at
                    store["history"].setdefault(key, []).append(dict(
                        at=at, calls=build.calls, pages=build.evidence.pages, research=build.research_answer))
                    self.running.pop(key, None)

        task = asyncio.create_task(finish())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def list_dossiers(self, request):
        q = request.query.get("q", "").casefold()
        limit = page_parameter(request.query, "limit", 50, 1, 200)
        offset = page_parameter(request.query, "offset", 0, 0)
        rows = []
        for key, d in sorted(self.data["dossiers"].items()):
            legal = d["fields"]["legal_name"]["value"]
            if q in key.casefold() or q in (legal or "").casefold():
                rows.append({**{k: v for k, v in d.items() if k != "fields"}, "legal_name": legal})
        return response(dict(dossiers=rows[offset:offset + limit], has_more=len(rows) > offset + limit))

    async def route(self, request):
        path = request.path
        method = request.method
        if path == "/health" and method == "GET":
            return response({"status": "ok"})
        if path.startswith("/_test/"):
            return await self.control(path, request)
        if method == "POST" and path in ("/auth/login", "/auth/signup"):
            return await self.authenticate(path, request)
        uid = self.identify(request)
        if path == "/dossiers" and method == "GET":
            return self.list_dossiers(request)
        create = path == "/dossiers" and method == "POST"
        refresh = path.startswith("/dossiers/") and path.endswith("/refresh") and method == "POST"
        if create or refresh:
            key = request.headers.get("Idempotency-Key", "")
            if not key:
                raise Error(400, "missing_idempotency_key")
            require(len(key) <= 255)
            params = await body(request) if create else {}
            # Reading the body yields to reset/import. Recheck the principal at commit.
            uid = self.identify(request)
            recognized = {"domain": params["domain"]} if create and "domain" in params else {}
            scope = encode([uid, request.rel_url.raw_path, key]).decode()
            previous = self.data["keys"].get(scope)
            if previous:
                if encode(previous["body"]) != encode(recognized):
                    raise Error(409, "idempotency_key_reuse")
                return response(previous["response"])
            normalized = domain(field(params, "domain") if create else path[len("/dossiers/"):-len("/refresh")])
            dossiers = self.data["dossiers"]
            new = normalized not in dossiers
            if new:
                if refresh:
                    raise Error(404, "not_found")
                dossiers[normalized] = dict(dossier_id=secrets.token_hex(16), domain=normalized,
                                            state="failed", researched_at=None, spent_units=0, fields=empty_fields())
            if new or (refresh and normalized not in self.running):
                self.begin(normalized, self.now())
            summary = {k: dossiers[normalized][k] for k in ("dossier_id", "domain", "state")}
            self.data["keys"][scope] = dict(body=recognized, response=summary)
            return response(summary, 202 if new or refresh else 200)
        if path.startswith("/dossiers/") and method == "GET":
            d = self.data["dossiers"].get(domain(path.removeprefix("/dossiers/")))
            if d:
                return response(d)
        raise Error(404, "not_found")


@web.middleware
async def errors(request, handler):
    try:
        return await handler(request)
    except Error as exc:
        return response({"error": {"code": exc.code, "message": exc.code.replace("_", " ")}}, exc.status)
    except web.HTTPException as exc:
        code = "not_found" if exc.status == 404 else "malformed_request"
        return response({"error": {"code": code, "message": exc.reason}}, exc.status)


async def application():
    app = web.Application(middlewares=[errors], client_max_size=512 * 1024**2)
    service = Service()
    app.router.add_route("*", "/{tail:.*}", service.route)
    return app


if __name__ == "__main__":
    web.run_app(application(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")), backlog=128, access_log=None)
