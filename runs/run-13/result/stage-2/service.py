"""Ephemeral, single-event-loop HTTP service for company dossiers."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

from aiohttp import web

from evidence import PHRASES, unknowns, resolve
from research import Build, Providers

CODES = {"malformed_request": 400, "missing_idempotency_key": 400, "unauthenticated": 401,
         "not_found": 404, "idempotency_key_reuse": 409, "email_taken": 409, "validation_failed": 422}


class Problem(Exception):
    def __init__(self, code):
        self.code = code


def require(condition, code="validation_failed"):
    if not condition:
        raise Problem(code)


def field(body, name, kind=str):
    require(name in body)
    value = body[name]
    require(isinstance(value, kind), "malformed_request")
    return value


def json_response(body, status=200):
    return web.json_response(body, status=status, dumps=lambda o: json.dumps(o, separators=(",", ":")))


def reject_constant(value):
    raise ValueError("Invalid JSON number")


def parse_integer(digits):
    # The decoder has already validated the JSON number grammar. Preserve a
    # large integer as numeric input so its field determines its validity.
    try:
        return int(digits)
    except ValueError:
        return Decimal(digits)


async def object_body(request, *, importing=False):
    try:
        value = json.loads(await request.read(), parse_constant=reject_constant, parse_int=parse_integer)
    except (ValueError, RecursionError):
        raise Problem("malformed_request")
    require(isinstance(value, dict), "validation_failed" if importing else "malformed_request")
    return value


@web.middleware
async def errors(request, handler):
    try:
        return await handler(request)
    except Problem as e:
        code = e.code
    except web.HTTPException as e:
        code = "malformed_request" if e.status in (400, 413) else "not_found"
    return json_response({"error": {"code": code, "message": code.replace("_", " ")}}, CODES[code])


LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
HOST = re.compile(rf"{LABEL}(?:\.{LABEL})+")
TIME = re.compile(r"(\d{4}-\d\d-\d\d[Tt]\d\d:\d\d:\d\d)(\.\d+)?([Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)", re.ASCII)


def normal(raw):
    domain = raw.strip().lower().removesuffix(".").removeprefix("www.")
    require(len(domain) <= 253 and HOST.fullmatch(domain))
    return domain


def instant(raw):
    found = TIME.fullmatch(raw)
    require(found)
    try:
        dt = datetime.fromisoformat(found[1] + found[3].upper().replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise Problem("validation_failed")
    return dt, Decimal(found[2] or "0")


def password_hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt),
                          n=2**14, r=8, p=1, dklen=32).hex()


def email_address(body):
    email = field(body, "email")
    require(re.fullmatch(r"[^\s@]+@[^\s@]+", email))
    return email.casefold()


async def account(body, seeded):
    email = email_address(body)
    password = field(body, "password")
    name = field(body, "display_name")
    require(1 <= len(name) <= 100 and len(password) >= 8)
    uid = field(body, "id") if seeded else secrets.token_hex(16)
    require(0 < len(uid) <= 64)
    salt = secrets.token_hex(16)
    digest = await asyncio.to_thread(password_hash, password, salt)
    return email, {"id": uid, "name": name, "hash": digest, "salt": salt}


def empty():
    return {"users": {}, "tokens": {}, "dossiers": {}, "replays": {}, "history": {}}


class Store:
    def __init__(self):
        self.data = empty()
        self.clock = None
        self.running = {}
        self.providers = Providers()

    def time(self):
        return self.clock or datetime.now(timezone.utc).isoformat()

    def replace(self, data):
        for _, task in self.running.values():
            task.cancel()
        self.running.clear()
        self.data = data

    def start(self, domain, started):
        build = Build(domain, self.providers, started)
        data = self.data

        async def run():
            result = await build.run()
            if data is not self.data:
                return
            dossier = data["dossiers"][domain]
            dossier["state"] = "ready" if build.success else "failed"
            if build.success:
                dossier.update(fields=result, researched_at=started)
            dossier["spent_units"] += build.units
            data["history"].setdefault(domain, []).append(
                {"started": started, "outcome": dossier["state"], "calls": build.calls, "pages": build.pages})
            self.running.pop(domain, None)

        self.running[domain] = build, asyncio.create_task(run())

    def view(self, domain):
        require(domain in self.data["dossiers"], "not_found")
        doc = self.data["dossiers"][domain]
        if domain in self.running:
            return dict(doc, state="building", spent_units=doc["spent_units"] + self.running[domain][0].units)
        return doc

    def user(self, request):
        parts = request.headers.get("Authorization", "").split()
        require(len(parts) == 2 and parts[0].lower() == "bearer", "unauthenticated")
        uid = self.data["tokens"].get(parts[1])
        require(uid is not None, "unauthenticated")
        return uid

    def login_response(self, user, status):
        token = secrets.token_urlsafe(32)
        self.data["tokens"][token] = user["id"]
        return json_response({"user_id": user["id"], "display_name": user["name"], "token": token}, status)


store = None


async def health(request):
    return json_response({"status": "ok"})


async def reset(request):
    body = await object_body(request)
    now = field(body, "now")
    instant(now)
    users = body.get("users", [])
    require(isinstance(users, list), "malformed_request")
    replacement = empty()
    ids = set()
    for entry in users:
        require(isinstance(entry, dict), "malformed_request")
        email, user = await account(entry, True)
        require(email not in replacement["users"] and user["id"] not in ids)
        replacement["users"][email] = user
        ids.add(user["id"])
    store.replace(replacement)
    store.clock = now
    return web.Response(status=204)


async def clock(request):
    now = field(await object_body(request), "now")
    require(instant(now) >= instant(store.time()))
    store.clock = now
    return web.Response(status=204)


def digest(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


async def export(request):
    # Only committed dossier versions are stored here. The running build's
    # receipts and fields stay private to that build until its atomic commit.
    data = store.data
    return json_response({"track": "dossier", "format_version": 1,
                          "state": {"data": data, "checksum": digest(data)}})


def valid_snapshot(data):
    require(isinstance(data, dict) and all(isinstance(data.get(k), dict) for k in empty()))
    uids = set()
    for user in data["users"].values():
        require(isinstance(user, dict) and isinstance(user.get("name"), str))
        require(isinstance(user.get("id"), str) and 0 < len(user["id"]) <= 64 and user["id"] not in uids)
        for name, size in (("hash", 64), ("salt", 32)):
            require(isinstance(user.get(name), str) and re.fullmatch("[a-f0-9]{%d}" % size, user[name]))
        uids.add(user["id"])
    require(all(isinstance(uid, str) and uid in uids for uid in data["tokens"].values()))
    for domain, doc in data["dossiers"].items():
        require(isinstance(doc, dict) and doc.get("domain") == domain and HOST.fullmatch(domain))
        require(doc.get("state") in ("failed", "ready") and isinstance(doc.get("dossier_id"), str))
        require(type(doc.get("spent_units")) is int and doc["spent_units"] >= 0)
        require("researched_at" in doc and (doc["researched_at"] is None or isinstance(doc["researched_at"], str)))
        if doc["researched_at"]:
            instant(doc["researched_at"])
        require(isinstance(doc.get("fields"), dict) and set(doc["fields"]) == set(PHRASES))
        for answer in doc["fields"].values():
            require(isinstance(answer, dict) and {"value", "status", "citations"} <= answer.keys())
            require(isinstance(answer["citations"], list))
            require((answer["status"] == "unknown" and answer["value"] is None and not answer["citations"])
                    or (answer["status"] in ("known", "contested") and answer["value"] is not None and answer["citations"]))
    for replay in data["replays"].values():
        require(isinstance(replay, dict) and "body" in replay and isinstance(replay.get("response"), dict))
    for domain, builds in data["history"].items():
        require(domain in data["dossiers"] and isinstance(builds, list))


def upgrade(data):
    for domain, dossier in data["dossiers"].items():
        fields = dossier["fields"]
        if all("candidates" in answer for answer in fields.values()):
            continue
        when = dossier["researched_at"]
        pages = []
        for build in reversed(data["history"].get(domain, [])):
            if build["started"] == when and (build["pages"] or any(
                    "outcome" not in c or (c["cost"] and c["outcome"] == "ExtractFailedError")
                    for c in build["calls"])):
                pages = list(build["pages"])
                break
        for name, answer in fields.items():
            pages.extend({"url": c["url"], "provider": c["provider"], "text": c["excerpt"],
                          "method": "citation", "claim": [name, answer["value"]]} for c in answer["citations"])
        dossier["fields"] = resolve(domain, when, pages, imported=True)


async def restore(request):
    body = await object_body(request, importing=True)
    require(body.get("track") == "dossier" and type(body.get("format_version")) is int and body["format_version"] == 1)
    state = body.get("state")
    require(isinstance(state, dict) and isinstance(state.get("data"), dict))
    data = state["data"]
    try:
        checksum = digest(data)
    except (ValueError, TypeError, RecursionError):
        # Valid JSON can represent numbers outside the snapshot encoder's
        # range. They cannot occur in an export produced by this service.
        raise Problem("validation_failed")
    require(state.get("checksum") == checksum)
    try:
        valid_snapshot(data)
        upgrade(data)
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError, RecursionError):
        raise Problem("validation_failed")
    store.replace(data)
    return web.Response(status=204)


async def signup(request):
    email, user = await account(await object_body(request), False)
    require(email not in store.data["users"], "email_taken")
    store.data["users"][email] = user
    return store.login_response(user, 201)


async def login(request):
    body = await object_body(request)
    email = email_address(body)
    password = field(body, "password")
    user = store.data["users"].get(email)
    require(user is not None, "unauthenticated")
    actual = await asyncio.to_thread(password_hash, password, user["salt"])
    require(hmac.compare_digest(actual, user["hash"]) and store.data["users"].get(email) == user, "unauthenticated")
    return store.login_response(user, 200)


def integer(query, key, default):
    value = query.get(key, str(default))
    require(re.fullmatch("[0-9]+", value))
    digits = value.lstrip("0")
    # A larger offset always points beyond this process's last dossier.
    return int(digits[:20] or "0")


async def listing(request):
    store.user(request)
    limit, offset = integer(request.query, "limit", 50), integer(request.query, "offset", 0)
    require(1 <= limit <= 200)
    term = request.query.get("q", "").casefold()
    rows = []
    for domain in sorted(store.data["dossiers"]):
        d = store.view(domain)
        name = d["fields"]["legal_name"]["value"]
        if term in domain or term in (name or "").casefold():
            rows.append({k: v for k, v in d.items() if k != "fields"} | {"legal_name": name})
    return json_response({"dossiers": rows[offset:offset+limit], "has_more": len(rows) > offset + limit})


UI = Path(__file__).with_name("ui")


async def screen(request):
    if "domain" in request.match_info:
        normal(request.match_info["domain"])
    return web.FileResponse(UI / "index.html", headers={"Cache-Control": "no-cache", "Vary": "Accept"})


async def read(request):
    if "text/html" in request.headers.get("Accept", "").lower():
        return await screen(request)
    store.user(request)
    return json_response(store.view(normal(request.match_info["domain"])))


async def write(request):
    started = store.time()
    uid = store.user(request)
    key = request.headers.get("Idempotency-Key", "")
    require(key, "missing_idempotency_key")
    require(len(key) <= 255)
    refreshing = "domain" in request.match_info
    body = {} if refreshing else await object_body(request)
    # Reading the request body may suspend across a reset.
    uid = store.user(request)
    replay_key = json.dumps([uid, request.method, request.rel_url.raw_path, key])
    identity = {k: body[k] for k in ("domain",) if k in body}
    saved = store.data["replays"].get(replay_key)
    if saved:
        require(saved["body"] == identity, "idempotency_key_reuse")
        return json_response(saved["response"])
    domain = normal(request.match_info["domain"] if refreshing else field(body, "domain"))
    docs = store.data["dossiers"]
    status = 200
    if refreshing:
        require(domain in docs, "not_found")
        if domain not in store.running:
            store.start(domain, started)
        status = 202
    elif domain not in docs:
        docs[domain] = {"dossier_id": secrets.token_hex(16), "domain": domain, "state": "failed",
                        "spent_units": 0, "researched_at": None, "fields": unknowns()}
        store.start(domain, started)
        status = 202
    response = {k: v for k, v in store.view(domain).items() if k in ("dossier_id", "domain", "state")}
    store.data["replays"][replay_key] = {"body": identity, "response": response}
    return json_response(response, status)


async def app():
    global store
    store = Store()
    application = web.Application(middlewares=[errors], client_max_size=256 * 1024 * 1024)
    application.add_routes([
        web.get("/", screen), web.get("/signup", screen), web.get("/login", screen), web.get("/contested", screen),
        web.get("/dossiers/{domain}/evidence", screen), web.static("/assets", UI),
        web.get("/health", health), web.post("/_test/reset", reset), web.post("/_test/clock", clock),
        web.get("/_test/export", export), web.post("/_test/import", restore),
        web.post("/auth/signup", signup), web.post("/auth/login", login),
        web.get("/dossiers", listing), web.post("/dossiers", write),
        web.post("/dossiers/{domain:.+}/refresh", write), web.get("/dossiers/{domain:.+}", read)])

    async def shutdown(_):
        store.replace(empty())
        await store.providers.close()
    application.on_shutdown.append(shutdown)
    return application


if __name__ == "__main__":
    web.run_app(app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")), access_log=None, backlog=256)
