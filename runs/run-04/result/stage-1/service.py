"""Single-process ASGI service. State transitions do not yield within a transaction."""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import re

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
import uvicorn

from research import Build, make_router
from state import (
    ApiError, blank, canonical, check_password, display_name, domain_name, email_key, field,
    initial, invalid, malformed, new_id, now_system, password_hash, restore, snapshot, timestamp, valid_id,
)


class Store:
    def __init__(self):
        self.data = blank()
        self.clock = None
        self.active = {}
        self.router = None
        self.hash_slots = asyncio.Semaphore(4)

    def replace(self, data):
        for _, task in self.active.values():
            task.cancel()
        self.active = {}
        self.data = data

    def now(self):
        return self.clock or now_system()

    async def hashed(self, function, *args):
        async with self.hash_slots:
            return await asyncio.to_thread(function, *args)

    def view(self, domain):
        doc = self.data["dossiers"][domain]
        if domain not in self.active:
            return doc
        build, _ = self.active[domain]
        return {**doc, "state": "building", "spent_units": doc["spent_units"] + build.spent}

    def start(self, domain, at):
        if domain in self.active:
            return
        build = Build(domain, self.router)
        task = asyncio.create_task(self.finish(build, at, self.data))
        self.active[domain] = build, task

    async def finish(self, build, at, generation):
        try:
            async with asyncio.timeout(286):
                await build.run()
        except asyncio.CancelledError:
            return
        except TimeoutError:
            pass
        except Exception as exc:
            # Avoid logging provider details, which can include credentials or research text.
            logging.getLogger("dossier").error("Build interrupted (%s)", type(exc).__name__)
        if self.data is not generation:
            return
        doc = generation["dossiers"][build.domain]
        doc["spent_units"] += build.spent
        doc["state"] = "ready" if build.succeeded else "failed"
        if build.succeeded:
            doc["researched_at"] = at
            doc["fields"] = build.fields
        history = generation["builds"].setdefault(build.domain, [])
        history.append({"time": at, "calls": build.calls, "pages": build.pages, "claims": build.claims})
        del self.active[build.domain]


store = Store()


def json_response(status, value=None):
    if status == 204:
        return Response(status_code=204)
    return Response(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")),
                    status_code=status, media_type="application/json; charset=utf-8")


async def body_object(request):
    try:
        raw = (await request.body()).decode("utf-8")
        obj = json.loads(raw, parse_constant=lambda _: malformed())
    except (ValueError, RecursionError):
        malformed()
    if not isinstance(obj, dict):
        malformed()
    return obj


def authenticated(request):
    auth = request.headers.get("authorization", "")
    found = re.fullmatch(r"(?i:Bearer) ([^\s]+)", auth)
    uid = store.data["tokens"].get(found[1]) if found else None
    if uid is None:
        raise ApiError(401, "unauthenticated")
    return uid


def session(user):
    token = new_id("s_")
    store.data["tokens"][token] = user["id"]
    return {"user_id": user["id"], "display_name": user["display_name"], "token": token}


async def authenticate(request, signup):
    body = await body_object(request)
    email = email_key(field(body, "email"))
    password = field(body, "password")
    if signup:
        name = display_name(field(body, "display_name"))
        if len(password) < 8:
            invalid("Password must contain at least eight characters")
        hashed = await store.hashed(password_hash, password)
        if email in store.data["users"]:
            raise ApiError(409, "email_taken")
        user = {"id": new_id("u_"), "display_name": name, "password_hash": hashed}
        store.data["users"][email] = user
        return json_response(201, session(user))

    while True:
        user = store.data["users"].get(email)
        if user is None:
            raise ApiError(401, "unauthenticated")
        valid = await store.hashed(check_password, password, user["password_hash"])
        if store.data["users"].get(email) is not user:
            continue
        if not valid:
            raise ApiError(401, "unauthenticated")
        return json_response(200, session(user))


async def reset(body):
    at = field(body, "now")
    timestamp(at)
    users = field(body, "users", list) if "users" in body else []
    entries = []
    seen_emails, seen_ids = set(), set()
    for user in users:
        if not isinstance(user, dict):
            malformed()
        email = email_key(field(user, "email"))
        uid = field(user, "id")
        if email in seen_emails or not valid_id(uid) or uid in seen_ids:
            invalid("Invalid or duplicate fixture identity")
        seen_emails.add(email)
        seen_ids.add(uid)
        entries.append((email, uid, display_name(field(user, "display_name")), field(user, "password")))
    hashes = await asyncio.gather(*(store.hashed(password_hash, row[3]) for row in entries))
    data = blank()
    for (email, uid, name, _), hashed in zip(entries, hashes):
        data["users"][email] = {"id": uid, "display_name": name, "password_hash": hashed}
    store.replace(data)
    store.clock = at


def idempotency_key(request):
    key = request.headers.get("idempotency-key", "")
    if not key:
        raise ApiError(400, "missing_idempotency_key")
    if len(key) > 255:
        invalid("Idempotency key exceeds 255 characters")
    return key


def writes(request, uid, key, body, raw_domain, at):
    path = request.scope["raw_path"].decode("latin-1")
    identity = canonical([uid, "POST", path, key])
    replay = store.data["replays"].get(identity)
    if replay is not None:
        if replay["body"] != body:
            raise ApiError(409, "idempotency_key_reuse")
        return json_response(200, replay["response"])

    create = raw_domain is None
    domain = domain_name(field(body, "domain") if create else raw_domain)
    if create and domain not in store.data["dossiers"]:
        doc = initial(domain)
        store.data["dossiers"][domain] = doc
        store.start(domain, at)
        status = 202
    elif domain not in store.data["dossiers"]:
        raise ApiError(404, "not_found")
    elif create:
        status = 200
    else:
        store.start(domain, at)
        status = 202
    doc = store.view(domain)
    result = {k: doc[k] for k in ("dossier_id", "domain", "state")}
    store.data["replays"][identity] = {"body": body, "response": result}
    return json_response(status, result)


def decimal_param(raw, max_relevant):
    if not re.fullmatch(r"[0-9]+", raw):
        invalid("Expected a decimal integer")
    digits = raw.lstrip("0") or "0"
    if len(digits) > len(str(max_relevant)):
        return max_relevant + 1
    return int(digits)


def listing(request):
    query = request.query_params
    limit = decimal_param(query.get("limit", "50"), 200)
    if not 1 <= limit <= 200:
        invalid("Limit must be 1 to 200")
    all_docs = store.data["dossiers"]
    offset = decimal_param(query.get("offset", "0"), len(all_docs))
    q = query.get("q", "").casefold()
    matches = []
    for domain in sorted(all_docs):
        doc = store.view(domain)
        legal = doc["fields"]["legal_name"]["value"]
        if q in domain.casefold() or q in (legal or "").casefold():
            row = {k: doc[k] for k in ("dossier_id", "domain", "state", "researched_at", "spent_units")}
            matches.append({**row, "legal_name": legal})
    return json_response(200, {"dossiers": matches[offset:offset+limit], "has_more": offset+limit < len(matches)})


async def dispatch(request: Request):
    at = store.now()
    path = request.scope["path"]
    method = request.method
    if (method, path) == ("GET", "/health"):
        return json_response(200, {"status": "ok"})
    if (method, path) == ("GET", "/_test/export"):
        return json_response(200, snapshot(store.data))
    if method == "POST" and path in {"/_test/reset", "/_test/import", "/_test/clock"}:
        body = await body_object(request)
        if path == "/_test/reset":
            await reset(body)
        elif path == "/_test/import":
            store.replace(restore(body))
        else:
            now = field(body, "now")
            if timestamp(now) < timestamp(store.now()):
                invalid("Clock cannot move backwards")
            store.clock = now
        return json_response(204)
    if method == "POST" and path in {"/auth/signup", "/auth/login"}:
        return await authenticate(request, path == "/auth/signup")

    uid = authenticated(request)
    if path == "/dossiers" and method == "GET":
        return listing(request)
    if path == "/dossiers" and method == "POST":
        key = idempotency_key(request)
        obj = await body_object(request)
        uid = authenticated(request)
        body = {"domain": obj["domain"]} if "domain" in obj else {}
        return writes(request, uid, key, body, None, at)
    if path.startswith("/dossiers/"):
        raw = path[len("/dossiers/"):]
        if method == "POST" and raw.endswith("/refresh"):
            return writes(request, uid, idempotency_key(request), {}, raw[:-len("/refresh")], at)
        if method == "GET":
            domain = domain_name(raw)
            if domain not in store.data["dossiers"]:
                raise ApiError(404, "not_found")
            return json_response(200, store.view(domain))
    raise ApiError(404, "not_found")


async def endpoint(request):
    try:
        return await dispatch(request)
    except ApiError as exc:
        return json_response(exc.status, {"error": {"code": exc.code, "message": exc.message}})


async def unmatched(_request, _exception):
    return json_response(404, {"error": {"code": "not_found", "message": "Unknown endpoint"}})


@asynccontextmanager
async def lifespan(_app):
    store.router = make_router()
    try:
        yield
    finally:
        store.replace(blank())
        await store.router.aclose()


app = Starlette(routes=[Route("/{path:path}", endpoint, methods=["GET", "POST", "PUT", "PATCH", "DELETE",
                                                                 "OPTIONS", "HEAD", "TRACE"])],
                exception_handlers={404: unmatched, 405: unmatched}, lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
