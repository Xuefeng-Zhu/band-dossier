"""Dossier Stage 1 HTTP API and atomic state lifecycle."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import scrypt
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
from threading import Lock, Thread
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from evidence import FIELDS, INTEGER_FIELDS, unknown_fields
from research import Audit, gather


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.body = {"error": {"code": code, "message": message}}


def invalid(message):
    return ApiError(422, "validation_failed", message)


def malformed(message):
    return ApiError(400, "malformed_request", message)


def unauthenticated():
    return ApiError(401, "unauthenticated", "Valid authentication is required")


def not_found():
    return ApiError(404, "not_found", "No such resource")


TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\d[Tt]\d\d:\d\d:\d\d(?:\.\d+)?(?:[Zz]|[+-]\d\d:\d\d)", re.ASCII)
DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
BEARER = re.compile(r"Bearer ([A-Za-z0-9_-]+)", re.I)
HEX = re.compile(r"[0-9a-f]+")


def timestamp(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise invalid("An RFC 3339 time with an offset is required")
    if not value.endswith(("z", "Z")) and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise invalid("Invalid timestamp offset")
    try:
        return datetime.fromisoformat(value.removesuffix("z") + "Z" if value.endswith("z") else value)
    except ValueError:
        raise invalid("Invalid timestamp") from None


def member(body, name, expected=str):
    if name not in body:
        raise invalid(f"Missing {name}")
    value = body[name]
    if type(value) is not expected:
        raise malformed(f"Invalid JSON type for {name}")
    return value


def object_body(value):
    if not isinstance(value, dict):
        raise malformed("Expected a JSON object")
    return value


def domain_name(value):
    value = value.strip().lower().removesuffix(".").removeprefix("www.")
    labels = value.split(".")
    if (len(value) > 253 or len(labels) < 2 or not all(DOMAIN_LABEL.fullmatch(label) for label in labels)):
        raise invalid("Invalid company domain")
    return value


def email_address(value):
    if not EMAIL.fullmatch(value):
        raise invalid("Invalid email address")
    return value


def password_hash(password, salt):
    return scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32).hex()


def account(user_id, email, name, password):
    if not user_id or len(user_id) > 64:
        raise invalid("User id must have between 1 and 64 characters")
    if not name or len(name) > 100:
        raise invalid("Display name must have between 1 and 100 characters")
    salt = secrets.token_bytes(16)
    try:
        digest = password_hash(password, salt)
    except UnicodeError:
        raise invalid("Invalid password text") from None
    return {"id": user_id, "email": email, "display_name": name, "salt": salt.hex(), "hash": digest}


def empty_state():
    return {"users": {}, "tokens": {}, "dossiers": {}, "idempotency": []}


def fixture(body):
    now = timestamp(member(body, "now"))
    users = member(body, "users", list) if "users" in body else []
    state = empty_state()
    records = []
    ids, emails = set(), set()
    for item in users:
        item = object_body(item)
        user_id = member(item, "id")
        email = email_address(member(item, "email"))
        if user_id in ids or email in emails:
            raise invalid("Duplicate fixture user")
        ids.add(user_id)
        emails.add(email)
        records.append((user_id, email, member(item, "display_name"), member(item, "password")))
    for user_id, email, name, password in records:
        state["users"][email] = account(user_id, email, name, password)
    return now, state


def require(condition):
    if not condition:
        raise invalid("Invalid snapshot state")


def nonnegative(value):
    return type(value) is int and value >= 0


def valid_id(value):
    return isinstance(value, str) and 1 <= len(value) <= 64


def is_hex(value, length):
    return isinstance(value, str) and len(value) == length and HEX.fullmatch(value)


def validate_fields(fields):
    require(type(fields) is dict and set(fields) == set(FIELDS))
    for field, entry in fields.items():
        require(type(entry) is dict and set(entry) == {"status", "value", "citations"})
        value, citations = entry["value"], entry["citations"]
        require(type(citations) is list)
        if value is None:
            require(entry["status"] == "unknown" and not citations)
            continue
        require(entry["status"] == "known" and bool(citations))
        require(type(value) is (int if field in INTEGER_FIELDS else str))
        for citation in citations:
            require(type(citation) is dict and set(citation) == {"url", "provider", "excerpt"})
            require(isinstance(citation["url"], str) and citation["provider"] in ("nimble", "tavily")
                    and isinstance(citation["excerpt"], str) and 1 <= len(citation["excerpt"]) <= 500)


def validate_build(build):
    require(type(build) is dict and build.get("outcome") in ("ready", "failed"))
    require(valid_id(build.get("id")))
    timestamp(build.get("started_at"))
    timestamp(build.get("completed_at"))
    require(nonnegative(build.get("spent_units")) and build["spent_units"] <= 80)
    audit = build.get("audit")
    require(type(audit) is dict and set(audit) == {"calls", "pages", "research_answers"})
    require(all(type(entries) is list and all(type(entry) is dict for entry in entries)
                for entries in audit.values()))
    require(all(nonnegative(call.get("spent_units")) for call in audit["calls"]))
    require(sum(call["spent_units"] for call in audit["calls"]) == build["spent_units"])
    for page in audit["pages"]:
        require(isinstance(page.get("text"), str) and isinstance(page.get("url"), str)
                and page.get("scope") in ("search", "citation")
                and nonnegative(page.get("call_id")) and page["call_id"] < len(audit["calls"]))
    for answer in audit["research_answers"]:
        claims = answer.get("claims")
        require(type(claims) is list and all(type(claim) is dict for claim in claims))
        for key in ("call_id", "start_call_id"):
            require(nonnegative(answer.get(key)) and answer[key] < len(audit["calls"]))


def validate_dossier(domain, dossier):
    require(domain == domain_name(domain) and type(dossier) is dict)
    require(set(dossier) == {"dossier_id", "state", "researched_at", "spent_units", "fields", "builds"})
    require(valid_id(dossier["dossier_id"]) and dossier["state"] in ("ready", "failed"))
    require(nonnegative(dossier["spent_units"]) and type(dossier["builds"]) is list)
    validate_fields(dossier["fields"])
    latest_ready = None
    for build in dossier["builds"]:
        validate_build(build)
        if build["outcome"] == "ready":
            latest_ready = build["started_at"]
    builds = dossier["builds"]
    require(dossier["state"] == (builds[-1]["outcome"] if builds else "failed"))
    require(dossier["spent_units"] == sum(build["spent_units"] for build in builds))
    require(dossier["researched_at"] == latest_ready)
    if latest_ready is None:
        require(dossier["fields"] == unknown_fields())


def import_state(body):
    if body.get("track") != "dossier" or type(body.get("format_version")) is not int or body["format_version"] != 1:
        raise invalid("Invalid snapshot track or version")
    state = body.get("state")
    require(type(state) is dict and set(state) == set(empty_state()))
    users, tokens, dossiers, idempotency = (state[key] for key in empty_state())
    require(all(type(mapping) is dict for mapping in (users, tokens, dossiers)) and type(idempotency) is list)
    ids = set()
    for email, user in users.items():
        require(EMAIL.fullmatch(email) and type(user) is dict
                and set(user) == {"id", "email", "display_name", "salt", "hash"})
        require(valid_id(user["id"]) and user["id"] not in ids and email == user["email"])
        require(isinstance(user["display_name"], str) and 1 <= len(user["display_name"]) <= 100)
        require(is_hex(user["salt"], 32) and is_hex(user["hash"], 64))
        ids.add(user["id"])
    for token, user_id in tokens.items():
        require(BEARER.fullmatch("Bearer " + token) and isinstance(user_id, str) and user_id in ids)
    for domain, dossier in dossiers.items():
        validate_dossier(domain, dossier)
    keys = set()
    for entry in idempotency:
        require(type(entry) is dict and set(entry) == {"user_id", "path", "key", "body", "status", "response"})
        user_id, path, key = (entry[field] for field in ("user_id", "path", "key"))
        require(all(isinstance(value, str) for value in (user_id, path, key)))
        require(user_id in ids and 1 <= len(key) <= 255 and (user_id, path, key) not in keys)
        require(type(entry["body"]) is dict and entry["status"] in (200, 202))
        replay = entry["response"]
        require(type(replay) is dict and set(replay) == {"dossier_id", "domain", "state"})
        require(valid_id(replay["dossier_id"]) and replay["state"] in ("building", "ready", "failed"))
        require(isinstance(replay["domain"], str) and replay["domain"] in dossiers
                and replay["dossier_id"] == dossiers[replay["domain"]]["dossier_id"])
        keys.add((user_id, path, key))
    return state


def query_integer(query, name, default, low, high=None):
    if name not in query:
        return default
    text = query[name][0]
    if not re.fullmatch(r"[0-9]+", text):
        raise invalid(f"Invalid {name}")
    digits = text.lstrip("0")
    # Any offset above this is beyond the size of the data set.
    value = int(digits or "0") if len(digits) < 20 else 10**20
    if value < low or (high is not None and value > high):
        raise invalid(f"{name} out of range")
    return value


class Service:
    def __init__(self):
        self.lock = Lock()
        self.clock = None
        self.state = empty_state()
        self.replays = {}
        self.jobs = {}
        self.loop = asyncio.new_event_loop()
        Thread(target=self.loop.run_forever, daemon=True).start()

    def now(self):
        return self.clock if self.clock is not None else datetime.now(timezone.utc)

    def replace(self, state, now=None):
        with self.lock:
            previous = self.jobs
            self.jobs = {}
            self.state = state
            self.replays = {(entry["user_id"], entry["path"], entry["key"]): entry
                            for entry in state["idempotency"]}
            if now is not None:
                self.clock = now
            for job in previous.values():
                job["worker"].cancel()

    def session(self, user):
        token = secrets.token_urlsafe(32)
        self.state["tokens"][token] = user["id"]
        return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def auth(self, path, body):
        email = email_address(member(body, "email"))
        password = member(body, "password")
        if path == "/auth/signup":
            name = member(body, "display_name")
            if len(password) < 8:
                raise invalid("Password must have at least eight characters")
            user = account("u_" + uuid4().hex, email, name, password)
            with self.lock:
                if email in self.state["users"]:
                    raise ApiError(409, "email_taken", "Email is already registered")
                self.state["users"][email] = user
                return 201, self.session(user)
        with self.lock:
            user = self.state["users"].get(email)
        try:
            if user is None or not compare_digest(password_hash(password, bytes.fromhex(user["salt"])), user["hash"]):
                raise unauthenticated()
        except UnicodeError:
            raise unauthenticated() from None
        with self.lock:
            if self.state["users"].get(email) is not user:
                raise unauthenticated()
            return 200, self.session(user)

    def authenticated_user(self, authorization):
        if match := BEARER.fullmatch(authorization or ""):
            if user_id := self.state["tokens"].get(match[1]):
                return user_id
        raise unauthenticated()

    async def run_build(self, domain, job):
        def active():
            with self.lock:
                return self.jobs.get(domain) is job

        def charge(units):
            with self.lock:
                if self.jobs.get(domain) is job:
                    job["spent_units"] += units

        audit = Audit(active, charge)
        try:
            fields = await gather(domain, audit)
        except asyncio.CancelledError:
            return
        except Exception as error:
            print(f"Dossier build error: {type(error).__name__}", flush=True)
            fields = unknown_fields()
        complete = any(call.get("outcome") in ("success", "no_page") for call in audit.calls)
        outcome = "ready" if complete else "failed"
        with self.lock:
            if self.jobs.get(domain) is not job:
                return
            dossier = self.state["dossiers"][domain]
            dossier["state"] = outcome
            dossier["spent_units"] += job["spent_units"]
            dossier["builds"].append({
                "id": job["id"], "started_at": job["started_at"], "completed_at": self.now().isoformat(),
                "outcome": outcome, "spent_units": job["spent_units"], "audit": audit.output(),
            })
            if complete:
                dossier.update(fields=fields, researched_at=job["started_at"])
            del self.jobs[domain]

    def start_build(self, domain, received):
        job = {"id": "b_" + uuid4().hex, "started_at": received.isoformat(), "spent_units": 0}
        self.jobs[domain] = job
        job["worker"] = asyncio.run_coroutine_threadsafe(self.run_build(domain, job), self.loop)

    def summary(self, domain, dossier):
        return {"dossier_id": dossier["dossier_id"], "domain": domain,
                "state": "building" if domain in self.jobs else dossier["state"]}

    def dossier_body(self, domain, dossier):
        job = self.jobs.get(domain)
        return {**self.summary(domain, dossier), "researched_at": dossier["researched_at"],
                "spent_units": dossier["spent_units"] + (job["spent_units"] if job else 0)}

    def write(self, user_id, path, raw_path, body, key, received):
        comparison = {field: body[field] for field in ("domain",) if field in body}
        scope = (user_id, raw_path, key)
        if existing := self.replays.get(scope):
            if comparison != existing["body"]:
                raise ApiError(409, "idempotency_key_reuse", "Key was used for a different body")
            return 200, existing["response"]
        if path == "/dossiers":
            domain = domain_name(member(body, "domain"))
            dossier = self.state["dossiers"].get(domain)
            status = 200
            if dossier is None:
                dossier = self.state["dossiers"][domain] = {
                    "dossier_id": "d_" + uuid4().hex, "state": "failed", "researched_at": None,
                    "spent_units": 0, "fields": unknown_fields(), "builds": [],
                }
                self.start_build(domain, received)
                status = 202
        else:
            domain = domain_name(path[len("/dossiers/"):-len("/refresh")])
            dossier = self.state["dossiers"].get(domain)
            if dossier is None:
                raise not_found()
            if domain not in self.jobs:
                self.start_build(domain, received)
            status = 202
        response = self.summary(domain, dossier)
        entry = {"user_id": user_id, "path": raw_path, "key": key, "body": comparison,
                 "status": status, "response": response}
        self.replays[scope] = entry
        self.state["idempotency"].append(entry)
        return status, response

    def read(self, path, query):
        if path != "/dossiers":
            domain = domain_name(path[len("/dossiers/"):])
            dossier = self.state["dossiers"].get(domain)
            if dossier is None:
                raise not_found()
            return 200, {**self.dossier_body(domain, dossier), "fields": dossier["fields"]}
        q = query.get("q", [""])[0].casefold()
        limit = query_integer(query, "limit", 50, 1, 200)
        offset = query_integer(query, "offset", 0, 0)
        entries = []
        for domain, dossier in sorted(self.state["dossiers"].items()):
            name = dossier["fields"]["legal_name"]["value"]
            if q in domain.casefold() or q in (name or "").casefold():
                entries.append({**self.dossier_body(domain, dossier), "legal_name": name})
        return 200, {"dossiers": entries[offset:offset + limit], "has_more": len(entries) > offset + limit}

    def request(self, method, target, headers, read_body):
        with self.lock:
            received = self.now()
        try:
            parts = urlsplit(target)
        except ValueError:
            raise invalid("Invalid request path") from None
        path = unquote(parts.path)
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        if method == "GET" and path == "/_test/export":
            with self.lock:
                return 200, {"track": "dossier", "format_version": 1, "state": deepcopy(self.state)}
        if method == "POST" and path == "/_test/reset":
            now, state = fixture(read_body())
            self.replace(state, now)
            return 204, None
        if method == "POST" and path == "/_test/import":
            self.replace(import_state(read_body()))
            return 204, None
        if method == "POST" and path == "/_test/clock":
            now = timestamp(member(read_body(), "now"))
            with self.lock:
                if now < self.now():
                    raise invalid("Clock cannot move backwards")
                self.clock = now
            return 204, None
        if method == "POST" and path in ("/auth/signup", "/auth/login"):
            return self.auth(path, read_body())
        if path.startswith("/_test/"):
            raise not_found()
        with self.lock:
            user_id = self.authenticated_user(headers.get("Authorization"))
            if method == "GET" and (path == "/dossiers" or path.startswith("/dossiers/")):
                return self.read(path, parse_qs(parts.query, keep_blank_values=True))
        refresh = path.startswith("/dossiers/") and path.endswith("/refresh")
        if method != "POST" or (path != "/dossiers" and not refresh):
            raise not_found()
        key = headers.get("Idempotency-Key")
        if not key:
            raise ApiError(400, "missing_idempotency_key", "Idempotency-Key is required")
        if len(key) > 255:
            raise invalid("Idempotency-Key exceeds 255 characters")
        body = {} if refresh else read_body()
        with self.lock:
            user_id = self.authenticated_user(headers.get("Authorization"))
            return self.write(user_id, path, parts.path, body, key, received)


def reject_json_constant(_):
    raise ValueError("Non-JSON numeric constant")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 5

    def chunks(self):
        while True:
            size_line = self.rfile.readline(8192)
            size_text = size_line.split(b";", 1)[0].strip()
            if not re.fullmatch(rb"[0-9a-fA-F]+", size_text):
                raise ValueError("Invalid chunk size")
            size = int(size_text, 16)
            if size == 0:
                while True:
                    line = self.rfile.readline(8192)
                    if line == b"\r\n":
                        return
                    if not line.endswith(b"\r\n"):
                        raise ValueError("Incomplete chunked request")
            chunk = self.rfile.read(size)
            if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                raise ValueError("Incomplete chunk")
            yield chunk

    def read_body(self):
        try:
            if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                content = b"".join(self.chunks())
            else:
                length = int(self.headers.get("Content-Length", 0))
                if length < 0:
                    raise ValueError("Negative body length")
                content = self.rfile.read(length)
                if len(content) != length:
                    raise ValueError("Incomplete request")
            return object_body(json.loads(content.decode("utf-8"), parse_constant=reject_json_constant))
        except (ValueError, OverflowError, RecursionError, OSError):
            raise malformed("Expected a UTF-8 JSON object") from None

    def send_json(self, status, body):
        encoded = b"" if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        if status != 204:
            self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if encoded and self.command != "HEAD":
            self.wfile.write(encoded)

    def dispatch(self):
        try:
            if self.path.split("?", 1)[0] in ("/_test/reset", "/_test/export", "/_test/import"):
                self.connection.settimeout(10)
            status, body = self.server.service.request(self.command, self.path, self.headers, self.read_body)
        except ApiError as error:
            status, body = error.status, error.body
        try:
            self.send_json(status, body)
        except (ConnectionError, TimeoutError):
            pass

    def send_error(self, code, message=None, explain=None):
        self.send_json(code, {"error": {"code": "malformed_request" if code == 400 else "not_found",
                                        "message": message or "Request could not be processed"}})

    def log_message(self, format, *args):
        # Request paths and client-provided headers are not audit provenance.
        pass

    do_GET = do_POST = do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = dispatch


class Server(ThreadingHTTPServer):
    request_queue_size = 128

    def __init__(self, address):
        self.service = Service()
        super().__init__(address, Handler)


if __name__ == "__main__":
    with Server(("0.0.0.0", int(os.environ.get("PORT", "8080")))) as server:
        server.serve_forever()
