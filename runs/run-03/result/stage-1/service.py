"""In-memory HTTP service. The lock linearizes requests and worker publications."""
import copy
from datetime import datetime, timezone
from hashlib import scrypt, sha256
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
from threading import RLock, Thread
from urllib.parse import parse_qs, unquote, urlsplit

from evidence import empty_fields
from research import Build

LOCK = RLock()
CLOCK = None


def blank():
    return {"users": {}, "tokens": {}, "dossiers": {}, "replays": {}}


STATE = blank()
ERRORS = {"malformed_request": 400, "missing_idempotency_key": 400, "unauthenticated": 401,
          "not_found": 404, "email_taken": 409, "idempotency_key_reuse": 409, "validation_failed": 422}


class Error(Exception):
    def __init__(self, code, message=None):
        self.code = code
        self.message = message or code.replace("_", " ")


def need(condition, code="validation_failed", message=None):
    if not condition:
        raise Error(code, message)


def member(obj, key, kind=str):
    need(key in obj, message=f"Missing {key}")
    value = obj[key]
    need(isinstance(value, kind), "malformed_request", f"Invalid type for {key}")
    return value


def instant(value):
    parts = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]+))?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value)
    need(parts)
    try:
        whole_second = datetime.fromisoformat((parts[1] + parts[3]).upper())
    except ValueError:
        raise Error("validation_failed", "Invalid date or time")
    # Decimal fractions sort lexically once insignificant trailing zeros go.
    return whole_second, (parts[2] or "").rstrip("0")


def now():
    return CLOCK or datetime.now(timezone.utc).isoformat()


def normalize(value):
    domain = value.strip().lower().removesuffix(".").removeprefix("www.")
    labels = domain.split(".")
    need(len(domain) <= 253 and len(labels) > 1 and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels))
    return domain


def hashed(password, salt):
    return scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32).hex()


def user_record(obj, user_id, *, seeded=False):
    email = member(obj, "email")
    password = member(obj, "password")
    name = member(obj, "display_name")
    need(re.fullmatch(r"[^@\s]+@[^@\s]+", email))
    need((seeded or len(password) >= 8) and 1 <= len(name) <= 100 and 1 <= len(user_id) <= 64)
    salt = secrets.token_hex(16)
    return {"id": user_id, "email": email, "display_name": name, "salt": salt, "digest": hashed(password, salt)}


def login_response(user):
    token = secrets.token_urlsafe(32)
    STATE["tokens"][token] = user["id"]
    return {"user_id": user["id"], "display_name": user["display_name"], "token": token}


def reset(body):
    global STATE, CLOCK
    timestamp = member(body, "now").upper()
    instant(timestamp)
    fresh = blank()
    ids = set()
    users = body.get("users", [])
    need(isinstance(users, list), "malformed_request")
    for item in users:
        need(isinstance(item, dict), "malformed_request")
        record = user_record(item, member(item, "id"), seeded=True)
        email = record["email"].casefold()
        need(email not in fresh["users"] and record["id"] not in ids)
        ids.add(record["id"])
        fresh["users"][email] = record
    STATE, CLOCK = fresh, timestamp


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def export():
    snapshot = copy.deepcopy(STATE)
    for dossier in snapshot["dossiers"].values():
        before = dossier.pop("before", None)
        if before:
            dossier["state"], dossier["spent_units"] = before
    # Integrity check catches incomplete or changed transfer data before replacement.
    return {"track": "dossier", "format_version": 1,
            "state": {"records": snapshot, "sha256": sha256(canonical(snapshot).encode()).hexdigest()}}


def restore(body):
    global STATE
    need(body.get("track") == "dossier" and type(body.get("format_version")) is int and body["format_version"] == 1)
    state = body.get("state")
    need(isinstance(state, dict))
    records = state.get("records")
    need(isinstance(records, dict) and records.keys() == blank().keys())
    need(all(isinstance(v, dict) for v in records.values()))
    need(state.get("sha256") == sha256(canonical(records).encode()).hexdigest())
    try:
        ids = set()
        for email, u in records["users"].items():
            need(email == u["email"].casefold() and isinstance(u["display_name"], str))
            need(isinstance(u["id"], str) and 0 < len(u["id"]) <= 64 and u["id"] not in ids)
            ids.add(u["id"])
            need(re.fullmatch("[0-9a-f]{32}", u["salt"]) and re.fullmatch("[0-9a-f]{64}", u["digest"]))
        need(all(uid in ids for uid in records["tokens"].values()))
        for domain, d in records["dossiers"].items():
            need(normalize(domain) == domain == d["domain"] and d["state"] in ("ready", "failed"))
            need(isinstance(d["dossier_id"], str) and type(d["spent_units"]) is int and d["spent_units"] >= 0)
            need(d["researched_at"] is None or instant(d["researched_at"]))
            need(d["fields"].keys() == empty_fields().keys() and isinstance(d["history"], list))
            for field in d["fields"].values():
                need(isinstance(field["citations"], list) and
                     ((field["status"] == "known" and field["value"] is not None and field["citations"]) or
                      (field["status"] == "unknown" and field["value"] is None and not field["citations"])))
            need("before" not in d)
        for key, record in records["replays"].items():
            uid, method, path, client_key = json.loads(key)
            need(uid in ids and method == "POST" and isinstance(path, str) and 1 <= len(client_key) <= 255)
            need(isinstance(record["body"], str) and isinstance(record["response"], dict))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise Error("validation_failed")
    STATE = records


def build(dossier, timestamp, owner):
    def active():
        with LOCK:
            return owner is STATE

    def charge(amount):
        with LOCK:
            if owner is STATE:
                dossier["spent_units"] += amount

    attempt = Build(dossier["domain"], active, charge)
    try:
        attempt.run()
    finally:
        with LOCK:
            if owner is STATE:
                dossier["state"] = "ready" if attempt.success else "failed"
                if attempt.success:
                    dossier.update(fields=attempt.fields, researched_at=timestamp)
                dossier["history"].append({"time": timestamp, "calls": attempt.calls,
                                           "pages": attempt.pages, "claims": attempt.claims})
                dossier.pop("before")


def start(dossier):
    dossier["before"] = [dossier["state"], dossier["spent_units"]]
    dossier["state"] = "building"
    Thread(target=build, args=(dossier, now(), STATE), daemon=True).start()


def summary(dossier):
    return {k: dossier[k] for k in ("dossier_id", "domain", "state")}


def write(uid, raw_path, key, body, refresh_domain):
    need(key, "missing_idempotency_key")
    need(len(key) <= 255)
    replay_key = canonical([uid, "POST", raw_path, key])
    fingerprint = canonical({k: body[k] for k in ("domain",) if k in body}) if refresh_domain is None else "{}"
    cached = STATE["replays"].get(replay_key)
    if cached is not None:
        need(cached["body"] == fingerprint, "idempotency_key_reuse")
        return 200, cached["response"]
    dossiers = STATE["dossiers"]
    if refresh_domain is not None:
        domain = normalize(refresh_domain)
        need(domain in dossiers, "not_found")
        dossier = dossiers[domain]
        if dossier["state"] != "building":
            start(dossier)
        status = 202
    else:
        domain = normalize(member(body, "domain"))
        dossier = dossiers.get(domain)
        if dossier is None:
            dossier = {"dossier_id": secrets.token_hex(16), "domain": domain, "state": "failed",
                       "fields": empty_fields(), "researched_at": None, "spent_units": 0, "history": []}
            dossiers[domain] = dossier
            start(dossier)
            status = 202
        else:
            status = 200
    response = summary(dossier)
    STATE["replays"][replay_key] = {"body": fingerprint, "response": response}
    return status, response


def listing(query):
    params = parse_qs(query, keep_blank_values=True)
    def integer(name, default, high):
        raw = params.get(name, [str(default)])[0]
        need(re.fullmatch("[0-9]+", raw))
        significant = raw.lstrip("0") or "0"
        if len(significant) > 19:
            need(high is None)
            return len(STATE["dossiers"]) + 1
        n = int(significant)
        need(high is None or 1 <= n <= high)
        return n
    limit, offset = integer("limit", 50, 200), integer("offset", 0, None)
    q = params.get("q", [""])[0].casefold()
    rows = []
    for domain, d in sorted(STATE["dossiers"].items()):
        name = d["fields"]["legal_name"]["value"]
        if q in domain or q in (name or "").casefold():
            rows.append({**summary(d), "legal_name": name, "researched_at": d["researched_at"], "spent_units": d["spent_units"]})
    return {"dossiers": rows[offset:offset + limit], "has_more": offset + limit < len(rows)}


class Handler(BaseHTTPRequestHandler):
    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler uses this hook before dispatch, including
        # when it cannot find a handler for the request's method.
        error = "not_found" if code == 501 else "malformed_request"
        encoded = canonical({"error": {"code": error, "message": error.replace("_", " ")}}).encode()
        self.send_response(ERRORS[error])
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    def log_message(self, *args):
        pass

    def body(self):
        try:
            obj = json.loads(self.payload, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            raise Error("malformed_request", "Invalid JSON")
        need(isinstance(obj, dict), "malformed_request")
        return obj

    def dispatch(self):
        global CLOCK
        parsed = urlsplit(self.path)
        path, method = unquote(parsed.path), self.command
        if (method, path) == ("GET", "/health"):
            return 200, {"status": "ok"}
        if (method, path) == ("POST", "/_test/reset"):
            reset(self.body())
            return 204, None
        if (method, path) == ("POST", "/_test/clock"):
            value = member(self.body(), "now").upper()
            need(instant(value) >= instant(now()))
            CLOCK = value
            return 204, None
        if (method, path) == ("GET", "/_test/export"):
            return 200, export()
        if (method, path) == ("POST", "/_test/import"):
            restore(self.body())
            return 204, None
        if method == "POST" and path in ("/auth/signup", "/auth/login"):
            body = self.body()
            email = member(body, "email")
            password = member(body, "password")
            need(re.fullmatch(r"[^@\s]+@[^@\s]+", email))
            user = STATE["users"].get(email.casefold())
            if path.endswith("/signup"):
                record = user_record(body, secrets.token_hex(16))
                need(user is None, "email_taken")
                STATE["users"][email.casefold()] = record
                return 201, login_response(record)
            need(user is not None and hmac.compare_digest(user["digest"], hashed(password, user["salt"])), "unauthenticated")
            return 200, login_response(user)
        auth = re.fullmatch(r"Bearer ([^\s]+)", self.headers.get("Authorization", ""), re.I)
        uid = auth and STATE["tokens"].get(auth[1])
        need(uid, "unauthenticated")
        if method == "GET" and path == "/dossiers":
            return 200, listing(parsed.query)
        if method == "GET" and path.startswith("/dossiers/"):
            domain = normalize(path[len("/dossiers/"):])
            d = STATE["dossiers"].get(domain)
            need(d, "not_found")
            return 200, {k: v for k, v in d.items() if k not in ("history", "before")}
        match = re.fullmatch(r"/dossiers/(.*)/refresh", path)
        if method == "POST" and (path == "/dossiers" or match):
            key = self.headers.get("Idempotency-Key")
            need(key, "missing_idempotency_key")
            return write(uid, parsed.path, key, {} if match else self.body(), match[1] if match else None)
        raise Error("not_found")

    def serve(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            need(length >= 0, "malformed_request")
            self.payload = self.rfile.read(length)
            with LOCK:
                status, result = self.dispatch()
                encoded = canonical(result).encode() if result is not None else b""
        except Error as e:
            status = ERRORS[e.code]
            encoded = canonical({"error": {"code": e.code, "message": e.message}}).encode()
        except (ValueError, UnicodeError, RecursionError):
            status = 400
            encoded = b'{"error":{"code":"malformed_request","message":"Invalid input"}}'
        self.send_response(status)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)

    do_GET = do_POST = do_DELETE = do_PUT = do_PATCH = do_HEAD = do_OPTIONS = serve


class Server(ThreadingHTTPServer):
    request_queue_size = 128


if __name__ == "__main__":
    Server(("0.0.0.0", int(os.getenv("PORT", "8080"))), Handler).serve_forever()
