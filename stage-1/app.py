"""Stage 1 HTTP API and atomic dossier state (R1, R3–R13, R18–R19, R23)."""

import copy
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from evidence import FIELDS, unknown_fields
from research import gather


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.code = code
        self.message = message


def invalid(message):
    raise ApiError(422, "validation_failed", message)


def malformed(message):
    raise ApiError(400, "malformed_request", message)


def unauthenticated():
    raise ApiError(401, "unauthenticated", "Valid credentials are required")


def missing():
    raise ApiError(404, "not_found", "Resource not found")


def require(data, field, expected=str):
    if field not in data:
        invalid(f"{field} is required")
    value = data[field]
    if type(value) is not expected:
        malformed(f"{field} must be a {expected.__name__}")
    return value


HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)
EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
CLOCK = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})[Tt]([0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.([0-9]+))?([Zz]|[+-][0-9]{2}:[0-9]{2})"
)


def domain_name(value):
    domain = value.strip().lower().removesuffix(".").removeprefix("www.")
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2 or any(not HOST_LABEL.fullmatch(x) for x in labels):
        invalid("Invalid domain name")
    return domain


def timestamp(value):
    match = CLOCK.fullmatch(value)
    if not match:
        invalid("now must be an RFC 3339 timestamp with an explicit offset")
    day, time, fraction, offset = match.groups()
    if offset in ("Z", "z"):
        offset = "+00:00"
    if int(offset[1:3]) > 23 or int(offset[4:]) > 59:
        invalid("Invalid clock offset")
    try:
        instant = datetime.fromisoformat(f"{day}T{time}{offset}")
    except ValueError:
        invalid("Invalid clock time")
    fraction = fraction or ""
    rendered = f"{day}T{time}" + (f".{fraction}" if fraction else "") + offset
    return (instant, fraction.rstrip("0")), rendered


def email_address(value):
    if not EMAIL.fullmatch(value):
        invalid("Invalid email address")
    return value


def display_name(value):
    if not 1 <= len(value) <= 100:
        invalid("display_name must be 1 to 100 characters")
    return value


def password_hash(password, salt=None):
    salt = secrets.token_hex(16) if salt is None else salt
    hashed = hashlib.scrypt(
        password.encode("utf-8", errors="surrogatepass"),
        salt=bytes.fromhex(salt), n=16384, r=8, p=1,
    )
    return f"{salt}:{hashed.hex()}"


def list_number(query, key, default, maximum=None):
    if key not in query:
        return default
    value = query[key][0]
    if not re.fullmatch(r"[0-9]+", value):
        invalid(f"{key} must be decimal digits")
    # Values above this cap are equivalent as offsets for any in-memory list.
    digits = value.lstrip("0") or "0"
    number = int(digits) if len(digits) <= 19 else 10**19
    if maximum is not None and not 1 <= number <= maximum:
        invalid(f"{key} is outside its allowed range")
    return number


def empty_state(now=None, users=None):
    return {"now": now, "users": users or {}, "tokens": {}, "dossiers": {}, "replays": {},
            "interrupted_builds": []}


def opaque_id(prefix):
    return prefix + uuid.uuid4().hex


def public_stub(dossier):
    return {name: dossier[name] for name in ("dossier_id", "domain", "state")}


def public_dossier(dossier):
    return {**public_stub(dossier),
            **{name: dossier[name] for name in ("researched_at", "spent_units", "fields")}}


def checked_export(packet):
    """Check the opaque schema and references before replacing destination state."""
    def check(condition):
        if not condition:
            invalid("Invalid exported dossier state")

    def identifier(value):
        return isinstance(value, str) and 0 < len(value) <= 64

    def date_or_none(value):
        if value is not None:
            check(isinstance(value, str))
            timestamp(value)

    def citations_are_valid(citations):
        check(isinstance(citations, list))
        for citation in citations:
            check(isinstance(citation, dict) and set(citation) == {"url", "provider", "excerpt"})
            check(isinstance(citation["url"], str) and bool(citation["url"]))
            check(isinstance(citation["excerpt"], str) and 1 <= len(citation["excerpt"]) <= 500)
            check(citation["provider"] in ("nimble", "tavily"))

    def elapsed_is_valid(seconds):
        return type(seconds) in (int, float) and 0 <= seconds < math.inf

    def audit(record, domain=None, interrupted=False):
        check(isinstance(record, dict))
        check(identifier(record.get("build_id")) and identifier(record.get("dossier_id")))
        check(isinstance(record.get("domain"), str) and domain_name(record["domain"]) == record["domain"])
        check(domain is None or record["domain"] == domain)
        check(record.get("outcome") in (("interrupted",) if interrupted else ("ready", "failed")))
        date_or_none(record.get("started_at"))
        date_or_none(record.get("completed_at"))
        check(isinstance(record.get("started_at"), str))
        check(interrupted or isinstance(record.get("completed_at"), str))
        check(type(record.get("spent_units")) is int and 0 <= record["spent_units"] <= 80)
        if not interrupted:
            check(elapsed_is_valid(record.get("elapsed_seconds")))
            candidates = record.get("candidates")
            check(isinstance(candidates, dict) and set(candidates) == set(FIELDS))
            for field, values in candidates.items():
                check(isinstance(values, list))
                for item in values:
                    check(isinstance(item, dict) and type(item.get("value")) is FIELDS[field])
                    citations_are_valid(item.get("citations"))
                    check(bool(item["citations"]))
        check(isinstance(record.get("calls"), list))
        for call in record["calls"]:
            check(isinstance(call, dict) and call.get("provider") in ("nimble", "tavily"))
            check(type(call.get("units")) is int and 0 <= call["units"] <= 80)
            check(call.get("operation") in ("search", "extract", "research", "research_result"))
            check(isinstance(call.get("target"), str) and elapsed_is_valid(call.get("elapsed_seconds")))
            check(call.get("outcome") in ("answered", "refused", "no_page", "no_answer", "unavailable", "started"))
            if "pages" in call:
                check(isinstance(call["pages"], list))
                check(all(isinstance(page, dict) and isinstance(page.get("url"), str)
                          and isinstance(page.get("text"), str) and page.get("provider") == call["provider"]
                          for page in call["pages"]))
        check(record["spent_units"] == sum(call["units"] for call in record["calls"]))

    check(packet.get("track") == "dossier" and type(packet.get("format_version")) is int
          and packet["format_version"] == 1)
    state = packet.get("state")
    check(isinstance(state, dict) and set(state) == set(empty_state()))
    check(all(isinstance(state[name], dict) for name in ("users", "tokens", "dossiers", "replays")))
    date_or_none(state["now"])
    user_ids = set()
    for email, user in state["users"].items():
        check(isinstance(user, dict) and set(user) == {"id", "display_name", "password_hash"})
        email_address(email)
        check(identifier(user["id"]) and user["id"] not in user_ids)
        user_ids.add(user["id"])
        check(isinstance(user["display_name"], str))
        display_name(user["display_name"])
        check(isinstance(user["password_hash"], str)
              and re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{128}", user["password_hash"]))
    for token, user_id in state["tokens"].items():
        check(identifier(token) and identifier(user_id) and user_id in user_ids)
    dossier_ids = set()
    for domain, dossier in state["dossiers"].items():
        check(domain_name(domain) == domain and isinstance(dossier, dict))
        check(set(dossier) == {"dossier_id", "domain", "state", "researched_at", "spent_units",
                               "fields", "builds", "active"})
        check(dossier["domain"] == domain and identifier(dossier["dossier_id"])
              and dossier["dossier_id"] not in dossier_ids)
        dossier_ids.add(dossier["dossier_id"])
        check(dossier["state"] in ("ready", "failed") and dossier["active"] is None)
        date_or_none(dossier["researched_at"])
        check(type(dossier["spent_units"]) is int and dossier["spent_units"] >= 0)
        fields = dossier["fields"]
        check(isinstance(fields, dict) and set(fields) == set(FIELDS))
        for field, result in fields.items():
            check(isinstance(result, dict) and set(result) == {"value", "status", "citations"})
            value, status, citations = result["value"], result["status"], result["citations"]
            citations_are_valid(citations)
            check((value is None and status == "unknown" and not citations)
                  or (type(value) is FIELDS[field] and status == "known" and bool(citations)))
        check(isinstance(dossier["builds"], list))
        for record in dossier["builds"]:
            audit(record, domain)
            check(record["dossier_id"] == dossier["dossier_id"])
        check(dossier["spent_units"] == sum(record["spent_units"] for record in dossier["builds"]))
        check(dossier["state"] == (dossier["builds"][-1]["outcome"] if dossier["builds"] else "failed"))
        ready = next((build for build in reversed(dossier["builds"]) if build["outcome"] == "ready"), None)
        check(dossier["researched_at"] == (ready["started_at"] if ready else None))
        check(ready is not None or fields == unknown_fields())
    for key, entry in state["replays"].items():
        try:
            scope = json.loads(key)
        except (ValueError, RecursionError):
            invalid("Invalid exported replay key")
        check(isinstance(scope, list) and len(scope) == 4 and all(isinstance(x, str) for x in scope))
        user_id, method, path, request_key = scope
        check(user_id in user_ids and method == "POST" and 1 <= len(request_key) <= 255)
        check(isinstance(entry, dict) and set(entry) == {"body", "response"})
        check(isinstance(entry["body"], dict))
        response = entry["response"]
        check(isinstance(response, dict) and set(response) == {"dossier_id", "domain", "state"})
        check(isinstance(response["domain"], str) and response["domain"] in state["dossiers"])
        check(response["dossier_id"] == state["dossiers"][response["domain"]]["dossier_id"]
              and response["state"] in ("building", "ready", "failed"))
        if path == "/dossiers":
            check(set(entry["body"]) == {"domain"} and isinstance(entry["body"]["domain"], str))
            check(domain_name(entry["body"]["domain"]) == response["domain"])
        else:
            match = re.fullmatch(r"/dossiers/([^/]+)/refresh", path)
            check(match is not None and not entry["body"])
            check(domain_name(unquote(match[1])) == response["domain"])
    check(isinstance(state["interrupted_builds"], list))
    for record in state["interrupted_builds"]:
        audit(record, interrupted=True)
        check(record["dossier_id"] in dossier_ids
              and state["dossiers"].get(record["domain"], {}).get("dossier_id") == record["dossier_id"])
    return state


class Service:
    def __init__(self, gather_pages=gather):
        self.lock = threading.RLock()
        self.state = empty_state()
        self.gather_pages = gather_pages
        # Throttle memory-intensive password verification to fit the container limit.
        self.hash_slots = threading.BoundedSemaphore(4)

    def now(self):
        return self.state["now"] or datetime.now(timezone.utc).isoformat()

    def hashed(self, password, salt=None):
        with self.hash_slots:
            return password_hash(password, salt)

    def reset(self, data):
        _, now = timestamp(require(data, "now"))
        users = {}
        ids = set()
        users_input = require(data, "users", list) if "users" in data else []
        for entry in users_input:
            if not isinstance(entry, dict):
                malformed("Fixture users must be objects")
            user_id = require(entry, "id")
            email = email_address(require(entry, "email"))
            password = require(entry, "password")
            name = display_name(require(entry, "display_name"))
            if not 0 < len(user_id) <= 64 or user_id in ids or email in users:
                invalid("Duplicate or invalid fixture identity")
            ids.add(user_id)
            users[email] = {"id": user_id, "display_name": name, "password_hash": self.hashed(password)}
        with self.lock:
            self.state = empty_state(now, users)
        return 204, None

    def set_clock(self, data):
        instant, now = timestamp(require(data, "now"))
        with self.lock:
            if instant < timestamp(self.now())[0]:
                invalid("The clock cannot move backwards")
            self.state["now"] = now
        return 204, None

    def export(self):
        with self.lock:
            state = copy.deepcopy(self.state)
        for dossier in state["dossiers"].values():
            active = dossier["active"]
            if active is not None:
                dossier["active"] = None
                dossier["state"] = active.pop("previous_state")
                dossier["spent_units"] -= active["spent_units"]
                state["interrupted_builds"].append({**active, "outcome": "interrupted"})
        return 200, {"track": "dossier", "format_version": 1, "state": state}

    def import_state(self, packet):
        state = checked_export(packet)
        with self.lock:
            self.state = state
        return 204, None

    def authenticate(self, authorization):
        match = re.fullmatch(r"Bearer ([A-Za-z0-9_-]+)", authorization or "", re.IGNORECASE)
        user_id = self.state["tokens"].get(match[1]) if match else None
        if user_id is None:
            unauthenticated()
        return user_id

    def account(self, data, signup):
        email = email_address(require(data, "email"))
        password = require(data, "password")
        if signup:
            name = display_name(require(data, "display_name"))
            if len(password) < 8:
                invalid("Password must be at least 8 characters")
            hashed = self.hashed(password)
            with self.lock:
                users = self.state["users"]
                if email in users:
                    raise ApiError(409, "email_taken", "Email already registered")
                user = {"id": opaque_id("u_"), "display_name": name, "password_hash": hashed}
                users[email] = user
                return 201, self.session(user)

        # Reset/import may replace the account while the hash is being computed.
        while True:
            with self.lock:
                user = self.state["users"].get(email)
                if user is None:
                    unauthenticated()
            stored_hash = user["password_hash"]
            submitted_hash = self.hashed(password, stored_hash.split(":", 1)[0])
            with self.lock:
                if self.state["users"].get(email) is not user:
                    continue
                if not hmac.compare_digest(stored_hash, submitted_hash):
                    unauthenticated()
                return 200, self.session(user)

    def session(self, user):
        token = secrets.token_urlsafe(32)
        self.state["tokens"][token] = user["id"]
        return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def start_build(self, dossier):
        state = self.state
        record = {
            "build_id": opaque_id("b_"), "dossier_id": dossier["dossier_id"],
            "domain": dossier["domain"], "started_at": self.now(), "completed_at": None,
            "outcome": None, "spent_units": 0, "calls": [], "previous_state": dossier["state"],
        }
        dossier["active"] = record
        dossier["state"] = "building"
        threading.Thread(target=self.build, args=(state, dossier, record), daemon=True).start()

    def build(self, state, dossier, record):
        started = time.monotonic()

        def current():
            with self.lock:
                return self.state is state

        def observe(call):
            with self.lock:
                if self.state is state:
                    record["calls"].append(call)
                    record["spent_units"] += call["units"]
                    dossier["spent_units"] += call["units"]

        succeeded, fields, candidates = False, unknown_fields(), {field: [] for field in FIELDS}
        try:
            succeeded, fields, candidates = self.gather_pages(record["domain"], current, observe)
        except Exception:
            # Provider data and exceptions may hold credentials, so log only a fixed message.
            logging.error("Dossier build encountered an unexpected internal error")
        with self.lock:
            if self.state is not state:
                return
            outcome = "ready" if succeeded else "failed"
            dossier["state"] = outcome
            if succeeded:
                dossier["fields"] = fields
                dossier["researched_at"] = record["started_at"]
            record["outcome"] = outcome
            record["completed_at"] = self.now()
            record["elapsed_seconds"] = time.monotonic() - started
            record["candidates"] = candidates
            del record["previous_state"]
            dossier["builds"].append(record)
            dossier["active"] = None

    def write(self, user, key, raw_path, raw_domain, data):
        if key is None or not key.strip():
            raise ApiError(400, "missing_idempotency_key", "Idempotency-Key is required")
        if len(key) > 255:
            invalid("Idempotency-Key exceeds 255 characters")
        create = raw_domain is None
        body = {"domain": data["domain"]} if create and "domain" in data else {}
        scope = json.dumps([user, "POST", raw_path, key], separators=(",", ":"))
        replay = self.state["replays"].get(scope)
        if replay is not None:
            if replay["body"] != body:
                raise ApiError(409, "idempotency_key_reuse", "Key was used with a different request")
            return 200, replay["response"]
        domain = domain_name(require(data, "domain") if create else raw_domain)
        dossier = self.state["dossiers"].get(domain)
        if dossier is None:
            if not create:
                missing()
            dossier = {
                "dossier_id": opaque_id("d_"), "domain": domain, "state": "failed",
                "researched_at": None, "spent_units": 0, "fields": unknown_fields(),
                "builds": [], "active": None,
            }
            self.state["dossiers"][domain] = dossier
            self.start_build(dossier)
            status = 202
        elif create:
            status = 200
        else:
            if dossier["active"] is None:
                self.start_build(dossier)
            status = 202
        response = public_stub(dossier)
        self.state["replays"][scope] = {"body": body, "response": response}
        return status, response

    def list_dossiers(self, query):
        q = query.get("q", [""])[0].casefold()
        limit = list_number(query, "limit", 50, 200)
        offset = list_number(query, "offset", 0)
        dossiers = []
        for domain, dossier in sorted(self.state["dossiers"].items()):
            legal_name = dossier["fields"]["legal_name"]["value"]
            if q in domain.casefold() or q in (legal_name or "").casefold():
                dossiers.append({**public_stub(dossier), "legal_name": legal_name,
                                 "researched_at": dossier["researched_at"],
                                 "spent_units": dossier["spent_units"]})
        return 200, {"dossiers": dossiers[offset:offset + limit], "has_more": offset + limit < len(dossiers)}

    def dispatch(self, method, target, headers, read_object):
        try:
            url = urlsplit(target)
        except ValueError:
            url = urlsplit("/")
        path = url.path
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        if method == "POST" and path in ("/auth/signup", "/auth/login"):
            return self.account(read_object(), path.endswith("/signup"))
        if path.startswith("/_test/"):
            if method == "POST" and path == "/_test/reset":
                return self.reset(read_object())
            if method == "POST" and path == "/_test/clock":
                return self.set_clock(read_object())
            if method == "GET" and path == "/_test/export":
                return self.export()
            if method == "POST" and path == "/_test/import":
                return self.import_state(read_object())
            missing()

        # Authenticate before parsing, then revalidate after any socket I/O.
        with self.lock:
            self.authenticate(headers.get("Authorization"))
        data = read_object() if method == "POST" and path == "/dossiers" else {}
        with self.lock:
            user = self.authenticate(headers.get("Authorization"))
            if path == "/dossiers":
                if method == "POST":
                    return self.write(user, headers.get("Idempotency-Key"), path, None, data)
                if method == "GET":
                    return self.list_dossiers(parse_qs(url.query, keep_blank_values=True))
            if method == "POST" and (match := re.fullmatch(r"/dossiers/([^/]+)/refresh", path)):
                return self.write(user, headers.get("Idempotency-Key"), path, unquote(match[1]), {})
            if method == "GET" and (match := re.fullmatch(r"/dossiers/([^/]+)", path)):
                dossier = self.state["dossiers"].get(domain_name(unquote(match[1])))
                if dossier is not None:
                    return 200, public_dossier(dossier)
            missing()


class HTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Dossier"
    sys_version = ""

    def read_body(self):
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = []
            while True:
                size_line = self.rfile.readline(65537)
                if len(size_line) > 65536 or not size_line.endswith(b"\r\n"):
                    malformed("Malformed chunk size")
                size_text = size_line[:-2].split(b";", 1)[0]
                if not re.fullmatch(rb"[0-9A-Fa-f]{1,16}", size_text):
                    malformed("Malformed chunk size")
                size = int(size_text, 16)
                if not size:
                    while True:
                        trailer = self.rfile.readline(65537)
                        if trailer == b"\r\n":
                            return b"".join(chunks)
                        if not trailer or len(trailer) > 65536:
                            malformed("Malformed chunk trailer")
                chunk = self.rfile.read(size)
                if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                    malformed("Incomplete chunk")
                chunks.append(chunk)
        length = self.headers.get("Content-Length", "0")
        if not re.fullmatch(r"[0-9]{1,18}", length):
            malformed("Invalid Content-Length")
        size = int(length)
        content = self.rfile.read(size)
        if len(content) != size:
            malformed("Incomplete request body")
        return content

    def read_object(self):
        def reject_constant(_):
            malformed("Use standard JSON values")

        try:
            obj = json.loads(self.read_body().decode("utf-8"), parse_constant=reject_constant)
        except (ValueError, RecursionError, OverflowError, TimeoutError):
            malformed("Invalid JSON request body")
        if not isinstance(obj, dict):
            malformed("Expected a JSON object")
        return obj

    def respond(self, status, body):
        # One request per connection also permits ignoring a refresh body without parsing it.
        self.close_connection = True
        self.send_response(status)
        self.send_header("Connection", "close")
        if status != 204:
            encoded = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if status != 204 and self.command != "HEAD":
            self.wfile.write(encoded)

    def route(self):
        service = self.server.service
        try:
            status, body = service.dispatch(self.command, self.path, self.headers, self.read_object)
        except ApiError as exc:
            status, body = exc.status, {"error": {"code": exc.code, "message": exc.message}}
        try:
            self.respond(status, body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = do_POST = do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = route

    def send_error(self, code, message=None, explain=None):
        if code == 501 and getattr(self, "headers", None) is not None:
            self.route()
            return
        self.respond(code, {"error": {"code": "malformed_request", "message": "Invalid HTTP request"}})

    def log_message(self, _format, *_args):
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address, service):
        self.service = service
        super().__init__(address, HTTPHandler)


if __name__ == "__main__":
    with Server(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Service()) as server:
        server.serve_forever()
