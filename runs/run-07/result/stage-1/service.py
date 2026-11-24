import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote

import uvicorn
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from research import Research, make_router
from state import (ActiveBuild, Database, Problem, Store, member, new_account, new_dossier,
                   normalize, parse_time, require, uid, user_input)


db = Database()


@asynccontextmanager
async def lifespan(app):
    # Bound password-hash memory as well as CPU use on the two-core deployment.
    pool = ThreadPoolExecutor(max_workers=4)
    asyncio.get_running_loop().set_default_executor(pool)
    app.state.router = make_router()
    try:
        yield
    finally:
        tasks = [b.task for b in db.state.active.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await app.state.router.aclose()
        pool.shutdown(wait=False)


def json_response(status, value):
    return Response(json.dumps(value, ensure_ascii=True, separators=(",", ":")),
                    status, media_type="application/json; charset=utf-8")


def json_object(raw):
    def invalid(value):
        raise ValueError(value)
    try:
        body = json.loads(raw, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise Problem("malformed_request", "Invalid JSON")
    if not isinstance(body, dict):
        raise Problem("malformed_request", "Expected a JSON object")
    return body


def authenticate(request):
    match = re.fullmatch(r"Bearer ([^\s]+)", request.headers.get("authorization", ""), re.I)
    user = db.state.tokens.get(match[1]) if match else None
    if user is None:
        raise Problem("unauthenticated", "A valid bearer token is required")
    return user


async def finish_build(store, domain, build, router):
    research = Research(domain, router, build)
    try:
        await research.run()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        # Preserve collected evidence and settled charges if a provider response is unusable.
        research.record_issue(type(exc).__name__)
    if store is not db.state or store.active.get(domain) is not build:
        return
    doc = store.dossiers[domain]
    doc["spent_units"] += build.spent
    doc["state"] = "ready" if research.succeeded else "failed"
    if research.succeeded:
        doc.update(fields=research.fields(), researched_at=build.started)
    store.history.setdefault(domain, []).append(research.record)
    del store.active[domain]


def start_build(store, domain, router):
    build = ActiveBuild(db.now().isoformat())
    store.active[domain] = build
    build.task = asyncio.create_task(finish_build(store, domain, build, router))


def summary(doc):
    return {k: doc[k] for k in ("dossier_id", "domain", "state")}


def write_dossier(request, user, raw, path, raw_path):
    key = request.headers.get("idempotency-key")
    if not key:
        raise Problem("missing_idempotency_key", "Provide an Idempotency-Key")
    require(len(key) <= 255, "Idempotency-Key is too long")
    creating = path == "/dossiers"
    body = json_object(raw) if creating else {}
    recognized = {"domain": body["domain"]} if "domain" in body else {}
    index = (user, "POST", raw_path, key)
    store = db.state
    if index in store.replays:
        original, response = store.replays[index]
        if recognized != original:
            raise Problem("idempotency_key_reuse", "This key was used with a different request body")
        return 200, response
    domain = normalize(member(body, "domain") if creating else path[len("/dossiers/"):-len("/refresh")])
    if domain not in store.dossiers:
        if not creating:
            raise Problem("not_found", "Dossier not found")
        store.dossiers[domain] = new_dossier(domain)
    elif creating:
        response = summary(store.view(domain))
        store.replays[index] = (recognized, response)
        return 200, response
    if domain not in store.active:
        start_build(store, domain, request.app.state.router)
    response = summary(store.view(domain))
    store.replays[index] = (recognized, response)
    return 202, response


def list_dossiers(query):
    q = query.get("q", "").casefold()
    vals = {}
    for name, default in (("offset", "0"), ("limit", "50")):
        raw = query.get(name, default)
        require(re.fullmatch("[0-9]+", raw), f"Expected decimal digits for {name}")
        digits = raw.lstrip("0")
        vals[name] = int(digits[:20] or "0")
    offset, limit = vals["offset"], vals["limit"]
    require(1 <= limit <= 200, "Limit must be between 1 and 200")
    docs = []
    matched = 0
    for domain in sorted(db.state.dossiers):
        doc = db.state.view(domain)
        name = doc["fields"]["legal_name"]["value"]
        if q not in domain.casefold() and q not in (name or "").casefold():
            continue
        if matched >= offset:
            if len(docs) == limit:
                return {"dossiers": docs, "has_more": True}
            docs.append({**summary(doc), "legal_name": name, "researched_at": doc["researched_at"],
                         "spent_units": doc["spent_units"]})
        matched += 1
    return {"dossiers": docs, "has_more": False}


async def dispatch(request, raw):
    method = request.method
    raw_path = request.scope["raw_path"].decode("ascii", "surrogateescape")
    path = unquote(raw_path)
    if (method, path) == ("GET", "/health"):
        return 200, {"status": "ok"}
    if (method, path) == ("POST", "/_test/reset"):
        await db.reset(json_object(raw))
        return 204, None
    if (method, path) == ("POST", "/_test/clock"):
        stamp = parse_time(member(json_object(raw), "now"))
        require(stamp >= db.now(), "Clock cannot move backwards")
        db.clock = stamp
        return 204, None
    if (method, path) == ("GET", "/_test/export"):
        return 200, db.state.snapshot()
    if (method, path) == ("POST", "/_test/import"):
        db.replace(Store.from_snapshot(json_object(raw)))
        return 204, None
    if (method, path) == ("POST", "/auth/signup"):
        email, password, display = user_input(json_object(raw))
        if email in db.state.users:
            raise Problem("email_taken", "Email already registered")
        user = await new_account(uid("u_"), email, password, display)
        if email in db.state.users:
            raise Problem("email_taken", "Email already registered")
        db.state.users[email] = user
        return 201, db.state.session(user)
    if (method, path) == ("POST", "/auth/login"):
        return 200, await db.login(json_object(raw))
    user = authenticate(request)
    if method == "GET" and path == "/dossiers":
        return 200, list_dossiers(request.query_params)
    if method == "GET" and path.startswith("/dossiers/"):
        domain = normalize(path[len("/dossiers/"):])
        if domain in db.state.dossiers:
            return 200, db.state.view(domain)
    if method == "POST" and (path == "/dossiers" or path.startswith("/dossiers/") and path.endswith("/refresh")):
        return write_dossier(request, user, raw, path, raw_path)
    raise Problem("not_found", "Resource not found")


async def endpoint(request: Request):
    try:
        status, value = await dispatch(request, await request.body())
    except Problem as exc:
        return json_response(exc.status, {"error": {"code": exc.code, "message": exc.message}})
    return Response(status_code=204) if status == 204 else json_response(status, value)


async def http_error(request, exc):
    return json_response(exc.status_code, {"error": {"code": "not_found", "message": "Resource or method unavailable"}})


app = Starlette(routes=[Route("/{path:path}", endpoint, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])],
                exception_handlers={HTTPException: http_error}, lifespan=lifespan)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
