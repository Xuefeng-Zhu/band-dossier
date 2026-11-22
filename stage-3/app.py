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
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from candidates import AUTHORITY, CANDIDATE_KEYS, PROVIDERS, day_key, publication_key, select, unknown_fields
from evidence import FIELDS, unknown_fields as legacy_unknown_fields
from research import gather
from temporal import ALL_FIELDS, GROUPS, TITLES, empty_fields, finish, new_timeline, through, upgrade, valid_values


@dataclass(frozen=True)
class Asset:
    name: str
    content_type: str


WEB_ROOT = Path(__file__).resolve().with_name("web")
HTML = Asset("index.html", "text/html; charset=utf-8")
WEB_ASSETS = {
    "/assets/app.js": Asset("app.js", "text/javascript; charset=utf-8"),
    "/assets/app.css": Asset("app.css", "text/css; charset=utf-8"),
}


def accepts_html(value):
    for entry in value.split(","):
        media, *params = entry.strip().lower().split(";")
        if media.strip() == "text/html":
            quality = next((item.strip()[2:] for item in params if item.strip().startswith("q=")), "1")
            try:
                if float(quality) > 0:
                    return True
            except ValueError:
                continue
    return False


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
            "interrupted_builds": [], "stage": 3, "changes": [], "next_seq": 1}


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
            check(citation["provider"] in PROVIDERS)

    def candidate_is_valid(item, field, public, *, temporal=False, selected=True):
        raw_keys = CANDIDATE_KEYS - {"retrieved_at", "selected"}
        keys = set(CANDIDATE_KEYS) if public and selected else raw_keys
        if temporal:
            keys |= {"true_from", "learned_at", "retrieved_at"}
        if field == "executives":
            keys |= {"title"}
        check(isinstance(item, dict) and set(item) == keys)
        check(type(item["value"]) is FIELDS.get(field, str) and item["kind"] in tuple(AUTHORITY))
        check(item["published_at"] is None or bool(publication_key(item["published_at"])))
        citations_are_valid([{name: item[name] for name in ("url", "provider", "excerpt")}])
        if field == "executives":
            check(item["title"] in TITLES)
        if public and selected:
            check(type(item["selected"]) is bool)
        if public or temporal:
            date_or_none(item["retrieved_at"])
        if temporal:
            check(item["true_from"] is None or day_key(item["true_from"]) is not None)
            check(isinstance(item["learned_at"], str) and bool(publication_key(item["learned_at"])))

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
            groups = GROUPS if record.get("schema_stage") == 3 else FIELDS
            check(isinstance(candidates, dict) and set(candidates) == set(groups))
            for field, values in candidates.items():
                check(isinstance(values, list))
                for item in values:
                    if record.get("schema_stage") in (2, 3):
                        candidate_is_valid(item, field, public=False)
                    else:
                        check(isinstance(item, dict) and type(item.get("value")) is FIELDS[field])
                        citations_are_valid(item.get("citations"))
                        check(bool(item["citations"]))
        check(isinstance(record.get("calls"), list))
        for call in record["calls"]:
            check(isinstance(call, dict) and call.get("provider") in PROVIDERS)
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
    check(isinstance(state, dict))
    stage = state.get("stage", 1)
    check(type(stage) is int and stage in (1, 2, 3))
    keys = set(empty_state())
    if stage != 3:
        keys -= {"changes", "next_seq"}
    if stage == 1:
        keys.remove("stage")
    check(set(state) == keys)
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

    def is_value(field, value):
        if value is None:
            return True
        if field != "executives":
            return type(value) is FIELDS[field]
        return isinstance(value, list) and 1 <= len(value) <= len(TITLES) and all(
            isinstance(member, dict) and set(member) == {"title", "name"}
            and member["title"] in TITLES and isinstance(member["name"], str) for member in value
        ) and [member["title"] for member in value] == [
            title for title in TITLES if any(member["title"] == title for member in value)
        ]

    def selected_fields_are_valid(fields, researched_at):
        check(isinstance(fields, dict) and set(fields) == set(ALL_FIELDS if stage == 3 else FIELDS))
        for field, result in fields.items():
            keys = {"value", "status", "citations"}
            if stage >= 2:
                keys.add("candidates")
            if stage == 3:
                keys |= {"true_from", "learned_at"}
            check(isinstance(result, dict) and set(result) == keys)
            value, status, citations = result["value"], result["status"], result["citations"]
            citations_are_valid(citations)
            check(is_value(field, value))
            check((value is None and status == "unknown" and not citations)
                  or (value is not None and status in (("known",) if stage == 1 else ("known", "contested"))
                      and bool(citations)))
            if stage == 3:
                check(result["true_from"] is None or day_key(result["true_from"]) is not None)
                check((result["learned_at"] is None and value is None)
                      or (value is not None and bool(publication_key(result["learned_at"]))))
            if stage >= 2:
                check(isinstance(result["candidates"], list))
                check(bool(result["candidates"]) == (value is not None))
                for item in result["candidates"]:
                    candidate_is_valid(item, field, public=True, temporal=stage == 3)
                    check(item["retrieved_at"] == researched_at)
                if stage == 2:
                    check(result == select({field: result["candidates"]}, researched_at)[field])

    def timeline_is_valid(dossier):
        timeline = dossier["timeline"]
        check(isinstance(timeline, dict) and set(timeline) == set(new_timeline()))
        check(isinstance(timeline["first_seen"], dict))
        check(all(publication_key(when) for when in timeline["first_seen"].values()))
        check(isinstance(timeline["builds"], list))
        prior = None
        for build in timeline["builds"]:
            check(isinstance(build, dict) and build.get("outcome") in ("ready", "failed"))
            time_key = publication_key(build.get("started_at"))
            check(time_key and (prior is None or time_key >= prior))
            prior = time_key
            check(type(build.get("spent_units")) is int and build["spent_units"] >= 0)
            keys = {"started_at", "outcome", "spent_units"}
            if build["outcome"] == "ready":
                keys |= {"fields", "versions"}
            check(set(build) == keys)
            if build["outcome"] == "failed":
                continue
            selected_fields_are_valid(build["fields"], build["started_at"])
            check(isinstance(build["versions"], dict))
            for url, version in build["versions"].items():
                check(isinstance(version, dict) and set(version) == {"true_from", "groups"})
                check(version["true_from"] is None or day_key(version["true_from"]) is not None)
                check(isinstance(version["groups"], dict) and set(version["groups"]) <= set(GROUPS))
                for group, items in version["groups"].items():
                    check(isinstance(items, list))
                    for item in items:
                        candidate_is_valid(item, group, public=False, temporal=True)
                        check(item["url"] == url and item["retrieved_at"] == build["started_at"]
                              and item["true_from"] == version["true_from"])
        check(sum(build["spent_units"] for build in timeline["builds"]) == dossier["spent_units"])
        ready = next((build for build in reversed(timeline["builds"]) if build["outcome"] == "ready"), None)
        check(dossier["fields"] == (ready["fields"] if ready else empty_fields()))
        check(dossier["researched_at"] == (ready["started_at"] if ready else None))
        history = timeline["history"]
        check(isinstance(history, dict) and set(history) == set(ALL_FIELDS))
        for field, entries in history.items():
            check(isinstance(entries, list))
            for entry in entries:
                check(isinstance(entry, dict) and set(entry) == {"value", "citations", "true_from", "learned_at", "type"})
                check(entry["type"] in ("initial", "change", "correction") and is_value(field, entry["value"]))
                check(entry["true_from"] is None or day_key(entry["true_from"]) is not None)
                check(bool(publication_key(entry["learned_at"])))
                citations_are_valid(entry["citations"])

    dossier_ids = set()
    for domain, dossier in state["dossiers"].items():
        check(domain_name(domain) == domain and isinstance(dossier, dict))
        keys = {"dossier_id", "domain", "state", "researched_at", "spent_units", "fields", "builds", "active"}
        check(set(dossier) == (keys | {"timeline"} if stage == 3 else keys))
        check(dossier["domain"] == domain and identifier(dossier["dossier_id"])
              and dossier["dossier_id"] not in dossier_ids)
        dossier_ids.add(dossier["dossier_id"])
        check(dossier["state"] in ("ready", "failed") and dossier["active"] is None)
        date_or_none(dossier["researched_at"])
        check(type(dossier["spent_units"]) is int and dossier["spent_units"] >= 0)
        selected_fields_are_valid(dossier["fields"], dossier["researched_at"])
        check(isinstance(dossier["builds"], list))
        for record in dossier["builds"]:
            audit(record, domain)
            check(record["dossier_id"] == dossier["dossier_id"])
        check(dossier["spent_units"] == sum(record["spent_units"] for record in dossier["builds"]))
        check(dossier["state"] == (dossier["builds"][-1]["outcome"] if dossier["builds"] else "failed"))
        ready = next((build for build in reversed(dossier["builds"]) if build["outcome"] == "ready"), None)
        check(dossier["researched_at"] == (ready["started_at"] if ready else None))
        if stage == 3:
            timeline_is_valid(dossier)
        elif ready is None:
            check(dossier["fields"] == (legacy_unknown_fields() if stage == 1 else unknown_fields()))
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
    if stage != 3:
        for dossier in state["dossiers"].values():
            upgrade(dossier, stage)
        state.update(stage=3, changes=[], next_seq=1)
    else:
        check(isinstance(state["changes"], list))
        check(type(state["next_seq"]) is int and state["next_seq"] == len(state["changes"]) + 1)
        for seq, entry in enumerate(state["changes"], start=1):
            check(isinstance(entry, dict) and set(entry) == {
                "seq", "domain", "field", "type", "from", "to", "true_from", "learned_at",
            })
            check(type(entry["seq"]) is int and entry["seq"] == seq)
            check(isinstance(entry["domain"], str) and entry["domain"] in state["dossiers"])
            check(entry["type"] in ("change", "correction") and entry["field"] in ALL_FIELDS)
            check(is_value(entry["field"], entry["from"]) and is_value(entry["field"], entry["to"]))
            check(bool(publication_key(entry["learned_at"])))
            check(entry["true_from"] is None or day_key(entry["true_from"]) is not None)
    return state


class Service:
    def __init__(self, gather_pages=gather, *, state_path=None):
        self.lock = threading.RLock()
        self.state_path = Path(state_path) if state_path else None
        if self.state_path:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if self.state_path and self.state_path.is_file():
            with self.state_path.open(encoding="utf-8") as saved:
                self.state = checked_export(json.load(saved))
        else:
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
            self.persist()
        return 204, None

    def set_clock(self, data):
        instant, now = timestamp(require(data, "now"))
        with self.lock:
            if instant < timestamp(self.now())[0]:
                invalid("The clock cannot move backwards")
            self.state["now"] = now
            self.persist()
        return 204, None

    def snapshot(self):
        state = {**self.state, "dossiers": dict(self.state["dossiers"]),
                 "interrupted_builds": list(self.state["interrupted_builds"])}
        for domain, dossier in self.state["dossiers"].items():
            active = dossier["active"]
            if active is not None:
                state["dossiers"][domain] = {
                    **dossier, "active": None, "state": active["previous_state"],
                    "spent_units": dossier["spent_units"] - active["spent_units"],
                }
                state["interrupted_builds"].append({
                    **{name: value for name, value in active.items() if name != "previous_state"},
                    "outcome": "interrupted",
                })
        return {"track": "dossier", "format_version": 1, "state": state}

    def export(self):
        with self.lock:
            return 200, copy.deepcopy(self.snapshot())

    def persist(self):
        """Publish a private, durable snapshot while the state lock is held."""
        if not self.state_path:
            return
        directory = self.state_path.parent
        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                             prefix=".dossier-", delete=False) as temporary:
                temporary_name = temporary.name
                json.dump(self.snapshot(), temporary, ensure_ascii=True, separators=(",", ":"))
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.state_path)
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)

    def import_state(self, packet):
        state = checked_export(packet)
        with self.lock:
            self.state = state
            self.persist()
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
        self.persist()
        return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def start_build(self, dossier):
        state = self.state
        record = {
            "build_id": opaque_id("b_"), "dossier_id": dossier["dossier_id"],
            "domain": dossier["domain"], "started_at": self.now(), "completed_at": None,
            "outcome": None, "spent_units": 0, "calls": [], "previous_state": dossier["state"],
            "schema_stage": 3,
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

        succeeded, dates, candidates = False, {}, {field: [] for field in GROUPS}
        try:
            succeeded, dates, candidates = self.gather_pages(record["domain"], current, observe)
        except Exception:
            # Provider data and exceptions may hold credentials, so log only a fixed message.
            logging.error("Dossier build encountered an unexpected internal error")
        with self.lock:
            if self.state is not state:
                return
            outcome = "ready" if succeeded else "failed"
            dossier["state"] = outcome
            record["outcome"] = outcome
            record["completed_at"] = self.now()
            record["elapsed_seconds"] = time.monotonic() - started
            record["candidates"] = candidates
            del record["previous_state"]
            dossier["builds"].append(record)
            dossier["active"] = None
            finish(state, dossier, record, candidates, dates)
            self.persist()

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
                "researched_at": None, "spent_units": 0, "fields": empty_fields(),
                "builds": [], "active": None, "timeline": new_timeline(),
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
        self.persist()
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

    def changes(self, query):
        since = list_number(query, "since", 0)
        limit = list_number(query, "limit", 50, 200)
        changes = self.state["changes"]
        # Feed sequence numbers are dense and one-indexed.
        return 200, {"changes": changes[since:since + limit], "has_more": since + limit < len(changes)}

    def dossier_read(self, domain, view, query):
        true_at = None
        if view == "values":
            true_at = query.get("true_at", [""])[0]
            if day_key(true_at) is None:
                invalid("true_at must be a YYYY-MM-DD date")
        as_of = None
        if view == "values" or (view is None and "as_of" in query):
            as_of = query["as_of"][0] if "as_of" in query else self.now()
            as_of_key = timestamp(as_of)[0]
        dossier = self.state["dossiers"].get(domain)
        if dossier is None:
            missing()
        if view == "history":
            entries = dossier["timeline"]["history"]
            return 200, {"domain": domain, "fields": {field: list(history) for field, history in entries.items()}}
        if as_of is None:
            return 200, public_dossier(dossier)
        records = through(dossier, as_of_key)
        ready = next((build for build in reversed(records) if build["outcome"] == "ready"), None)
        if ready is None:
            missing()
        if view == "values":
            return 200, {"domain": domain, "true_at": true_at, "as_of": as_of,
                         "fields": valid_values(records, true_at)}
        return 200, {**public_stub(dossier), "state": "ready", "fields": ready["fields"],
                     "researched_at": ready["started_at"], "spent_units": sum(build["spent_units"] for build in records)}

    def dispatch(self, method, target, headers, read_object):
        try:
            url = urlsplit(target)
        except ValueError:
            url = urlsplit("/")
        path = url.path
        if method in ("GET", "HEAD"):
            if path in WEB_ASSETS:
                return 200, WEB_ASSETS[path]
            if (path in ("/", "/login", "/signup", "/contested")
                    or re.fullmatch(r"/dossiers/[^/]+/evidence", path)
                    or (re.fullmatch(r"/dossiers/[^/]+", path) and accepts_html(headers.get("Accept", "")))):
                return 200, HTML
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
            if method == "GET" and path == "/changes":
                return self.changes(parse_qs(url.query, keep_blank_values=True))
            if method == "GET" and (match := re.fullmatch(r"/dossiers/([^/]+)(?:/(values|history))?", path)):
                return self.dossier_read(domain_name(unquote(match[1])), match[2],
                                         parse_qs(url.query, keep_blank_values=True))
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
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if re.fullmatch(r"/dossiers/[^/?]+(?:\?.*)?", getattr(self, "path", "")):
            self.send_header("Vary", "Accept")
        if status != 204:
            if isinstance(body, Asset):
                encoded = (WEB_ROOT / body.name).read_bytes()
                content_type = body.content_type
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            else:
                encoded = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            self.send_header("Content-Type", content_type)
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
    service = Service(state_path=os.environ.get("DOSSIER_STATE_PATH", "/data/dossier.json"))
    with Server(("0.0.0.0", int(os.environ.get("PORT", "8080"))), service) as server:
        server.serve_forever()
