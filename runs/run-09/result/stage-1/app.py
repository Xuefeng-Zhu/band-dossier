"""Single-event-loop HTTP service. Every state transition is synchronous."""
import asyncio
import copy
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from aiohttp import web
from evidence import PHRASES, unknown
from research import Build, initialize

def reject(status, code, message=None):
    raise Problem(status, code, message or code.replace("_", " "))

class Problem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message

def require(ok):
    if not ok:
        reject(422, "validation_failed")

def required(row, key, typ=str):
    require(key in row)
    if type(row[key]) is not typ:
        reject(400, "malformed_request")
    return row[key]

def strict_json(text):
    def invalid(value):
        raise ValueError("Invalid JSON number")
    def finite(value):
        n = float(value)
        if not math.isfinite(n):
            invalid(value)
        return n
    return json.loads(text, parse_constant=invalid, parse_float=finite)

async def body(req):
    try:
        obj = strict_json(await req.text())
    except (ValueError, LookupError, RecursionError):
        reject(400, "malformed_request")
    if type(obj) is not dict:
        reject(400, "malformed_request")
    return obj

def normalize(raw):
    d = raw.strip().lower().removesuffix(".").removeprefix("www.")
    require(len(d) <= 253 and "." in d and all(re.fullmatch("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", l) for l in d.split(".")))
    return d

RFC3339 = re.compile(r"(\d{4}-\d\d-\d\d[Tt]\d\d:\d\d:\d\d)(?:\.(\d+))?([Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)")

def time_order(raw):
    match = RFC3339.fullmatch(raw) if isinstance(raw, str) else None
    require(match)
    date, fraction, offset = match.groups()
    try:
        second = datetime.fromisoformat(date.upper() + offset.upper().replace("Z", "+00:00"))
    except (OverflowError, ValueError):
        reject(422, "validation_failed")
    utc_seconds = second.toordinal() * 86400 + second.hour * 3600 + second.minute * 60 + second.second - int(second.utcoffset().total_seconds())
    # Lexical comparison of fractional digits, after trimming trailing zeroes,
    # preserves arbitrary RFC 3339 precision even across differing offsets.
    return utc_seconds, (fraction or "").rstrip("0")

def email_field(obj):
    email = required(obj, "email")
    require(re.fullmatch(r"[^@\s]+@[^@\s]+", email))
    return email

def passwd(password, salt):
    return hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt), n=8192, r=8, p=1, dklen=32).hex()

def new_user(obj, seeded):
    email = email_field(obj)
    password = required(obj, "password")
    display_name = required(obj, "display_name")
    uid = required(obj, "id") if seeded else secrets.token_hex(16)
    require(0 < len(uid) <= 64 and len(password) >= 8 and 0 < len(display_name) <= 100)
    salt = secrets.token_hex(16)
    return {"email": email, "id": uid, "display_name": display_name, "salt": salt, "hash": passwd(password,salt)}

def empty():
    return {"users": {}, "tokens": {}, "dossiers": {}, "receipts": {}}

def response(value, status=200):
    return web.json_response(value, status=status, content_type="application/json")

def identity(req):
    match = re.fullmatch(r"Bearer ([^\s]+)", req.headers.get("Authorization", ""), re.I)
    uid = match and data["tokens"].get(match[1])
    if not uid:
        reject(401, "unauthenticated")
    return uid

def brief(d):
    return {k: d[k] for k in ("dossier_id", "domain", "state")}

def detail(d):
    return {**brief(d), **{k:d[k] for k in ("researched_at", "spent_units", "fields")}}

def now():
    return clock or datetime.now(timezone.utc).isoformat()

data = empty()
clock = None
running = {}
router = None

async def build_dossier(d, started):
    old_cost = d["spent_units"]
    def charge(amount):
        d["spent_units"] += amount
    work = Build(d["domain"], router, charge)
    try:
        async with asyncio.timeout(285):
            await work.collect()
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        pass
    except Exception as exc:
        print("Build interrupted:", type(exc).__name__, file=sys.stderr, flush=True)
    finally:
        if data["dossiers"].get(d["domain"]) is d:
            if work.success:
                d["fields"] = work.evidence.fields()
                d["researched_at"] = started
            d["state"] = "ready" if work.success else "failed"
            d["history"].append({"at": started, "outcome": d["state"], "cost": d["spent_units"] - old_cost,
                                 "calls": work.log, "pages": work.evidence.pages, "candidates": work.evidence.candidates})
            running.pop(d["domain"], None)

def start(d):
    domain = d["domain"]
    if domain in running:
        return
    previous = (d["state"], d["spent_units"])
    d["state"] = "building"
    task = asyncio.create_task(build_dossier(d, now()))
    running[domain] = (task, previous)

def replace(new_data):
    global data
    for task,_ in running.values():
        task.cancel()
    running.clear()
    data = new_data

def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)

def checksum(snapshot):
    return hashlib.sha256(canonical(snapshot).encode()).hexdigest()

def exported():
    snapshot = copy.deepcopy(data)
    for domain,(_, previous) in running.items():
        d = snapshot["dossiers"][domain]
        d["state"], d["spent_units"] = previous
    return {"track":"dossier", "format_version":1, "state":{"records":snapshot, "checksum":checksum(snapshot)}}

def imported(obj):
    # The digest covers the complete portable record, including opaque build evidence.
    require(obj.get("track") == "dossier" and type(obj.get("format_version")) is int and obj["format_version"] == 1)
    state = obj.get("state")
    require(isinstance(state,dict) and isinstance(state.get("records"),dict))
    records = state["records"]
    require(state.get("checksum") == checksum(records))
    require(records.keys() == empty().keys() and all(isinstance(v,dict) for v in records.values()))
    try:
        ids = set()
        for email, u in records["users"].items():
            require(u["email"] == email and isinstance(u["id"], str) and 0 < len(u["id"]) <= 64 and u["id"] not in ids)
            require(re.fullmatch("[a-f0-9]{32}",u["salt"]) and re.fullmatch("[a-f0-9]{64}",u["hash"]) and isinstance(u["display_name"], str))
            ids.add(u["id"])
        require(all(uid in ids for uid in records["tokens"].values()))
        for k, d in records["dossiers"].items():
            require(normalize(k) == k == d["domain"] and d["state"] in ("ready","failed") and isinstance(d["dossier_id"],str))
            require(type(d["spent_units"]) is int and d["spent_units"] >= 0 and isinstance(d["history"], list))
            require(set(d["fields"]) == set(PHRASES))
            for field in d["fields"].values():
                require(isinstance(field["citations"],list) and field["status"] == ("unknown" if field["value"] is None else "known"))
                require(bool(field["citations"]) == (field["value"] is not None))
            if d["researched_at"] is not None:
                time_order(d["researched_at"])
        for key,row in records["receipts"].items():
            uid, method, path, idem = json.loads(key)
            require(uid in ids and method == "POST" and isinstance(path,str) and isinstance(idem,str))
            require(isinstance(row["body"],dict) and row["response"]["domain"] in records["dossiers"])
    except (TypeError, ValueError, KeyError, IndexError, AttributeError):
        reject(422, "validation_failed")
    return records

def signed(u,status):
    token = secrets.token_urlsafe(32)
    data["tokens"][token] = u["id"]
    return response({"user_id":u["id"], "display_name":u["display_name"], "token":token},status)

async def auth(req):
    obj = await body(req)
    if req.path == "/auth/signup":
        user = new_user(obj, False)
        if user["email"] in data["users"]:
            reject(409,"email_taken")
        data["users"][user["email"]] = user
        return signed(user,201)
    email, pwd = email_field(obj), required(obj, "password")
    user = data["users"].get(email)
    if not user or not hmac.compare_digest(passwd(pwd,user["salt"]),user["hash"]):
        reject(401,"unauthenticated")
    return signed(user,200)

async def control(req):
    global clock
    if req.path == "/_test/export":
        return response(exported())
    obj = await body(req)
    if req.path == "/_test/import":
        replace(imported(obj))
    elif req.path == "/_test/clock":
        t = required(obj, "now").upper().replace("Z", "+00:00")
        require(time_order(t) >= time_order(now()))
        clock = t
    else:
        t = required(obj, "now").upper().replace("Z", "+00:00")
        time_order(t)
        new_data = empty()
        users = obj.get("users", [])
        if type(users) is not list:
            reject(400, "malformed_request")
        ids = set()
        for row in users:
            if not isinstance(row, dict):
                reject(400,"malformed_request")
            user = new_user(row, True)
            require(user["email"] not in new_data["users"] and user["id"] not in ids)
            new_data["users"][user["email"]] = user
            ids.add(user["id"])
        replace(new_data)
        clock = t
    return web.Response(status=204)

def find(domain):
    if domain not in data["dossiers"]:
        reject(404,"not_found")
    return data["dossiers"][domain]

async def write(req):
    identity(req)
    key = req.headers.get("Idempotency-Key","")
    if not key:
        reject(400, "missing_idempotency_key")
    require(len(key) <= 255)
    create = req.path == "/dossiers"
    obj = await body(req) if create else {}
    uid = identity(req)
    effective = {k:obj[k] for k in ("domain",) if k in obj} if create else {}
    key = canonical([uid, req.method, req.rel_url.raw_path, key])
    existing = data["receipts"].get(key)
    if existing:
        if canonical(effective) != canonical(existing["body"]):
            reject(409, "idempotency_key_reuse")
        return response(existing["response"])
    status = 202
    if create:
        domain = normalize(required(obj,"domain"))
        d = data["dossiers"].get(domain)
        if d:
            status = 200
        else:
            d = {"domain":domain,"dossier_id":secrets.token_hex(16),"state":"failed","spent_units":0,
                 "researched_at":None,"fields":unknown(),"history":[]}
            data["dossiers"][domain] = d
            start(d)
    else:
        d = find(normalize(req.match_info["domain"]))
        start(d)
    result = brief(d)
    data["receipts"][key] = {"body":effective,"response":result}
    return response(result,status)

def number(req, name, default):
    value = req.query.get(name, str(default))
    require(re.fullmatch("[0-9]+",value))
    # No physical list could exceed this offset. Do not overflow on long inputs.
    return int((value.lstrip("0") or "0")[:20])

async def read(req):
    identity(req)
    if "domain" in req.match_info:
        return response(detail(find(normalize(req.match_info["domain"]))))
    limit, offset = number(req,"limit",50), number(req,"offset",0)
    require(1 <= limit <= 200)
    q = req.query.get("q","").casefold()
    selected = []
    for domain,d in sorted(data["dossiers"].items()):
        legal = d["fields"]["legal_name"]["value"]
        if q in domain.casefold() or q in (legal or "").casefold():
            selected.append({**brief(d), "legal_name": legal, "researched_at": d["researched_at"], "spent_units": d["spent_units"]})
    return response({"dossiers": selected[offset:offset+limit], "has_more": len(selected)>offset+limit})

@web.middleware
async def errors(req, handler):
    try:
        return await handler(req)
    except Problem as exc:
        return response({"error":{"code":exc.code,"message":exc.message}},exc.status)
    except web.HTTPException:
        return response({"error":{"code":"not_found","message":"No such endpoint"}},404)

async def init():
    global router
    router = initialize()
    app = web.Application(middlewares=[errors], client_max_size=1024**3)
    async def health(req):
        return response({"status":"ok"})
    app.router.add_get("/health",health)
    for name in ["reset","clock","import"]:
        app.router.add_post("/_test/"+name,control)
    app.router.add_get("/_test/export",control)
    for name in ["signup","login"]:
        app.router.add_post("/auth/"+name,auth)
    app.router.add_post("/dossiers",write)
    app.router.add_post("/dossiers/{domain:.+}/refresh",write)
    app.router.add_get("/dossiers",read)
    app.router.add_get("/dossiers/{domain:.+}",read)
    return app

if __name__ == "__main__":
    web.run_app(init(),host="0.0.0.0",port=int(os.getenv("PORT","8080")),access_log=None)
