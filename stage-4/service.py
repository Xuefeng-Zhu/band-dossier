"""Dossier Stage 4 HTTP API, durable budget ledger, and state lifecycle."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import scrypt
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
from threading import Lock, Thread
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from candidates import (AUTHORITY, PROVIDERS, empty_fields as stage_two_unknown_fields, normalized_host,
                        publication_time, select)
from evidence import EXECUTIVE_TITLES, FIELDS, INTEGER_FIELDS, unknown_fields as stage_one_unknown_fields
from research import Audit, LIMIT, gather, public_url
from store import Store
from temporal import (ALL_FIELDS, STAGE_THREE_FIELDS, at_or_before, choose, chronological_row, empty_fields,
                      empty_history, member_origins, migrate_dossier, page_versions, record_changes, timed_fields,
                      valid_date, values_at)


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
UI_ASSETS = {
    "/ui.css": ("ui.css", "text/css; charset=utf-8"),
    "/ui.js": ("ui.js", "text/javascript; charset=utf-8"),
}
UI_PAGE = ("index.html", "text/html; charset=utf-8")


def browser_resource(path, accept):
    if path in UI_ASSETS:
        return UI_ASSETS[path]
    if path in {"/", "/contested", "/signup", "/login"}:
        return UI_PAGE
    if path.startswith("/dossiers/") and path.endswith("/evidence"):
        return UI_PAGE
    if path.startswith("/dossiers/") and any(
        part.split(";", 1)[0].strip().lower() == "text/html"
        and not re.search(r";\s*q=0(?:\.0+)?(?:\s*;|\s*$)", part)
        for part in accept.split(",")
    ):
        return UI_PAGE
    return None


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


def same_json(left, right):
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


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
    return {"schema": 4, "users": {}, "tokens": {}, "dossiers": {}, "idempotency": [],
            "feed": [], "batches": {}, "pending": {}}


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


def validate_fields(fields, stage):
    expected_fields = ALL_FIELDS if stage == 4 else STAGE_THREE_FIELDS if stage == 3 else FIELDS
    require(type(fields) is dict and set(fields) == set(expected_fields))
    for field, entry in fields.items():
        keys = {"status", "value", "citations"}
        if stage >= 2:
            keys.add("candidates")
        if stage >= 3:
            keys.update(("true_from", "learned_at"))
        if stage == 4:
            keys.update(("origins", "corroborated", "corroborated_since"))
        require(type(entry) is dict and set(entry) == keys)
        value, citations = entry["value"], entry["citations"]
        require(type(citations) is list)
        expected_type = int if field in INTEGER_FIELDS else str
        if stage >= 2:
            records = entry["candidates"]
            require(type(records) is list)
            for record in records:
                record_keys = {
                    "value", "url", "provider", "excerpt", "kind", "published_at", "retrieved_at", "selected",
                }
                if stage >= 3:
                    record_keys.update(("true_from", "learned_at"))
                if stage == 4:
                    record_keys.add("origin")
                if field == "executives":
                    record_keys.add("title")
                require(type(record) is dict and set(record) == record_keys)
                require(type(record["value"]) is expected_type and record["provider"] in PROVIDERS
                        and record["kind"] in tuple(AUTHORITY) and public_url(record["url"]) is not None
                        and isinstance(record["excerpt"], str) and 1 <= len(record["excerpt"]) <= 500
                        and type(record["selected"]) is bool)
                require(record["published_at"] is None or publication_time(record["published_at"]) is not None)
                timestamp(record["retrieved_at"])
                if stage >= 3:
                    require(record["true_from"] is None or valid_date(record["true_from"]) is not None)
                    timestamp(record["learned_at"])
                if stage == 4:
                    require(isinstance(record["origin"], str) and normalized_host(record["origin"]) == record["origin"])
                if field == "executives":
                    require(record["title"] in EXECUTIVE_TITLES)
            if stage >= 3:
                learned = entry["learned_at"]
                if value is not None:
                    timestamp(learned)
                else:
                    require(learned is None)
                selected = {**choose(field, records), "learned_at": learned}
                if stage == 4:
                    origins = member_origins(field, selected)
                    standing = entry["corroborated_since"]
                    if standing is not None:
                        timestamp(standing)
                        require(bool(origins))
                    require(type(entry["corroborated"]) is bool)
                    selected.update(origins=sorted(set().union(*origins.values())),
                                    corroborated=bool(origins) and all(len(value) >= 2 for value in origins.values()),
                                    corroborated_since=standing)
                require(entry == selected)
            else:
                require(entry == select(records))
        if value is None:
            require(entry["status"] == "unknown" and not citations)
            continue
        require(entry["status"] in (("known",) if stage == 1 else ("known", "contested")) and bool(citations))
        require(type(value) is (list if field in ("executives", "investors") else expected_type))
        for citation in citations:
            require(type(citation) is dict and set(citation) == {"url", "provider", "excerpt"})
            require(isinstance(citation["url"], str) and citation["provider"] in PROVIDERS
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
        require(isinstance(page.get("text"), str) and public_url(page.get("url")) is not None
                and page.get("provider") in PROVIDERS
                and page.get("scope") in ("search", "search_snippet", "citation", "rendered", "lineage")
                and nonnegative(page.get("call_id")) and page["call_id"] < len(audit["calls"]))
    for answer in audit["research_answers"]:
        claims = answer.get("claims")
        require(type(claims) is list and all(type(claim) is dict for claim in claims))
        for key in ("call_id", "start_call_id"):
            require(nonnegative(answer.get(key)) and answer[key] < len(audit["calls"]))


def validate_timeline(dossier, stage):
    timeline = dossier["timeline"]
    history = dossier["history"]
    require(type(timeline) is list and type(history) is dict
            and set(history) == set(ALL_FIELDS if stage == 4 else STAGE_THREE_FIELDS))
    latest = None
    for row in timeline:
        row_keys = {"id", "started_at", "spent_units", "outcome", "fields", "versions"}
        require(type(row) is dict)
        if stage == 4 and "standing_reset" in row:
            require(row["standing_reset"] is True and row.get("outcome") == "ready")
            row_keys.add("standing_reset")
        require(set(row) == row_keys)
        require(valid_id(row["id"]) and nonnegative(row["spent_units"]) and row["outcome"] in ("ready", "failed"))
        timestamp(row["started_at"])
        if row["outcome"] == "ready":
            latest = row
            validate_fields(row["fields"], stage)
            require(type(row["versions"]) is dict and all(
                public_url(url) is not None and (value is None or valid_date(value) is not None)
                for url, value in row["versions"].items()
            ))
        else:
            require(row["fields"] is None and row["versions"] is None)
    require(sum(row["spent_units"] for row in timeline) == dossier["spent_units"])
    require(dossier["fields"] == (latest["fields"] if latest else empty_fields(stage)))
    require(dossier["researched_at"] == (latest["started_at"] if latest else None))
    for entries in history.values():
        require(type(entries) is list)
        for item in entries:
            require(type(item) is dict and set(item) == {"type", "value", "true_from", "learned_at", "citations"})
            require(item["type"] in ("initial", "change", "correction") and type(item["citations"]) is list)
            require(item["true_from"] is None or valid_date(item["true_from"]) is not None)
            timestamp(item["learned_at"])


def validate_dossier(domain, dossier, stage):
    require(domain == domain_name(domain) and type(dossier) is dict)
    keys = {"dossier_id", "state", "researched_at", "spent_units", "fields", "builds"}
    require(set(dossier) == (keys | {"timeline", "history"} if stage >= 3 else keys))
    require(valid_id(dossier["dossier_id"]) and dossier["state"] in ("ready", "failed"))
    require(nonnegative(dossier["spent_units"]) and type(dossier["builds"]) is list)
    validate_fields(dossier["fields"], stage)
    latest_ready = None
    for build in dossier["builds"]:
        validate_build(build)
        if build["outcome"] == "ready":
            latest_ready = build
    builds = dossier["builds"]
    require(dossier["state"] == (builds[-1]["outcome"] if builds else "failed"))
    require(dossier["spent_units"] == sum(build["spent_units"] for build in builds))
    require(dossier["researched_at"] == (latest_ready["started_at"] if latest_ready else None))
    if latest_ready is None:
        empty = {1: stage_one_unknown_fields, 2: stage_two_unknown_fields,
                 3: lambda: empty_fields(3), 4: empty_fields}[stage]
        require(dossier["fields"] == empty())
    if stage >= 3:
        validate_timeline(dossier, stage)
    if stage < 4:
        migrate_dossier(domain, dossier, stage)


def import_state(body):
    if body.get("track") != "dossier" or type(body.get("format_version")) is not int or body["format_version"] != 1:
        raise invalid("Invalid snapshot track or version")
    state = body.get("state")
    require(type(state) is dict)
    stage = state.get("schema", 1)
    require(type(stage) is int and stage in (1, 2, 3, 4))
    keys = set(empty_state()) - ({"batches", "pending"} if stage < 4 else set())
    expected = (keys - {"feed", "schema"}) if stage == 1 else (keys - {"feed"} if stage == 2 else keys)
    require(set(state) == expected)
    if stage < 4:
        state = deepcopy(state)
    users, tokens, dossiers, idempotency = (state[key] for key in ("users", "tokens", "dossiers", "idempotency"))
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
        validate_dossier(domain, dossier, stage)
    if stage < 4:
        state.update(schema=4, batches={}, pending={})
    require(state["pending"] == {} and type(state["batches"]) is dict)
    for batch_id, batch in state["batches"].items():
        require(valid_id(batch_id) and type(batch) is dict
                and set(batch) == {"owner", "domains", "budget_units", "spent_units"})
        require(isinstance(batch["owner"], str) and batch["owner"] in ids)
        require(type(batch["domains"]) is list and 1 <= len(batch["domains"]) <= 50
                and all(isinstance(domain, str) and domain in dossiers for domain in batch["domains"])
                and len(set(batch["domains"])) == len(batch["domains"]))
        require(nonnegative(batch["spent_units"]) and type(batch["budget_units"]) is int
                and 1 <= batch["budget_units"] <= 100000 and batch["spent_units"] <= batch["budget_units"])
    keys = set()
    for entry in idempotency:
        require(type(entry) is dict and set(entry) == {"user_id", "path", "key", "body", "status", "response"})
        user_id, path, key = (entry[field] for field in ("user_id", "path", "key"))
        require(all(isinstance(value, str) for value in (user_id, path, key)))
        require(user_id in ids and 1 <= len(key) <= 255 and (user_id, path, key) not in keys)
        require(type(entry["body"]) is dict and entry["status"] in (200, 202))
        replay = entry["response"]
        if unquote(path) == "/batches":
            require(type(replay) is dict and set(replay) == {"batch_id", "state", "budget_units", "spent_units", "dossiers"})
            batch_id = replay["batch_id"]
            require(valid_id(batch_id) and batch_id in state["batches"] and entry["status"] == 202)
            batch = state["batches"][batch_id]
            require(batch["owner"] == user_id and replay["state"] in ("running", "done")
                    and replay["spent_units"] == 0 and replay["budget_units"] == batch["budget_units"]
                    and type(replay["dossiers"]) is list and len(replay["dossiers"]) == len(batch["domains"]))
            for item, domain in zip(replay["dossiers"], batch["domains"]):
                require(type(item) is dict and set(item) == {"domain", "state"} and item["domain"] == domain
                        and item["state"] in ("building", "ready", "failed"))
            keys.add((user_id, path, key))
            continue
        require(type(replay) is dict and set(replay) == {"dossier_id", "domain", "state"})
        require(valid_id(replay["dossier_id"]) and replay["state"] in ("building", "ready", "failed"))
        require(isinstance(replay["domain"], str) and replay["domain"] in dossiers
                and replay["dossier_id"] == dossiers[replay["domain"]]["dossier_id"])
        keys.add((user_id, path, key))
    if stage < 3:
        state["feed"] = []
    feed = state["feed"]
    require(type(feed) is list)
    for seq, item in enumerate(feed, 1):
        require(type(item) is dict and set(item) == {"seq", "domain", "field", "type", "from",
                                                   "to", "true_from", "learned_at"})
        require(type(item["seq"]) is int and item["seq"] == seq and isinstance(item["domain"], str)
                and item["domain"] in dossiers and item["field"] in ALL_FIELDS
                and item["type"] in ("change", "correction"))
        require(item["true_from"] is None or valid_date(item["true_from"]) is not None)
        timestamp(item["learned_at"])
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
    def __init__(self, state_path=None):
        self.lock = Lock()
        self.store = Store(state_path) if state_path is not None else None
        saved = self.store.load() if self.store else None
        self.clock = timestamp(saved["clock"]) if saved and saved["clock"] else None
        self.state = saved["state"] if saved else empty_state()
        self.replays = self.replay_index()
        self.jobs = {}
        self.workers = {}
        if self.state["pending"]:
            self.recover_pending()
        elif self.store and not saved:
            self.persist()
        self.loop = asyncio.new_event_loop()
        Thread(target=self.loop.run_forever, daemon=True).start()

    def now(self):
        return self.clock if self.clock is not None else datetime.now(timezone.utc)

    def replay_index(self):
        return {(entry["user_id"], entry["path"], entry["key"]): entry
                for entry in self.state["idempotency"]}

    def persist(self, observed=None):
        if self.store:
            self.store.save(self.state, (observed or self.now()).isoformat())

    def replace(self, state, now=None):
        with self.lock:
            previous = self.workers
            self.jobs = {}
            self.workers = {}
            self.state = state
            self.replays = self.replay_index()
            if now is not None:
                self.clock = now
            self.persist()
            for worker in previous.values():
                worker.cancel()

    def session(self, user):
        token = secrets.token_urlsafe(32)
        self.state["tokens"][token] = user["id"]
        self.persist()
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

    def batch_available(self, batch_id):
        if batch_id is None:
            return LIMIT
        batch = self.state["batches"][batch_id]
        reserved = sum(sum(job["reservations"].values()) for job in self.state["pending"].values()
                       if job["batch_id"] == batch_id)
        return batch["budget_units"] - batch["spent_units"] - reserved

    def reserve(self, domain, job, call, cost, audit):
        with self.lock:
            if (self.jobs.get(domain) is not job or cost > self.batch_available(job["batch_id"])
                    or job["spent_units"] + sum(job["reservations"].values()) + cost > LIMIT):
                return False
            job["reservations"][str(call)] = cost
            job["audit"] = deepcopy(audit)
            self.persist()
            return True

    def settle(self, domain, job, call, units, audit):
        with self.lock:
            if self.jobs.get(domain) is not job:
                return
            job["reservations"].pop(str(call))
            job["spent_units"] += units
            if job["batch_id"]:
                self.state["batches"][job["batch_id"]]["spent_units"] += units
            job["audit"] = deepcopy(audit)
            self.persist()

    def checkpoint(self, domain, job, audit):
        with self.lock:
            if self.jobs.get(domain) is job:
                job["audit"] = deepcopy(audit)
                self.persist()

    def detached_available(self, domain, job):
        with self.lock:
            return self.batch_available(job["batch_id"]) if self.jobs.get(domain) is job else -1

    def finish_build(self, domain, job, audit, raw_fields=None):
        complete = raw_fields is not None
        outcome = "ready" if complete else "failed"
        dossier = self.state["dossiers"][domain]
        dossier["state"] = outcome
        dossier["spent_units"] += job["spent_units"]
        build = {
            "id": job["id"], "started_at": job["started_at"], "completed_at": self.now().isoformat(),
            "outcome": outcome, "spent_units": job["spent_units"], "audit": audit,
        }
        dossier["builds"].append(build)
        if complete:
            versions = page_versions(audit["pages"], legacy=False)
            selected = timed_fields(raw_fields, versions, build["started_at"], dossier["timeline"])
            record_changes(domain, dossier, selected, build["started_at"], self.state["feed"])
            dossier["timeline"].append(chronological_row(build, selected, versions))
            dossier.update(fields=selected, researched_at=job["started_at"])
        else:
            dossier["timeline"].append(chronological_row(build))

    def recover_pending(self):
        for domain, job in self.state["pending"].items():
            # Each outbound call was reserved before dispatch. Its exact charge
            # can be unknown after an abrupt stop, so retain the reservation.
            for call_id, cost in job["reservations"].items():
                call = job["audit"]["calls"][int(call_id)]
                call.update(outcome="interrupted", spent_units=cost)
                job["spent_units"] += cost
                if job["batch_id"]:
                    self.state["batches"][job["batch_id"]]["spent_units"] += cost
            self.finish_build(domain, job, job["audit"])
        self.state["pending"] = {}
        self.persist()

    async def run_build(self, domain, job):
        def active():
            with self.lock:
                return self.jobs.get(domain) is job

        audit = Audit(active, lambda call, cost, data: self.reserve(domain, job, call, cost, data),
                      lambda call, units, data: self.settle(domain, job, call, units, data),
                      lambda data: self.checkpoint(domain, job, data),
                      lambda: self.detached_available(domain, job))
        try:
            fields = await gather(domain, audit, job["started_at"])
        except asyncio.CancelledError:
            return
        except Exception as error:
            print(f"Dossier build error: {type(error).__name__}", flush=True)
            fields = stage_two_unknown_fields()
        complete = any(call.get("outcome") in ("success", "no_page") for call in audit.calls)
        with self.lock:
            if self.jobs.get(domain) is not job:
                return
            self.finish_build(domain, job, audit.output(), fields if complete else None)
            del self.jobs[domain]
            del self.state["pending"][domain]
            self.workers.pop(domain, None)
            self.persist()

    def start_build(self, domain, received, batch_id=None):
        job = {"id": "b_" + uuid4().hex, "started_at": received.isoformat(), "spent_units": 0,
               "batch_id": batch_id, "reservations": {},
               "audit": {"calls": [], "pages": [], "research_answers": []}}
        self.jobs[domain] = job
        self.state["pending"][domain] = job
        self.workers[domain] = asyncio.run_coroutine_threadsafe(self.run_build(domain, job), self.loop)

    def summary(self, domain, dossier):
        return {"dossier_id": dossier["dossier_id"], "domain": domain,
                "state": "building" if domain in self.jobs else dossier["state"]}

    def dossier_body(self, domain, dossier):
        job = self.jobs.get(domain)
        return {**self.summary(domain, dossier), "researched_at": dossier["researched_at"],
                "spent_units": dossier["spent_units"] + (job["spent_units"] if job else 0)}

    def new_dossier(self, domain):
        dossier = {"dossier_id": "d_" + uuid4().hex, "state": "failed", "researched_at": None,
                   "spent_units": 0, "fields": empty_fields(), "builds": [],
                   "history": empty_history(), "timeline": []}
        self.state["dossiers"][domain] = dossier
        return dossier

    def batch_body(self, batch_id, batch):
        running = any(job["batch_id"] == batch_id for job in self.jobs.values())
        return {"batch_id": batch_id, "state": "running" if running else "done",
                "budget_units": batch["budget_units"], "spent_units": batch["spent_units"],
                "dossiers": [{"domain": domain, "state": self.summary(domain, self.state["dossiers"][domain])["state"]}
                             for domain in batch["domains"]]}

    def start_batch(self, user_id, body, received):
        supplied = member(body, "domains", list)
        if not 1 <= len(supplied) <= 50:
            raise invalid("A batch needs one to fifty domains")
        if not all(isinstance(domain, str) for domain in supplied):
            raise invalid("Invalid company domain")
        domains = [domain_name(domain) for domain in supplied]
        if len(set(domains)) != len(domains):
            raise invalid("Batch domains must be distinct")
        budget = body.get("budget_units")
        if type(budget) is not int or not 1 <= budget <= 100000:
            raise invalid("A batch budget must be an integer from 1 to 100000")
        batch_id = "b_" + uuid4().hex
        batch = {"owner": user_id, "domains": domains, "budget_units": budget, "spent_units": 0}
        self.state["batches"][batch_id] = batch
        for domain in domains:
            if domain not in self.state["dossiers"]:
                self.new_dossier(domain)
                self.start_build(domain, received, batch_id)
        return self.batch_body(batch_id, batch)

    def write(self, user_id, path, raw_path, body, key, received):
        recognized = ("domains", "budget_units") if path == "/batches" else ("domain",)
        comparison = {field: body[field] for field in recognized if field in body}
        scope = (user_id, raw_path, key)
        if existing := self.replays.get(scope):
            if not same_json(comparison, existing["body"]):
                raise ApiError(409, "idempotency_key_reuse", "Key was used for a different body")
            return 200, existing["response"]
        if path == "/batches":
            response = self.start_batch(user_id, body, received)
            status = 202
        elif path == "/dossiers":
            domain = domain_name(member(body, "domain"))
            dossier = self.state["dossiers"].get(domain)
            status = 200
            if dossier is None:
                dossier = self.new_dossier(domain)
                self.start_build(domain, received)
                status = 202
            response = self.summary(domain, dossier)
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
        self.persist()
        return status, response

    def read_dossier(self, path, query):
        name = path[len("/dossiers/"):]
        operation = None
        if "/" in name:
            possible_name, possible_operation = name.rsplit("/", 1)
            if possible_operation in {"values", "history"}:
                name, operation = possible_name, possible_operation
        domain = domain_name(name)
        if operation == "values":
            true_at = valid_date(query.get("true_at", [None])[0])
            if true_at is None:
                raise invalid("true_at must be a YYYY-MM-DD date")
        as_of = None
        observed = None
        if operation == "values" or ("as_of" in query and operation is None):
            if "as_of" in query:
                as_of = query["as_of"][0]
            else:
                observed = self.now()
                as_of = observed.isoformat()
            timestamp(as_of)
        dossier = self.state["dossiers"].get(domain)
        if dossier is None:
            raise not_found()
        if operation == "history":
            return 200, {"domain": domain, "fields": deepcopy(dossier["history"])}
        if as_of is None:
            return 200, {**self.dossier_body(domain, dossier), "fields": dossier["fields"]}
        timeline = at_or_before(dossier["timeline"], as_of)
        snapshot = next((build for build in reversed(timeline) if build["outcome"] == "ready"), None)
        if snapshot is None:
            raise not_found()
        if operation == "values":
            if observed is not None and self.clock is None:
                # A fresh service follows the wall clock until it is set.
                # Retain the last timestamp exposed to callers on restart.
                self.persist(observed)
            return 200, {"domain": domain, "true_at": true_at, "as_of": as_of,
                         "fields": values_at(timeline, true_at)}
        spent = sum(build["spent_units"] for build in timeline)
        job = self.jobs.get(domain)
        if job and publication_time(job["started_at"]) <= publication_time(as_of):
            spent += job["spent_units"]
        return 200, {"dossier_id": dossier["dossier_id"], "domain": domain, "state": "ready",
                     "researched_at": snapshot["started_at"], "spent_units": spent, "fields": snapshot["fields"]}

    def read(self, path, query):
        if path == "/changes":
            since = query_integer(query, "since", 0, 0)
            limit = query_integer(query, "limit", 50, 1, 200)
            feed = self.state["feed"]
            return 200, {"changes": feed[since:since + limit], "has_more": len(feed) > since + limit}
        if path != "/dossiers":
            return self.read_dossier(path, query)
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
                stable = {**self.state, "pending": {}}
                return 200, {"track": "dossier", "format_version": 1, "state": deepcopy(stable)}
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
                self.persist()
            return 204, None
        if method == "POST" and path in ("/auth/signup", "/auth/login"):
            return self.auth(path, read_body())
        if path.startswith("/_test/"):
            raise not_found()
        with self.lock:
            user_id = self.authenticated_user(headers.get("Authorization"))
            if method == "GET" and path.startswith("/batches/"):
                batch_id = path[len("/batches/"):]
                batch = self.state["batches"].get(batch_id)
                if not batch or batch["owner"] != user_id:
                    raise not_found()
                return 200, self.batch_body(batch_id, batch)
            if method == "GET" and (path in {"/dossiers", "/changes"} or path.startswith("/dossiers/")):
                return self.read(path, parse_qs(parts.query, keep_blank_values=True))
        refresh = path.startswith("/dossiers/") and path.endswith("/refresh")
        if method != "POST" or (path not in {"/dossiers", "/batches"} and not refresh):
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
            if self.command in {"GET", "HEAD"}:
                resource = browser_resource(self.path.partition("?")[0], self.headers.get("Accept", ""))
                if resource:
                    self.send_browser(*resource)
                    return
            if self.path.split("?", 1)[0] in ("/_test/reset", "/_test/export", "/_test/import"):
                self.connection.settimeout(10)
            status, body = self.server.service.request(self.command, self.path, self.headers, self.read_body)
        except ApiError as error:
            status, body = error.status, error.body
        try:
            self.send_json(status, body)
        except (ConnectionError, TimeoutError):
            pass

    def send_browser(self, filename, content_type):
        content = Path(__file__).with_name(filename).read_bytes()
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if self.command != "HEAD":
                self.wfile.write(content)
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
        self.service = Service(os.environ.get("DOSSIER_STATE_FILE", "dossier.sqlite3"))
        super().__init__(address, Handler)


if __name__ == "__main__":
    with Server(("0.0.0.0", int(os.environ.get("PORT", "8080")))) as server:
        server.serve_forever()
