"""Single-process HTTP API. All state transitions run on one asyncio loop."""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from evidence import PHRASES, excerpts, unknown_fields, values
from research import Build

class ApiError(Exception):
    def __init__(self, status, code):
        self.status = status
        self.code = code


def require(condition, status=422, code="validation_failed"):
    if not condition:
        raise ApiError(status, code)


def get(obj, field, kind=str):
    require(field in obj)
    value = obj[field]
    require(type(value) is kind, 400, "malformed_request")
    return value


def leap_second_dates():
    # The base image ships IANA tzdata. Work in UTC so an insertion can
    # be recognized at its local equivalent on either side of midnight.
    instants = set()
    for line in Path("/usr/share/zoneinfo/leapseconds").read_text().splitlines():
        parts = line.split()
        if parts[:1] == ["Leap"] and parts[5] == "+":
            day = datetime.strptime(" ".join(parts[1:4]), "%Y %b %d")
            instants.add(day.toordinal() * 86400 + 86399)
    return instants


LEAP_SECONDS = leap_second_dates()


@dataclass(frozen=True, order=True)
class Instant:
    utc_second: int
    leap: bool
    fraction: str
    wire: str = field(compare=False)


def timestamp(s):
    match = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]+))?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", s)
    require(match)
    whole, fraction, offset = match.groups(default="")
    offset = "+00:00" if offset.upper() == "Z" else offset
    leap = whole.endswith(":60")
    parseable = whole[:-2] + "59" if leap else whole
    try:
        date = datetime.fromisoformat(parseable.upper() + offset)
    except ValueError:
        raise ApiError(422, "validation_failed")
    local_second = date.toordinal() * 86400 + date.hour * 3600 + date.minute * 60 + date.second
    utc_second = local_second - int(date.utcoffset().total_seconds())
    require(not leap or utc_second in LEAP_SECONDS)
    # Digits after the decimal point sort lexically once trailing zeroes are
    # removed. Keep the original fraction separately for the wire timestamp.
    wire = whole.upper() + ("." + fraction if fraction else "") + offset
    return Instant(utc_second, leap, fraction.rstrip("0"), wire)


def hostname(name):
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    return len(name) <= 253 and re.fullmatch(label + "(?:\\." + label + ")+", name)


def normalized(s):
    name = s.strip().lower().removesuffix(".").removeprefix("www.")
    require(hostname(name))
    return name


def valid_email(s):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+", s))


def ident(s):
    return isinstance(s, str) and 1 <= len(s) <= 64


def hash_password(password, salt):
    return hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


hash_slots = asyncio.Semaphore(4)


async def password_digest(password, salt):
    async with hash_slots:
        return await asyncio.to_thread(hash_password, password, salt)


async def account(user_id, name, password):
    salt = secrets.token_hex(16)
    return {"id": user_id, "display_name": name, "salt": salt, "digest": await password_digest(password, salt)}


def empty_state():
    return {"users": {}, "tokens": {}, "dossiers": {}, "replays": {}, "history": {}}


state = empty_state()
clock = None
active = {}


def now():
    return clock or timestamp(datetime.now(timezone.utc).isoformat())


def replace(new_state):
    global state
    for _, task in active.values():
        task.cancel()
    active.clear()
    state = new_state


def auth(req):
    parts = req.headers.get("Authorization", "").split()
    require(len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] in state["tokens"], 401, "unauthenticated")
    return state["tokens"][parts[1]]


def session(user):
    token = secrets.token_urlsafe(32)
    state["tokens"][token] = user["id"]
    return {"user_id": user["id"], "display_name": user["display_name"], "token": token}


async def body(req):
    try:
        raw = await req.read()
        obj = json.loads(raw, parse_constant=lambda s: (_ for _ in ()).throw(ValueError()))
    except (ValueError, RecursionError, UnicodeError):
        raise ApiError(400, "malformed_request")
    require(type(obj) is dict, 400, "malformed_request")
    return obj


def summary(d):
    return {key: d[key] for key in ("dossier_id", "domain", "state")}


def view(d):
    result = d.copy()
    if running := active.get(d["domain"]):
        result["state"] = "building"
        result["spent_units"] += running[0].spent
    return result


async def run_build(build, snapshot):
    try:
        async with asyncio.timeout(290):
            await build.gather()
    except asyncio.CancelledError:
        return
    except Exception as err:
        # Exceptions may include credentials or provider response bodies.
        print("Build stopped:", type(err).__name__, flush=True)
    if snapshot is not state:
        return
    d = state["dossiers"][build.domain]
    d["state"] = "ready" if build.succeeded else "failed"
    if build.succeeded:
        d["researched_at"] = build.timestamp
        d["fields"] = build.evidence.fields
    d["spent_units"] += build.spent
    state["history"].setdefault(build.domain, []).append({"time": build.timestamp, "calls": build.calls,
                                                       "sources": build.sources})
    del active[build.domain]


def start(d, t):
    if d["domain"] not in active:
        build = Build(d["domain"], t)
        active[d["domain"]] = (build, asyncio.create_task(run_build(build, state)))


def query_number(req, key, default):
    raw = req.query.get(key, str(default))
    require(re.fullmatch("[0-9]+", raw))
    significant = raw.lstrip("0")
    if len(significant) > 20:
        return 10**20
    return int(significant or "0")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def envelope():
    # Serialize while on the event loop. Dossiers in state always represent
    # their last completed build. The running build lives exclusively in active.
    return {"track": "dossier", "format_version": 1, "state": state}


def validate_fields(dossier, builds):
    fields = dossier["fields"]
    require(set(fields) == set(PHRASES))
    # A failed refresh retains the previous successful fields. Only evidence
    # from the corresponding build time can establish their provenance.
    sources = {}
    for build in builds:
        if build["time"] == dossier["researched_at"]:
            for source in build["sources"]:
                sources.setdefault((source["provider"], source["url"]), []).append(source)
    for field, item in fields.items():
        value = item["value"]
        if value is None:
            require(item == unknown_fields()[field])
            continue
        require(type(value) is (int if field in ("funding_total", "founded_year") else str))
        require(item["status"] == "known" and isinstance(item["citations"], list) and item["citations"])
        for citation in item["citations"]:
            quote = citation["excerpt"]
            require(isinstance(quote, str) and 1 <= len(quote) <= 500)
            require(values(dossier["domain"], quote).get(field) == value)
            matching = sources.get((citation["provider"], citation["url"]), [])
            require(any((source["claim"] is None or source["claim"] == [field, value])
                        and quote in excerpts(source["text"], source["claim"]) for source in matching))


def validate_state(obj):
    require(obj.get("track") == "dossier" and type(obj.get("format_version")) is int and obj["format_version"] == 1)
    s = obj.get("state")
    try:
        require(isinstance(s, dict) and all(isinstance(s[k], dict) for k in empty_state()))
        ids = set()
        for email, u in s["users"].items():
            require(valid_email(email) and ident(u["id"]) and u["id"] not in ids and isinstance(u["display_name"], str))
            require(re.fullmatch("[a-f0-9]{32}", u["salt"]) and re.fullmatch("[a-f0-9]{128}", u["digest"]))
            ids.add(u["id"])
        require(all(ident(k) and v in ids for k, v in s["tokens"].items()))
        dossier_ids = set()
        for name, d in s["dossiers"].items():
            require(d["domain"] == name and hostname(name) and ident(d["dossier_id"]) and d["dossier_id"] not in dossier_ids)
            dossier_ids.add(d["dossier_id"])
            require(d["state"] in ("ready", "failed") and type(d["spent_units"]) is int and d["spent_units"] >= 0)
            if d["researched_at"] is not None:
                timestamp(d["researched_at"])
            require(d["state"] != "ready" or d["researched_at"] is not None)
            validate_fields(d, s["history"].get(name, []))
        for encoded, replay in s["replays"].items():
            uid, path, key = json.loads(encoded)
            require(uid in ids and isinstance(path, str) and isinstance(key, str) and 1 <= len(key) <= 255)
            require(isinstance(replay["body"], dict) and replay["response"]["dossier_id"] in dossier_ids)
            require(replay["response"]["domain"] in s["dossiers"] and replay["response"]["state"] in ("building", "ready", "failed"))
        for name, builds in s["history"].items():
            require(name in s["dossiers"] and isinstance(builds, list))
            for b in builds:
                timestamp(b["time"])
                require(isinstance(b["calls"], list) and isinstance(b["sources"], list))
                for source in b["sources"]:
                    require(source["provider"] in ("nimble", "tavily") and isinstance(source["url"], str)
                            and isinstance(source["text"], str))
                    claim = source["claim"]
                    require(claim is None or (isinstance(claim, list) and len(claim) == 2 and claim[0] in PHRASES))
                require(all(type(c["units"]) is int and 0 <= c["units"] <= 25 for c in b["calls"]))
                require(sum(c["units"] for c in b["calls"]) <= 80)
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError):
        raise ApiError(422, "validation_failed")
    return s


async def handle(req):
    global clock
    path = req.path
    method = req.method
    received = now().wire
    if method == "GET" and path == "/health":
        return 200, {"status": "ok"}
    if path.startswith("/_test/"):
        if method == "GET" and path == "/_test/export":
            return 200, envelope()
        if method == "POST" and path in ("/_test/reset", "/_test/clock", "/_test/import"):
            obj = await body(req)
            if path == "/_test/import":
                replace(validate_state(obj))
            elif path == "/_test/clock":
                new_time = timestamp(get(obj, "now"))
                require(new_time >= now())
                clock = new_time
            else:
                new_time = timestamp(get(obj, "now"))
                fresh = empty_state()
                users = get(obj, "users", list) if "users" in obj else []
                ids = set()
                for u in users:
                    require(isinstance(u, dict), 400, "malformed_request")
                    uid, email, password, name = (get(u, k) for k in ("id", "email", "password", "display_name"))
                    require(ident(uid) and uid not in ids and valid_email(email) and email not in fresh["users"])
                    ids.add(uid)
                    fresh["users"][email] = await account(uid, name, password)
                replace(fresh)
                clock = new_time
            return 204, None
    if method == "POST" and path in ("/auth/signup", "/auth/login"):
        obj = await body(req)
        email, password = get(obj, "email"), get(obj, "password")
        require(valid_email(email))
        if path == "/auth/signup":
            name = get(obj, "display_name")
            require(len(password) >= 8 and 1 <= len(name) <= 100)
            user = await account(secrets.token_hex(16), name, password)
            require(email not in state["users"], 409, "email_taken")
            state["users"][email] = user
            return 201, session(user)
        user = state["users"].get(email)
        require(user is not None, 401, "unauthenticated")
        digest = await password_digest(password, user["salt"])
        require(state["users"].get(email) is user and hmac.compare_digest(digest, user["digest"]), 401, "unauthenticated")
        return 200, session(user)

    uid = auth(req)
    if method == "GET" and path == "/dossiers":
        q = req.query.get("q", "").casefold()
        limit, offset = query_number(req, "limit", 50), query_number(req, "offset", 0)
        require(1 <= limit <= 200)
        rows = []
        for domain in sorted(state["dossiers"]):
            d = view(state["dossiers"][domain])
            legal = d["fields"]["legal_name"]["value"]
            if q in domain.casefold() or q in (legal or "").casefold():
                rows.append({**summary(d), "researched_at": d["researched_at"], "spent_units": d["spent_units"], "legal_name": legal})
        return 200, {"dossiers": rows[offset:offset+limit], "has_more": offset+limit < len(rows)}

    if method == "GET" and path.startswith("/dossiers/"):
        name = normalized(path[len("/dossiers/"):])
        require(name in state["dossiers"], 404, "not_found")
        return 200, view(state["dossiers"][name])

    refresh = path.startswith("/dossiers/") and path.endswith("/refresh")
    if method == "POST" and (path == "/dossiers" or refresh):
        key = req.headers.get("Idempotency-Key", "")
        require(key, 400, "missing_idempotency_key")
        require(len(key) <= 255)
        recognized = {}
        if not refresh:
            obj = await body(req)
            if "domain" in obj:
                recognized["domain"] = obj["domain"]
            uid = auth(req)  # Reading a request body can interleave with reset.
        index = canonical([uid, req.rel_url.raw_path, key])
        if index in state["replays"]:
            old = state["replays"][index]
            require(old["body"] == recognized, 409, "idempotency_key_reuse")
            return 200, old["response"]
        name = normalized(path[len("/dossiers/"):-len("/refresh")] if refresh else get(recognized, "domain"))
        d = state["dossiers"].get(name)
        status = 202
        if refresh:
            require(d is not None, 404, "not_found")
            start(d, received)
        elif d is None:
            d = {"dossier_id": secrets.token_hex(16), "domain": name, "state": "failed", "fields": unknown_fields(),
                 "researched_at": None, "spent_units": 0}
            state["dossiers"][name] = d
            start(d, received)
        else:
            status = 200
        response = summary(view(d))
        state["replays"][index] = {"body": recognized, "response": response}
        return status, response
    raise ApiError(404, "not_found")


async def api(req):
    try:
        status, data = await handle(req)
    except ApiError as error:
        status, data = error.status, {"error": {"code": error.code, "message": error.code.replace("_", " ")}}
    if status == 204:
        return web.Response(status=204)
    return web.json_response(data, status=status)


if __name__ == "__main__":
    app = web.Application(client_max_size=256*1024**2)
    app.router.add_route("*", "/{path:.*}", api)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")), access_log=None, backlog=256)
