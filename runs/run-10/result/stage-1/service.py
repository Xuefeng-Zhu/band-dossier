"""Single event-loop HTTP service. Every state commit is synchronous on that loop."""
import asyncio
import base64
import gzip
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import unquote
from aiohttp import web

from evidence import FIELDS, unknown
from research import Build

class Fault(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message

def require(condition, message="Invalid request"):
    if not condition:
        raise Fault(422,"validation_failed",message)

def typed(value, kind):
    if type(value) is not kind:
        raise Fault(400,"malformed_request","Unexpected JSON type")
    return value

def field(obj,key,kind=str):
    require(key in obj, f"Missing {key}")
    return typed(obj[key],kind)

def timestamp(value):
    """Order the UTC second and its exact decimal fraction independently."""
    parts = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]+))?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value)
    require(parts, "Timestamp requires an explicit offset")
    wall_second, fraction, offset = parts.groups()
    try:
        second = datetime.fromisoformat(wall_second + offset.upper())
    except ValueError:
        raise Fault(422,"validation_failed","Invalid timestamp")
    # Removing trailing zeros makes equivalent fractions compare equal. With
    # a common decimal point, ordinary digit-string order is then exact.
    return second, (fraction or "").rstrip("0")

def domain(value):
    normalized = value.strip().lower().removesuffix(".").removeprefix("www.")
    labels = normalized.split(".")
    require(len(normalized)<=253 and len(labels)>=2 and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",label) for label in labels),"Invalid domain")
    return normalized

def email_address(value):
    require(re.fullmatch(r"[^@\s]+@[^@\s]+",value),"Invalid email")
    return value.casefold()

def opaque():
    return secrets.token_urlsafe(24)

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256",password.encode("utf-8","surrogatepass"),bytes.fromhex(salt),120000)
    return salt + "." + digest.hex()

def compact_json(obj):
    return json.dumps(obj,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)

async def body(request):
    def bad_constant(_):
        raise ValueError
    try:
        data = json.loads(await request.read(), parse_constant=bad_constant)
    except (ValueError,UnicodeError,RecursionError):
        raise Fault(400,"malformed_request","Invalid JSON body")
    return typed(data,dict)

def new_state():
    return {"users":{}, "tokens":{}, "dossiers":{}, "keys":{}, "history":{}}

state = new_state()
clock = None
running = {}

def now():
    return clock or datetime.now(timezone.utc).isoformat()

def replace(data):
    global state,running
    for _, task in running.values():
        task.cancel()
    state, running = data, {}

def authorized(request):
    match = re.fullmatch(r"Bearer ([^\s]+)",request.headers.get("Authorization",""),re.I)
    uid = state["tokens"].get(match[1]) if match else None
    if uid is None:
        raise Fault(401,"unauthenticated","Valid bearer token required")
    return uid

def token_for(user):
    token = opaque()
    state["tokens"][token] = user["id"]
    return {"user_id":user["id"],"display_name":user["display_name"],"token":token}

def missing():
    raise Fault(404,"not_found","Resource does not exist")

def detail(d):
    item = dict(d)
    if d["domain"] in running:
        build,_ = running[d["domain"]]
        item.update(state="building",spent_units=d["spent_units"]+build.spent)
    return item

def summary(d):
    return {key:d[key] for key in ("dossier_id","domain","state")}

async def finish(store, item, build):
    try:
        fields = await build.run()
    except asyncio.CancelledError:
        return
    except Exception:
        # A malformed provider payload does not discard previously supported evidence.
        logging.warning("Dossier build ended early", exc_info=False)
        fields = build.evidence.fields()
    if store is not state:
        return
    item["spent_units"] += build.spent
    item["state"] = "ready" if build.success else "failed"
    if build.success:
        item.update(fields=fields,researched_at=build.at)
    archived = gzip.compress(compact_json(build.archive()).encode(),compresslevel=1)
    store["history"].setdefault(build.domain,[]).append(base64.b64encode(archived).decode())
    running.pop(build.domain)

def start(d):
    if d["domain"] not in running:
        build = Build(d["domain"],now())
        running[d["domain"]] = (build,asyncio.create_task(finish(state,d,build)))

def paging(query,key,default):
    digits = query.get(key,str(default))
    require(re.fullmatch("[0-9]+",digits),"Expected decimal digits")
    stripped = digits.lstrip("0")
    value = int(stripped[:18] or "0")
    require(key != "limit" or 1<=value<=200,"Limit outside range")
    return value

def listing(query):
    limit = paging(query,"limit",50)
    offset = paging(query,"offset",0)
    needle = query.get("q","").casefold()
    selected = []
    for name,d in sorted(state["dossiers"].items()):
        legal = d["fields"]["legal_name"]["value"]
        if needle not in name and needle not in (legal or "").casefold():
            continue
        d = detail(d)
        selected.append({**summary(d),"legal_name":legal,"researched_at":d["researched_at"],"spent_units":d["spent_units"]})
    return {"dossiers":selected[offset:offset+limit],"has_more":offset+limit<len(selected)}

def write(uid,path,key,data,raw_domain):
    if not key:
        raise Fault(400,"missing_idempotency_key","Idempotency-Key required")
    require(len(key)<=255,"Idempotency key too long")
    scope = compact_json([uid,path,key])
    request_body = {k:data[k] for k in ("domain",) if k in data} if raw_domain is None else {}
    record = state["keys"].get(scope)
    if record:
        if record["body"] != request_body:
            raise Fault(409,"idempotency_key_reuse","Key already has a different request")
        return 200,record["response"]
    name = domain(field(data,"domain") if raw_domain is None else raw_domain)
    d = state["dossiers"].get(name)
    status = 202
    if raw_domain is None and d is not None:
        status = 200
    else:
        if d is None:
            if raw_domain is not None:
                missing()
            d = {"dossier_id":opaque(),"domain":name,"state":"failed","fields":unknown(),
                 "researched_at":None,"spent_units":0}
            state["dossiers"][name] = d
        start(d)
    response = summary(detail(d))
    state["keys"][scope] = {"body":request_body,"response":response}
    return status,response

async def reset(data):
    global clock
    time = field(data,"now").upper()
    timestamp(time)
    rows = typed(data.get("users",[]),list)
    fresh = new_state()
    ids = set()
    for row in rows:
        typed(row,dict)
        email = email_address(field(row,"email"))
        uid = field(row,"id")
        require(uid not in ids and 0<len(uid)<=64 and email not in fresh["users"],"Duplicate or invalid seed user")
        ids.add(uid)
        name = field(row,"display_name")
        fresh["users"][email] = {"id":uid,"display_name":name,
                                 "hash":await asyncio.to_thread(password_hash,field(row,"password"))}
    replace(fresh)
    clock = time

async def auth(data,signup):
    email = email_address(field(data,"email"))
    password = field(data,"password")
    if signup:
        display = field(data,"display_name")
        require(1<=len(display)<=100 and len(password)>=8,"Invalid password or display name")
        hashed = await asyncio.to_thread(password_hash,password)
        if email in state["users"]:
            raise Fault(409,"email_taken","Email already registered")
        user = {"id":opaque(),"display_name":display,"hash":hashed}
        state["users"][email] = user
        return 201, token_for(user)
    while True:
        user = state["users"].get(email)
        if not user:
            raise Fault(401,"unauthenticated","Invalid credentials")
        checked = await asyncio.to_thread(password_hash,password,user["hash"].split(".")[0])
        if state["users"].get(email) is not user:
            continue
        if not hmac.compare_digest(user["hash"],checked):
            raise Fault(401,"unauthenticated","Invalid credentials")
        return 200,token_for(user)

def checksum(data):
    return hashlib.sha256(compact_json(data).encode()).hexdigest()

def valid_state(data):
    if type(data) is not dict or set(data)!=set(new_state()) or not all(type(v) is dict for v in data.values()):
        return False
    try:
        ids = set()
        for email,u in data["users"].items():
            if email_address(email)!=email or not isinstance(u["id"],str) or not 0<len(u["id"])<=64 or u["id"] in ids:
                return False
            if not isinstance(u["display_name"],str) or not re.fullmatch(r"[0-9a-f]{32}\.[0-9a-f]{64}",u["hash"]):
                return False
            ids.add(u["id"])
        if any(uid not in ids for uid in data["tokens"].values()):
            return False
        for name,d in data["dossiers"].items():
            if domain(name)!=name or d["domain"]!=name or d["state"] not in ("ready","failed") or set(d["fields"])!=set(FIELDS):
                return False
            if not isinstance(d["dossier_id"],str) or not 0<len(d["dossier_id"])<=64 or type(d["spent_units"]) is not int or d["spent_units"]<0:
                return False
            if d["researched_at"] is not None:
                timestamp(d["researched_at"])
            for k,f in d["fields"].items():
                if f["value"] is None:
                    if f!=unknown()[k]:
                        return False
                elif (f["status"]!="known" or type(f["citations"]) is not list or not f["citations"] or
                      type(f["value"]) is not (int if k in ("funding_total","founded_year") else str)):
                    return False
                for c in f["citations"]:
                    if not isinstance(c["url"],str) or not 1<=len(c["excerpt"])<=500 or c["provider"] not in ("nimble","tavily"):
                        return False
        for scope,rec in data["keys"].items():
            uid,path,key = json.loads(scope)
            result = rec["response"]
            if uid not in ids or not isinstance(key,str) or not 1<=len(key)<=255 or not isinstance(path,str) or not isinstance(rec["body"],dict):
                return False
            if result["dossier_id"]!=data["dossiers"][result["domain"]]["dossier_id"] or result["state"] not in ("ready","failed","building"):
                return False
        return all(name in data["dossiers"] and type(builds) is list and all(type(b) is str for b in builds)
                   for name,builds in data["history"].items())
    except (KeyError,ValueError,TypeError,AttributeError,Fault):
        return False

async def dispatch(request):
    global clock
    path = request.rel_url.raw_path
    method = request.method
    if method=="GET" and path=="/health":
        return 200,{"status":"ok"}
    if path.startswith("/_test/"):
        if path=="/_test/export" and method=="GET":
            return 200,{"track":"dossier","format_version":1,"state":{"data":state,"sha256":checksum(state)}}
        if method!="POST":
            missing()
        data = await body(request)
        if path=="/_test/reset":
            await reset(data)
        elif path=="/_test/clock":
            new = field(data,"now").upper()
            require(timestamp(new)>=timestamp(now()),"Clock cannot move backwards")
            clock = new
        elif path=="/_test/import":
            envelope = data.get("state")
            require(data.get("track")=="dossier" and type(data.get("format_version")) is int and data["format_version"]==1
                    and type(envelope) is dict and "data" in envelope,"Invalid export envelope")
            restored = envelope["data"]
            require(valid_state(restored) and checksum(restored)==envelope.get("sha256"),"Invalid exported state")
            replace(restored)
        else:
            missing()
        return 204,None
    if method=="POST" and path in ("/auth/login","/auth/signup"):
        return await auth(await body(request),path.endswith("signup"))
    uid = authorized(request)
    if path=="/dossiers":
        if method=="GET":
            return 200,listing(request.query)
        if method=="POST":
            data = await body(request)
            uid = authorized(request)
            return write(uid,path,request.headers.get("Idempotency-Key"),data,None)
    if path.startswith("/dossiers/"):
        tail = path[len("/dossiers/"):]
        if method=="POST" and tail.endswith("/refresh"):
            return write(uid,path,request.headers.get("Idempotency-Key"),{},unquote(tail[:-len("/refresh")]))
        if method=="GET":
            name = domain(unquote(tail))
            if name not in state["dossiers"]:
                missing()
            return 200,detail(state["dossiers"][name])
    missing()

async def handle(request):
    try:
        status,data = await dispatch(request)
    except Fault as exc:
        status,data = exc.status,{"error":{"code":exc.code,"message":exc.message}}
    if status==204:
        return web.Response(status=204)
    return web.Response(status=status,text=compact_json(data),content_type="application/json",charset="utf-8")

if __name__ == "__main__":
    app = web.Application(client_max_size=512*1024**2)
    app.router.add_route("*","/{path:.*}",handle)
    web.run_app(app,host="0.0.0.0",port=int(os.getenv("PORT","8080")),backlog=256,access_log=None)
