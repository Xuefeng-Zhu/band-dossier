"""HTTP and atomic in-memory state for Dossier Stage 1."""

import base64
import binascii
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from evidence import (
    AUTHORITY, PHRASES, PROVIDERS, RANGES, empty_fields, field_from_candidates, parse_timestamp,
    public_url, select_fields,
)
from research import gather


class Problem(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code


def bad(message):
    raise Problem(422, "validation_failed", message)


def malformed(message):
    raise Problem(400, "malformed_request", message)


def unauthenticated():
    raise Problem(401, "unauthenticated", "Valid credentials are required.")


MISSING = object()
DOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
HASH_SLOTS = threading.BoundedSemaphore(4)
HEADCOUNTS = {label for _, label in RANGES} | {"10001+"}


def string(body, key):
    value = body.get(key, MISSING)
    if value is MISSING:
        bad(f"{key} is required.")
    if not isinstance(value, str):
        malformed(f"{key} must be a string.")
    return value


def normal_domain(value):
    value = value.strip().lower().removesuffix(".").removeprefix("www.")
    return checked_domain(value)


def checked_domain(value):
    labels = value.split(".")
    if len(value) > 253 or len(labels) < 2 or any(not DOMAIN.fullmatch(label) for label in labels):
        bad("Expected a valid host name.")
    return value


def timestamp(value):
    parsed = parse_timestamp(value)
    if parsed is None:
        bad("Expected an RFC 3339 timestamp with an explicit offset.")
    return parsed


def hash_password(password, salt):
    with HASH_SLOTS:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)


def b64(value):
    return base64.b64encode(value).decode("ascii")


def make_user(user_id, email, display_name, password):
    salt = secrets.token_bytes(16)
    return {"id": user_id, "email": email, "display_name": display_name,
            "salt": b64(salt), "password_hash": b64(hash_password(password, salt))}


def password_matches(user, password):
    digest = hash_password(password, base64.b64decode(user["salt"]))
    return hmac.compare_digest(digest, base64.b64decode(user["password_hash"]))


def public_brief(dossier):
    return {key: dossier[key] for key in ("dossier_id", "domain", "state")}


def public_detail(dossier):
    return {key: dossier[key] for key in
            ("dossier_id", "domain", "state", "researched_at", "spent_units", "fields")}


def new_dossier(domain):
    return {"dossier_id": secrets.token_urlsafe(18), "domain": domain, "state": "failed",
            "researched_at": None, "spent_units": 0, "fields": empty_fields(), "builds": []}


def new_state(users=None):
    return {"users": {} if users is None else users, "sessions": {}, "dossiers": {}, "replays": []}


def require(condition):
    if not condition:
        bad("The imported state is invalid.")


def valid_id(value):
    return isinstance(value, str) and 1 <= len(value) <= 64


def validate_field_value(field, value):
    if field in {"funding_total", "founded_year"}:
        require(type(value) is int)
    elif field == "headcount_range":
        require(isinstance(value, str) and value in HEADCOUNTS)
    else:
        require(isinstance(value, str) and bool(value))


def validate_citation(item):
    require(public_url(item["url"]) and item["provider"] in PROVIDERS)
    require(isinstance(item["excerpt"], str) and 1 <= len(item["excerpt"]) <= 500)


def validate_fields(fields, legacy):
    require(isinstance(fields, dict) and fields.keys() == PHRASES.keys())
    shape = {"value", "status", "citations"} if legacy else {"value", "status", "citations", "candidates"}
    for field, item in fields.items():
        require(isinstance(item, dict) and item.keys() == shape)
        value = item["value"]
        citations = item["citations"]
        require(isinstance(citations, list))
        if legacy:
            require(item["status"] == ("unknown" if value is None else "known"))
            require(bool(citations) == (value is not None))
        else:
            candidates = item["candidates"]
            require(isinstance(candidates, list))
            for candidate in candidates:
                require(isinstance(candidate, dict) and candidate.keys() == {
                    "value", "url", "excerpt", "provider", "kind", "published_at", "retrieved_at", "selected",
                })
                validate_citation(candidate)
                validate_field_value(field, candidate["value"])
                kind = candidate["kind"]
                require(kind is None or isinstance(kind, str) and kind in AUTHORITY)
                if candidate["published_at"] is not None:
                    timestamp(candidate["published_at"])
                timestamp(candidate["retrieved_at"])
                require(type(candidate["selected"]) is bool)
            require(item == field_from_candidates(candidates))
        if value is not None:
            validate_field_value(field, value)
        for citation in citations:
            require(isinstance(citation, dict) and citation.keys() == {"url", "provider", "excerpt"})
            validate_citation(citation)


def validate_snapshot(value):
    require(isinstance(value, dict) and value.get("track") == "dossier")
    require(type(value.get("format_version")) is int and value["format_version"] == 1)
    state = value.get("state")
    require(isinstance(state, dict) and state.keys() == new_state().keys())
    for key in ("users", "sessions", "dossiers"):
        require(isinstance(state[key], dict))
    require(isinstance(state["replays"], list))
    user_ids = set()
    for email, user in state["users"].items():
        require(isinstance(user, dict) and set(user) == {"id", "email", "display_name", "salt", "password_hash"})
        require(email == user["email"] and EMAIL.fullmatch(email) and valid_id(user["id"]))
        require(user["id"] not in user_ids and isinstance(user["display_name"], str))
        try:
            require(len(base64.b64decode(user["salt"], validate=True)) == 16)
            require(len(base64.b64decode(user["password_hash"], validate=True)) == 32)
        except (ValueError, TypeError, binascii.Error):
            bad("The imported account hash is invalid.")
        user_ids.add(user["id"])
    for token, owner in state["sessions"].items():
        require(TOKEN.fullmatch(token) and isinstance(owner, str) and owner in user_ids)

    dossier_ids = set()
    for domain, dossier in state["dossiers"].items():
        require(isinstance(dossier, dict) and dossier.keys() == new_dossier("").keys())
        require(checked_domain(domain) == dossier["domain"] and valid_id(dossier["dossier_id"]))
        require(dossier["dossier_id"] not in dossier_ids and dossier["state"] in ("ready", "failed"))
        dossier_ids.add(dossier["dossier_id"])
        fields = dossier["fields"]
        require(isinstance(fields, dict))
        legacy = all(isinstance(field, dict) and "candidates" not in field for field in fields.values())
        validate_fields(fields, legacy)
        require(isinstance(dossier["builds"], list))
        require(type(dossier["spent_units"]) is int and dossier["spent_units"] >= 0)
        spend = 0
        last_ready = None
        outcome = "failed"
        builds = set()
        for build in dossier["builds"]:
            require(isinstance(build, dict) and build.keys() == {
                "id", "started_at", "completed_at", "elapsed_ms", "outcome", "spent_units", "calls",
                "pages", "claims",
            })
            require(valid_id(build["id"]) and build["id"] not in builds)
            builds.add(build["id"])
            timestamp(build["started_at"])
            timestamp(build["completed_at"])
            require(type(build["elapsed_ms"]) is int and build["elapsed_ms"] >= 0)
            require(type(build["spent_units"]) is int and 0 <= build["spent_units"] <= 80)
            require(build["outcome"] in ("ready", "failed"))
            for key in ("calls", "pages", "claims"):
                require(isinstance(build[key], list) and all(isinstance(item, dict) for item in build[key]))
            require(all(isinstance(page.get("text"), str) and isinstance(page.get("url"), str)
                        for page in build["pages"]))
            require(all(isinstance(page.get("provider"), str) and page["provider"] in PROVIDERS
                        and isinstance(page.get("headers", {}), dict)
                        for page in build["pages"]))
            settled_spend = 0
            for call in build["calls"]:
                require(call.get("provider") == "nimble" and isinstance(call.get("argument"), dict))
                units = call.get("spent_units")
                require(type(units) is int and units in (0, 1, 3, 15, 25))
                settled_spend += units
            require(settled_spend == build["spent_units"])
            spend += build["spent_units"]
            outcome = build["outcome"]
            if outcome == "ready":
                last_ready = build
        researched = last_ready["started_at"] if last_ready else None
        require(dossier["researched_at"] == researched and spend == dossier["spent_units"])
        require(dossier["state"] == outcome)
        if last_ready is None:
            require(all(field["value"] is None for field in fields.values()))
        if legacy:
            dossier["fields"] = select_fields(
                domain, last_ready["pages"], researched, last_ready["claims"], imported=True,
            ) if last_ready else empty_fields()
    replays = set()
    for replay in state["replays"]:
        require(isinstance(replay, list) and len(replay) == 5)
        owner, path, key, body, response = replay
        require(isinstance(owner, str) and owner in user_ids and isinstance(path, str))
        require(isinstance(key, str) and 1 <= len(key) <= 255 and isinstance(body, dict))
        require(isinstance(response, dict) and response.keys() == {"dossier_id", "domain", "state"})
        domain = response["domain"]
        require(isinstance(domain, str) and domain in state["dossiers"])
        require(response["dossier_id"] == state["dossiers"][domain]["dossier_id"])
        require(response["state"] in ("building", "ready", "failed"))
        require((owner, path, key) not in replays)
        replays.add((owner, path, key))
        if path == "/dossiers":
            require(body.keys() == {"domain"} and isinstance(body["domain"], str))
            require(normal_domain(body["domain"]) == domain)
        else:
            require(path.startswith("/dossiers/") and path.endswith("/refresh") and not body)
            require(normal_domain(path[len("/dossiers/"):-len("/refresh")]) == domain)
    return state


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.clock = None
        self.state = new_state()
        self.replays = {}
        self.before_build = {}

    def now(self):
        return self.clock or datetime.now(timezone.utc)

    def set_clock(self, body):
        next_time = timestamp(string(body, "now"))
        with self.lock:
            if next_time < self.now():
                bad("The clock cannot move backwards.")
            self.clock = next_time

    def reset(self, fixture):
        instant = timestamp(string(fixture, "now"))
        users = fixture.get("users", [])
        if not isinstance(users, list):
            malformed("users must be an array.")
        accounts = {}
        ids = set()
        for user in users:
            if not isinstance(user, dict):
                malformed("A seeded user must be an object.")
            uid, email, display_name, password = (
                string(user, key) for key in ("id", "email", "display_name", "password")
            )
            if email in accounts or uid in ids or not valid_id(uid) or not EMAIL.fullmatch(email):
                bad("Invalid or duplicate fixture account.")
            accounts[email] = make_user(uid, email, display_name, password)
            ids.add(uid)
        with self.lock:
            self.replace(new_state(accounts))
            self.clock = instant

    def replace(self, state):
        self.state = state
        self.replays = {tuple(item[:3]): item for item in state["replays"]}
        self.before_build = {}

    def export(self):
        with self.lock:
            snapshot = self.state | {"dossiers": self.state["dossiers"] | self.before_build}
            return {"track": "dossier", "format_version": 1, "state": copy.deepcopy(snapshot)}

    def authenticate(self, value):
        match = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{43})", value or "", re.I)
        owner = self.state["sessions"].get(match[1]) if match else None
        if owner is None:
            unauthenticated()
        return owner

    def signin(self, body, signup):
        email = string(body, "email")
        password = string(body, "password")
        if signup:
            display_name = string(body, "display_name")
            if not EMAIL.fullmatch(email) or len(password) < 8 or not 1 <= len(display_name) <= 100:
                bad("An email, a password of at least 8 characters, and a display name are required.")
            user = make_user(secrets.token_urlsafe(18), email, display_name, password)
        else:
            with self.lock:
                user = self.state["users"].get(email)
            if not user or not password_matches(user, password):
                unauthenticated()
        with self.lock:
            accounts = self.state["users"]
            if signup:
                if email in accounts:
                    raise Problem(409, "email_taken", "That email is already registered.")
                accounts[email] = user
            elif accounts.get(email) is not user:
                unauthenticated()
            token = secrets.token_urlsafe(32)
            self.state["sessions"][token] = user["id"]
            return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def write(self, owner, path, key, body, received, domain_path=None):
        scope = (owner, path, key)
        prior = self.replays.get(scope)
        if prior is not None:
            if prior[3] != body:
                raise Problem(409, "idempotency_key_reuse", "That key was already used with a different body.")
            return 200, prior[4]
        refresh = domain_path is not None
        domain = normal_domain(domain_path if refresh else string(body, "domain"))
        dossier = self.state["dossiers"].get(domain)
        if refresh and dossier is None:
            raise Problem(404, "not_found", "Dossier not found.")
        if not refresh and dossier is not None:
            status = 200
        else:
            status = 202
            if dossier is None:
                dossier = self.state["dossiers"][domain] = new_dossier(domain)
            if dossier["state"] != "building":
                self.start(dossier, received)
        result = public_brief(dossier)
        replay = [owner, path, key, body, result]
        self.replays[scope] = replay
        self.state["replays"].append(replay)
        return status, result

    def start(self, dossier, received):
        domain = dossier["domain"]
        prior = dossier.copy()
        self.before_build[domain] = prior
        dossier["state"] = "building"
        worker = threading.Thread(target=self.build, args=(dossier, prior, received), daemon=True)
        worker.start()

    def build(self, dossier, prior, received):
        domain = dossier["domain"]
        started = time.monotonic()
        record = {"id": secrets.token_urlsafe(18), "started_at": received, "completed_at": None,
                  "elapsed_ms": None, "outcome": "failed", "spent_units": 0,
                  "calls": [], "pages": [], "claims": []}

        def current():
            return self.state["dossiers"].get(domain) is dossier

        def observed(cost=0):
            with self.lock:
                if not current():
                    return False
                dossier["spent_units"] += cost
                return True

        try:
            fields = gather(domain, record, observed)
        except Exception:
            # Preserve completed observations even when interpretation cannot complete.
            fields = None
        with self.lock:
            if not current():
                return
            record["completed_at"] = self.now().isoformat()
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            if fields is not None:
                record["outcome"] = "ready"
                dossier["fields"] = fields
                dossier["researched_at"] = received
            dossier["state"] = record["outcome"]
            dossier["builds"] = prior["builds"] + [record]
            self.before_build.pop(domain, None)

    def get(self, domain):
        dossier = self.state["dossiers"].get(normal_domain(domain))
        if dossier is None:
            raise Problem(404, "not_found", "Dossier not found.")
        return public_detail(dossier)

    def listed(self, q, limit, offset):
        items = []
        for domain, dossier in sorted(self.state["dossiers"].items()):
            legal_name = dossier["fields"]["legal_name"]["value"]
            if q in domain.casefold() or q in (legal_name or "").casefold():
                items.append(public_brief(dossier) | {
                    "legal_name": legal_name, "researched_at": dossier["researched_at"],
                    "spent_units": dossier["spent_units"],
                })
        return {"dossiers": items[offset:offset + limit], "has_more": len(items) > offset + limit}


def paging(query, key, default, minimum, maximum=None):
    if key not in query:
        return default
    raw = query[key][0]
    if not re.fullmatch(r"[0-9]+", raw):
        bad(f"{key} must be a decimal integer.")
    digits = raw.lstrip("0")
    # A large offset is equivalent to an empty page for this finite store.
    number = int(digits or "0") if len(digits) < 20 else 10**20
    if number < minimum or maximum is not None and number > maximum:
        bad(f"{key} is out of range.")
    return number


STORE = Store()
DETAIL = re.compile(r"/dossiers/([^/]*)")
REFRESH = re.compile(r"/dossiers/([^/]*)/refresh")
EVIDENCE = re.compile(r"/dossiers/([^/]*)/evidence")
WEB = Path(__file__).with_name("web")
BROWSER_ROUTES = {"/": "list", "/signup": "signup", "/login": "login", "/contested": "contested"}
STATIC = {
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/style.css": ("style.css", "text/css; charset=utf-8"),
}


class Page:
    def __init__(self, body, content_type):
        self.body = body
        self.content_type = content_type


def page_for(path, accept):
    if path in STATIC:
        filename, content_type = STATIC[path]
        return Page((WEB / filename).read_bytes(), content_type)
    screen = BROWSER_ROUTES.get(path)
    domain = ""
    if match := EVIDENCE.fullmatch(path):
        screen, domain = "evidence", normal_domain(match[1])
    elif DETAIL.fullmatch(path) and any(
        part.split(";", 1)[0].strip().lower() == "text/html"
        for part in accept.split(",")
        if not re.search(r"(?:^|;)\s*q=0(?:\.0+)?(?:;|$)", part.strip())
    ):
        screen, domain = "detail", normal_domain(DETAIL.fullmatch(path)[1])
    if screen:
        template = (WEB / "index.html").read_text(encoding="utf-8")
        html = template.replace("{{SCREEN}}", screen).replace("{{DOMAIN}}", escape(domain, quote=True))
        return Page(html.encode("utf-8"), "text/html; charset=utf-8")
    return None


def reject_constant(_value):
    raise ValueError("Invalid JSON constant")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, value=None):
        content_type = "application/json; charset=utf-8"
        if isinstance(value, Page):
            body, content_type = value.body, value.content_type
        elif value is None:
            body = b""
        else:
            body = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        if status != 204:
            self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Accept")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"error": {"code": "malformed_request", "message": message or "Invalid request."}})

    def payload(self):
        try:
            encodings = self.headers.get("Transfer-Encoding", "").lower()
            if encodings == "chunked":
                pieces = []
                while size := int(self.rfile.readline(128).split(b";", 1)[0], 16):
                    if size < 0:
                        raise ValueError("Invalid chunk size")
                    pieces.append(self.rfile.read(size))
                    if self.rfile.read(2) != b"\r\n":
                        raise ValueError("Invalid chunk end")
                raw = b"".join(pieces)
            elif encodings:
                raise ValueError("Unsupported encoding")
            else:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 0:
                    raise ValueError("Invalid body size")
                raw = self.rfile.read(size)
            body = json.loads(raw, parse_constant=reject_constant)
            # JSON permits escaped surrogate code points, which are invalid in UTF-8.
            raw_text = json.dumps(body, ensure_ascii=False, allow_nan=False)
            raw_text.encode("utf-8")
        except (OSError, ValueError, UnicodeError, RecursionError):
            malformed("Expected a JSON object.")
        if not isinstance(body, dict):
            malformed("Expected a JSON object.")
        return body

    def dispatch(self):
        with STORE.lock:
            received = STORE.now().isoformat()
        try:
            target = urlsplit(self.path)
        except ValueError:
            malformed("Invalid request target.")
        raw_path = target.path
        path = unquote(raw_path)
        method = self.command
        if method in ("GET", "HEAD"):
            if page := page_for(path, self.headers.get("Accept", "")):
                return 200, page
        if (method, path) == ("GET", "/health"):
            return 200, {"status": "ok"}
        if method == "POST" and path in ("/auth/login", "/auth/signup"):
            signup = path.endswith("/signup")
            return (201 if signup else 200), STORE.signin(self.payload(), signup)
        if (method, path) == ("POST", "/_test/reset"):
            STORE.reset(self.payload())
            return 204, None
        if (method, path) == ("POST", "/_test/clock"):
            STORE.set_clock(self.payload())
            return 204, None
        if (method, path) == ("GET", "/_test/export"):
            return 200, STORE.export()
        if (method, path) == ("POST", "/_test/import"):
            snapshot = validate_snapshot(self.payload())
            with STORE.lock:
                STORE.replace(snapshot)
            return 204, None

        refresh = REFRESH.fullmatch(path)
        detail = DETAIL.fullmatch(path)
        authorization = self.headers.get("Authorization")
        with STORE.lock:
            if not (path == "/health" or path.startswith("/_test/")):
                STORE.authenticate(authorization)
            if method == "GET" and path == "/dossiers":
                query = parse_qs(target.query, keep_blank_values=True)
                q = query.get("q", [""])[0].casefold()
                return 200, STORE.listed(q, paging(query, "limit", 50, 1, 200),
                                         paging(query, "offset", 0, 0))
            if method == "GET" and detail:
                return 200, STORE.get(detail[1])
        if method == "POST" and (refresh or path == "/dossiers"):
            key = self.headers.get("Idempotency-Key", "").strip()
            if not key:
                raise Problem(400, "missing_idempotency_key", "An Idempotency-Key is required.")
            if len(key) > 255:
                bad("Idempotency-Key must be 1 to 255 characters.")
            if refresh:
                body = {}
            else:
                parsed = self.payload()
                body = {"domain": parsed["domain"]} if "domain" in parsed else {}
            with STORE.lock:
                owner = STORE.authenticate(authorization)
                return STORE.write(owner, path, key, body, received, refresh[1] if refresh else None)
        raise Problem(404, "not_found", "Route not found.")

    def handle_request(self):
        try:
            try:
                status, value = self.dispatch()
            except Problem as error:
                status = error.status
                value = {"error": {"code": error.code, "message": str(error)}}
            self.reply(status, value)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = handle_request


class Server(ThreadingHTTPServer):
    request_queue_size = 128

    def get_request(self):
        accepted, address = super().get_request()
        accepted.settimeout(4)
        return accepted, address


if __name__ == "__main__":
    with Server(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler) as server:
        server.serve_forever()
