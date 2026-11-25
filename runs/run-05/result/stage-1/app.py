"""Single event-loop ownership makes each state transition atomic."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hmac
import json
import re

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from research import Build, initialize, router
from state import Problem, Store, domain, fresh_dossier, new_user, password_hash, prop, require, timestamp, validate_email

store = Store()
hash_pool = ThreadPoolExecutor(max_workers=4)

class Json(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content):
        return json.dumps(content, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()

async def body(request):
    try:
        def invalid_constant(_):
            raise ValueError()
        obj = json.loads(await request.body(), parse_constant=invalid_constant)
        if type(obj) is not dict:
            raise ValueError()
        return obj
    except (ValueError, RecursionError):
        raise Problem(400, "malformed_request", "Expected a JSON object")

def seed(obj):
    fresh = Store()
    fresh.clock = timestamp(prop(obj, "now"))
    users = prop(obj, "users", list) if "users" in obj else []
    ids = set()
    for spec in users:
        if type(spec) is not dict:
            raise Problem(400, "malformed_request", "Expected a user object")
        user = new_user(spec, seeded=True)
        require(user["email"] not in fresh.users and user["id"] not in ids, "Duplicate fixture user")
        fresh.add_user(user)
        ids.add(user["id"])
    return fresh

def replace(fresh):
    global store
    for job in store.running.values():
        job.task.cancel()
    store = fresh

async def control(request, path):
    if path == "/health" and request.method == "GET":
        return Json({"status": "ok"})
    if path == "/_test/export" and request.method == "GET":
        return Json(store.export())
    if request.method != "POST":
        raise Problem(404, "not_found", "Unknown route")
    obj = await body(request)
    if path == "/_test/reset":
        fresh = await asyncio.get_running_loop().run_in_executor(hash_pool, seed, obj)
        replace(fresh)
    elif path == "/_test/import":
        fresh = Store.restore(obj)
        fresh.clock = store.clock
        replace(fresh)
    elif path == "/_test/clock":
        new_time = timestamp(prop(obj, "now"))
        require(new_time >= store.now(), "Clock cannot move backwards")
        store.clock = new_time
    else:
        raise Problem(404, "not_found", "Unknown route")
    return Response(status_code=204)

async def auth(request, signup):
    obj = await body(request)
    loop = asyncio.get_running_loop()
    if signup:
        user = await loop.run_in_executor(hash_pool, new_user, obj)
        store.add_user(user)
        return Json(store.session(user), 201)
    email, password = prop(obj, "email"), prop(obj, "password")
    validate_email(email)
    while user := store.users.get(email):
        encoded = user["hash"]
        hashed = await loop.run_in_executor(hash_pool, password_hash, password, encoded.split(":")[0])
        if store.users.get(email) is not user:
            continue
        if hmac.compare_digest(hashed, encoded):
            return Json(store.session(user))
        break
    raise Problem(401, "unauthenticated", "Invalid login")

def identify(request):
    match = re.fullmatch(r"Bearer ([^\s]+)", request.headers.get("authorization", ""), re.I)
    if not match or match[1] not in store.tokens:
        raise Problem(401, "unauthenticated", "A valid bearer token is required")
    return store.tokens[match[1]]

def pagination(request, key, default):
    value = request.query_params.get(key, str(default))
    require(re.fullmatch(r"[0-9]+", value), f"Invalid {key}")
    digits = value.lstrip("0")
    # All indices beyond the in-memory list's size yield the same empty page.
    number = int(digits[:20] or "0")
    require(key != "limit" or 1 <= number <= 200)
    return number

def listing(request):
    q = request.query_params.get("q", "").casefold()
    limit = pagination(request, "limit", 50)
    offset = pagination(request, "offset", 0)
    rows = []
    for name in sorted(store.dossiers):
        row = store.detail(name)
        row["legal_name"] = row.pop("fields")["legal_name"]["value"]
        if q in name.casefold() or q in (row["legal_name"] or "").casefold():
            rows.append(row)
    return Json({"dossiers": rows[offset:offset + limit], "has_more": len(rows) > offset + limit})

async def gather(target, job, name, when):
    try:
        await job.run()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        # Never include provider payloads, credentials or URLs in operational errors.
        print("Build interrupted by", type(exc).__name__, flush=True)
    if target is not store or target.running.get(name) is not job:
        return
    row = target.dossiers[name]
    row["spent_units"] += job.spent
    if job.succeeded:
        row.update(state="ready", fields=job.fields(), researched_at=when)
    else:
        row["state"] = "failed"
    target.history.setdefault(name, []).append(job.record(when))
    del target.running[name]

async def write(request, path, refresh):
    # A refresh ignores even a malformed body.
    obj = {} if refresh else await body(request)
    uid = identify(request)
    key = request.headers.get("idempotency-key")
    if not key:
        raise Problem(400, "missing_idempotency_key", "Supply an Idempotency-Key")
    require(len(key) <= 255)
    fingerprint = {"domain": obj["domain"]} if "domain" in obj else {}
    scope = (uid, path, key)
    if old := store.replays.get(scope):
        if old["body"] != fingerprint:
            raise Problem(409, "idempotency_key_reuse", "Key already used with a different body")
        return Json(old["response"])
    name = domain(path[len("/dossiers/"):-len("/refresh")]) if refresh else domain(prop(obj, "domain"))
    exists = name in store.dossiers
    if refresh and not exists:
        raise Problem(404, "not_found", "Unknown dossier")
    if not exists:
        store.dossiers[name] = fresh_dossier(name)
    start = not exists or refresh
    if start and name not in store.running:
        job = Build(name)
        store.running[name] = job
        job.task = asyncio.create_task(gather(store, job, name, store.now().isoformat()))
    detail = store.detail(name)
    response = {k: detail[k] for k in ("dossier_id", "domain", "state")}
    store.replays[scope] = {"scope": list(scope), "body": fingerprint, "response": response}
    return Json(response, 202 if start else 200)

async def dispatch(request):
    try:
        path = request.scope["path"]
        if path == "/health" or path.startswith("/_test/"):
            return await control(request, path)
        if request.method == "POST" and path in ("/auth/signup", "/auth/login"):
            return await auth(request, path.endswith("/signup"))
        identify(request)
        if path == "/dossiers":
            if request.method == "GET":
                return listing(request)
            if request.method == "POST":
                if not request.headers.get("idempotency-key"):
                    raise Problem(400, "missing_idempotency_key", "Supply an Idempotency-Key")
                return await write(request, path, False)
        if path.startswith("/dossiers/"):
            if request.method == "POST" and path.endswith("/refresh"):
                return await write(request, path, True)
            if request.method == "GET":
                return Json(store.detail(domain(path[len("/dossiers/"):])))
        raise Problem(404, "not_found", "Unknown route")
    except Problem as exc:
        return Json({"error": {"code": exc.code, "message": exc.message}}, exc.status)

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield
    await router().aclose()

app = Starlette(lifespan=lifespan, routes=[Route("/{path:path}", dispatch, methods=["GET","POST","PATCH","PUT","DELETE","OPTIONS","HEAD","TRACE"])])
