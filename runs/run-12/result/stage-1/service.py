"""Single event-loop HTTP service. Each state transition runs without an await."""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import unquote

from aiohttp import web

from evidence import unknown_fields
from gather import Build, Providers


class Problem(Exception):
    def __init__(self, status=422, code="validation_failed", message="Invalid request"):
        self.status, self.code, self.message = status, code, message


def require(ok):
    if not ok:
        raise Problem()


def typed(obj, key, kind=str):
    if key not in obj:
        raise Problem(message=f"Missing {key}")
    if type(obj[key]) is not kind:
        raise Problem(400, "malformed_request", f"Invalid type for {key}")
    return obj[key]


def invalid_constant(_):
    raise ValueError("Non-JSON constant")


async def body(req):
    try:
        obj = json.loads(await req.read(), parse_constant=invalid_constant)
    except (ValueError, RecursionError):
        obj = None
    if not isinstance(obj, dict):
        raise Problem(400, "malformed_request", "Expected a JSON object")
    return obj


def norm(value):
    host = value.strip().lower().removesuffix(".").removeprefix("www.")
    labels = host.split(".")
    require(len(host) <= 253 and len(labels) >= 2 and
            all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in labels))
    return host


def instant(value):
    require(isinstance(value, str) and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value))
    try:
        return datetime.fromisoformat(value.upper())
    except ValueError:
        raise Problem() from None


def digest(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt), n=8192, r=8, p=1)
    return salt + ":" + key.hex()


def account_data(obj):
    email, pwd, name = (typed(obj, k) for k in ("email", "password", "display_name"))
    require(re.fullmatch(r"[^@\s]+@[^@\s]+", email) and len(pwd) >= 8 and 0 < len(name) <= 100)
    return email, pwd, name


def blank():
    return {"users": {}, "tokens": {}, "dossiers": {}, "replays": {}, "history": {}}


def compact(row):
    return {k: row[k] for k in ("dossier_id", "domain", "state")}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class Service:
    def __init__(self):
        self.state = blank()
        self.clock = None
        self.active = {}
        self.providers = Providers()

    def now(self):
        return self.clock or datetime.now(timezone.utc).isoformat()

    def replace(self, state):
        for task, _ in self.active.values():
            task.cancel()
        self.active.clear()
        self.state = state

    def user(self, req):
        scheme, _, token = req.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or token not in self.state["tokens"]:
            raise Problem(401, "unauthenticated", "Valid bearer token required")
        return self.state["tokens"][token]

    def session(self, record, status):
        uid = record["id"]
        token = secrets.token_urlsafe(32)
        self.state["tokens"][token] = uid
        return web.json_response({"user_id": uid, "display_name": record["name"], "token": token}, status=status)

    async def auth(self, req, path):
        obj = await body(req)
        if path == "/auth/signup":
            email, pwd, name = account_data(obj)
            hashed = await asyncio.to_thread(digest, pwd)
            if email in self.state["users"]:
                raise Problem(409, "email_taken", "Email already registered")
            record = {"id": secrets.token_hex(16), "name": name, "hash": hashed}
            self.state["users"][email] = record
            return self.session(record, 201)
        email, pwd = typed(obj, "email"), typed(obj, "password")
        require(re.fullmatch(r"[^@\s]+@[^@\s]+", email))
        record = self.state["users"].get(email)
        if record:
            stored = record["hash"]
            check = await asyncio.to_thread(digest, pwd, stored.split(":")[0])
            if self.state["users"].get(email) == record and hmac.compare_digest(check, stored):
                return self.session(record, 200)
        raise Problem(401, "unauthenticated", "Invalid login")

    async def reset(self, obj):
        state = blank()
        now = typed(obj, "now")
        instant(now)
        users = obj.get("users", [])
        if not isinstance(users, list):
            raise Problem(400, "malformed_request", "Expected users array")
        ids = set()
        for usr in users:
            if not isinstance(usr, dict):
                raise Problem(400, "malformed_request", "Expected account object")
            email, pwd, name = account_data(usr)
            uid = typed(usr, "id")
            require(0 < len(uid) <= 64 and uid not in ids and email not in state["users"])
            ids.add(uid)
            state["users"][email] = {"id": uid, "name": name, "hash": await asyncio.to_thread(digest, pwd)}
        self.replace(state)
        self.clock = now

    def snapshot(self):
        # The committed rows always hold their previous completed state during research.
        data = self.state
        return {"track": "dossier", "format_version": 1,
                "state": {"data": data, "sha256": hashlib.sha256(canonical(data).encode()).hexdigest()}}

    def restore(self, obj):
        require(obj.get("track") == "dossier" and type(obj.get("format_version")) is int and obj["format_version"] == 1)
        package = obj.get("state")
        require(isinstance(package, dict))
        data = package.get("data")
        require(isinstance(data, dict) and data.keys() == blank().keys() and all(isinstance(v, dict) for v in data.values()))
        require(package.get("sha256") == hashlib.sha256(canonical(data).encode()).hexdigest())
        validate_state(data)
        self.replace(data)

    def projection(self, domain):
        row = self.state["dossiers"][domain]
        if domain in self.active:
            build = self.active[domain][1]
            return {**row, "state": "building", "spent_units": row["spent_units"] + build.spent}
        return row

    def start(self, domain):
        if domain in self.active:
            return
        row = self.state["dossiers"][domain]
        build = Build(domain, self.providers)
        when = self.now()

        async def run():
            try:
                async with asyncio.timeout(285):
                    await build.gather()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print("Build ended with", type(exc).__name__, flush=True)
            if self.active.get(domain, (None, None))[1] is not build:
                return
            row["state"] = "ready" if build.succeeded else "failed"
            row["spent_units"] += build.spent
            if build.succeeded:
                row["fields"] = build.fields()
                row["researched_at"] = when
            self.state["history"].setdefault(domain, []).append({
                "time": when, "state": row["state"], "calls": build.calls, "sources": build.sources})
            self.active.pop(domain)

        self.active[domain] = (asyncio.create_task(run()), build)

    async def write(self, req, raw_path, raw_domain):
        self.user(req)
        key = req.headers.get("Idempotency-Key", "")
        if not key:
            raise Problem(400, "missing_idempotency_key", "Idempotency-Key is required")
        require(len(key) <= 255)
        create = raw_domain is None
        obj = await body(req) if create else {}
        uid = self.user(req)
        request_body = {k: obj[k] for k in ("domain",) if k in obj}
        scope = canonical([uid, "POST", raw_path, key])
        replay = self.state["replays"].get(scope)
        if replay:
            if replay["body"] != request_body:
                raise Problem(409, "idempotency_key_reuse", "Request body has changed")
            return web.json_response(replay["result"])
        domain = norm(typed(obj, "domain") if create else raw_domain)
        rows = self.state["dossiers"]
        status = 202
        if domain not in rows:
            if not create:
                raise Problem(404, "not_found", "Unknown dossier")
            rows[domain] = {"domain": domain, "dossier_id": secrets.token_hex(16), "state": "failed",
                            "researched_at": None, "spent_units": 0, "fields": unknown_fields()}
            self.start(domain)
        elif create:
            status = 200
        else:
            self.start(domain)
        result = compact(self.projection(domain))
        self.state["replays"][scope] = {"body": request_body, "result": result}
        return web.json_response(result, status=status)

    def listing(self, query):
        def number(key, default, lo, hi=None):
            raw = query.get(key, default)
            require(re.fullmatch(r"[0-9]+", raw))
            value = int((raw.lstrip("0") or "0")[:20])
            require(value >= lo and (hi is None or value <= hi))
            return value
        limit, offset = number("limit", "50", 1, 200), number("offset", "0", 0)
        needle = query.get("q", "").casefold()
        rows = []
        for domain in sorted(self.state["dossiers"]):
            row = self.projection(domain)
            name = row["fields"]["legal_name"]["value"]
            if needle in domain or needle in (name or "").casefold():
                rows.append({**compact(row), "legal_name": name, "spent_units": row["spent_units"],
                             "researched_at": row["researched_at"]})
        return web.json_response({"dossiers": rows[offset:offset+limit], "has_more": offset+limit < len(rows)})

    async def handle(self, req):
        raw_path = req.raw_path.partition("?")[0]
        path = unquote(raw_path)
        verb = req.method
        try:
            if path == "/health" and verb == "GET":
                return web.json_response({"status": "ok"})
            if path == "/_test/export" and verb == "GET":
                return web.json_response(self.snapshot())
            if path in {"/_test/reset", "/_test/clock", "/_test/import"} and verb == "POST":
                obj = await body(req)
                if path == "/_test/reset":
                    await self.reset(obj)
                elif path == "/_test/clock":
                    new = typed(obj, "now")
                    require(instant(new) >= instant(self.now()))
                    self.clock = new
                else:
                    self.restore(obj)
                return web.Response(status=204)
            if path in {"/auth/login", "/auth/signup"} and verb == "POST":
                return await self.auth(req, path)
            self.user(req)
            if path == "/dossiers":
                if verb == "POST":
                    return await self.write(req, raw_path, None)
                if verb == "GET":
                    return self.listing(req.query)
            if path.startswith("/dossiers/"):
                tail = path[len("/dossiers/"):]
                if verb == "POST" and tail.endswith("/refresh"):
                    return await self.write(req, raw_path, tail[:-8])
                if verb == "GET":
                    domain = norm(tail)
                    if domain in self.state["dossiers"]:
                        return web.json_response(self.projection(domain))
            raise Problem(404, "not_found", "Resource not found")
        except Problem as exc:
            return web.json_response({"error": {"code": exc.code, "message": exc.message}}, status=exc.status)


def validate_state(data):
    try:
        ids = set()
        for email, user in data["users"].items():
            require(isinstance(user["id"], str) and 0 < len(user["id"]) <= 64 and user["id"] not in ids)
            require(isinstance(user["name"], str) and 0 < len(user["name"]) <= 100 and re.fullmatch(r"[^@\s]+@[^@\s]+", email))
            require(re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{128}", user["hash"]))
            ids.add(user["id"])
        require(all(uid in ids for uid in data["tokens"].values()))
        for domain, row in data["dossiers"].items():
            # Normalisation removes only one prefix per request.
            require(isinstance(domain, str) and row["domain"] == domain and row["state"] in ("ready", "failed"))
            require(type(row["spent_units"]) is int and row["spent_units"] >= 0)
            require(isinstance(row["dossier_id"], str) and 0 < len(row["dossier_id"]) <= 64)
            if row["researched_at"] is not None:
                instant(row["researched_at"])
            require(row["fields"].keys() == unknown_fields().keys())
            for f in row["fields"].values():
                require(f == {"value": None, "status": "unknown", "citations": []} or
                        (f["value"] is not None and f["status"] == "known" and isinstance(f["citations"], list) and f["citations"]))
        for scope, replay in data["replays"].items():
            uid, method, path, key = json.loads(scope)
            require(uid in ids and method == "POST" and isinstance(path, str) and 0 < len(key) <= 255)
            require(isinstance(replay["body"], dict) and replay["result"]["domain"] in data["dossiers"])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise Problem() from None


if __name__ == "__main__":
    service = Service()
    app = web.Application(client_max_size=0)
    app.router.add_route("*", "/{path:.*}", service.handle)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=None)
