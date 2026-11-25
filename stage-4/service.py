"""Dossier HTTP service and durable state transitions."""

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
from bisect import bisect_right
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, unquote, urlsplit

from budgets import BuildLedger
from evidence import (
    AUTHORITY, EXECUTIVE_PHRASES, FIELDS, PHRASES, PROVIDERS, RANGES, field_from_candidates,
    parse_timestamp, public_url,
)
from research import gather
from lineage import normalized_domain
from temporal import (
    blank_fields, corroboration, date_text, display_field, effective_fields, migrate_dossier,
    migrate_stage_three, qualifying_builds, selected_snapshot, snapshot_for_build, updates,
)


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
    normalized = normalized_domain(value)
    if normalized is None:
        bad("Expected a valid host name.")
    return normalized


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
            "researched_at": None, "spent_units": 0, "fields": blank_fields(), "builds": [],
            "timeline": [], "history": {field: [] for field in FIELDS}}


def new_state(users=None):
    return {
        "users": {} if users is None else users, "sessions": {}, "dossiers": {}, "replays": [],
        "changes": [], "batches": {},
    }


def require(condition):
    if not condition:
        bad("The imported state is invalid.")


def valid_id(value):
    return isinstance(value, str) and 1 <= len(value) <= 64


def interrupt(record, reservations):
    for index, units in reservations.items():
        record["calls"][int(index)].update(response="interrupted", spent_units=units)
    record["spent_units"] += sum(reservations.values())


def batch_request(body):
    domains = body.get("domains", MISSING)
    if domains is MISSING:
        bad("domains is required.")
    if not isinstance(domains, list):
        malformed("domains must be an array.")
    if not 1 <= len(domains) <= 50:
        bad("Supply between 1 and 50 domains.")
    if not all(isinstance(domain, str) for domain in domains):
        malformed("Each domain must be a string.")
    domains = [normal_domain(domain) for domain in domains]
    if len(set(domains)) != len(domains):
        bad("Domains must be unique after normalization.")
    budget = body.get("budget_units")
    if type(budget) is not int or not 1 <= budget <= 100000:
        bad("budget_units must be an integer between 1 and 100000.")
    return domains, budget


def validate_field_value(field, value):
    if field == "investors":
        require(isinstance(value, list) and bool(value) and all(isinstance(name, str) and name for name in value))
        require(value == sorted(set(value)))
    elif field == "executives":
        require(isinstance(value, list) and bool(value))
        titles = []
        for member in value:
            require(isinstance(member, dict) and member.keys() == {"title", "name"})
            require(isinstance(member["title"], str) and member["title"] in EXECUTIVE_PHRASES
                    and isinstance(member["name"], str)
                    and bool(member["name"]))
            titles.append(member["title"])
        require(titles == [title for title in EXECUTIVE_PHRASES if title in titles])
    elif field in {"funding_total", "founded_year"}:
        require(type(value) is int)
    elif field == "headcount_range":
        require(isinstance(value, str) and value in HEADCOUNTS)
    else:
        require(isinstance(value, str) and bool(value))


def validate_citation(item):
    require(public_url(item["url"]) and item["provider"] in PROVIDERS)
    require(isinstance(item["excerpt"], str) and 1 <= len(item["excerpt"]) <= 500)


def validate_fields(fields, legacy=False, temporal=False, modern=False):
    names = FIELDS if modern else FIELDS[:-1] if temporal else PHRASES
    require(isinstance(fields, dict) and fields.keys() == set(names))
    shape = {"value", "status", "citations"} if legacy else {"value", "status", "citations", "candidates"}
    if temporal:
        shape |= {"true_from", "learned_at"}
    if modern:
        shape |= {"origins", "corroborated", "corroborated_since"}
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
            candidate_shape = {"value", "url", "excerpt", "provider", "kind", "published_at",
                               "retrieved_at", "selected"}
            if temporal:
                candidate_shape |= {"true_from", "learned_at"}
            if modern:
                candidate_shape.add("origin")
            if field == "executives":
                candidate_shape.add("title")
            for candidate in candidates:
                require(isinstance(candidate, dict) and candidate.keys() == candidate_shape)
                validate_citation(candidate)
                if field in ("executives", "investors"):
                    if field == "executives":
                        require(isinstance(candidate["title"], str) and candidate["title"] in EXECUTIVE_PHRASES)
                    require(isinstance(candidate["value"], str) and bool(candidate["value"]))
                else:
                    validate_field_value(field, candidate["value"])
                kind = candidate["kind"]
                require(kind is None or isinstance(kind, str) and kind in AUTHORITY)
                if candidate["published_at"] is not None:
                    timestamp(candidate["published_at"])
                timestamp(candidate["retrieved_at"])
                if temporal:
                    timestamp(candidate["learned_at"])
                    require(candidate["true_from"] is None or date_text(candidate["true_from"]))
                if modern:
                    require(isinstance(candidate["origin"], str) and checked_domain(candidate["origin"]))
                require(type(candidate["selected"]) is bool)
            if temporal:
                if value is None:
                    require(item["learned_at"] is None)
                else:
                    timestamp(item["learned_at"])
                require({key: val for key, val in item.items() if key not in
                         {"learned_at", "origins", "corroborated", "corroborated_since"}}
                        == display_field(field, candidates))
            else:
                require(item == field_from_candidates(candidates))
        if value is not None:
            validate_field_value(field, value)
        if modern:
            origins = corroboration(field, item, (), item["learned_at"])
            require(item["origins"] == origins["origins"] and type(item["corroborated"]) is bool
                    and item["corroborated"] == origins["corroborated"])
            if item["corroborated_since"] is not None:
                require(value is not None)
                timestamp(item["corroborated_since"])
        for citation in citations:
            require(isinstance(citation, dict) and citation.keys() == {"url", "provider", "excerpt"})
            validate_citation(citation)


def validate_timeline(dossier, raw_builds, modern):
    timeline, history = dossier["timeline"], dossier["history"]
    names = FIELDS if modern else FIELDS[:-1]
    require(isinstance(timeline, list) and isinstance(history, dict) and history.keys() == set(names))
    known_ids = set()
    spend = 0
    previous_index = -1
    for event in timeline:
        require(isinstance(event, dict) and event.keys() ==
                {"id", "started_at", "outcome", "spent_units", "fields", "versions"})
        require(valid_id(event["id"]) and event["id"] in raw_builds and event["id"] not in known_ids)
        index, build = raw_builds[event["id"]]
        require(index > previous_index and event["started_at"] == build["started_at"]
                and event["outcome"] == build["outcome"])
        previous_index = index
        known_ids.add(event["id"])
        require(type(event["spent_units"]) is int and event["spent_units"] >= build["spent_units"])
        spend += event["spent_units"]
        versions = event["versions"]
        require(isinstance(versions, dict) and all(
            public_url(url) and (value is None or date_text(value)) for url, value in versions.items()
        ))
        if event["outcome"] == "ready":
            validate_fields(event["fields"], temporal=True, modern=modern)
            require(all(
                item["url"] in versions and item["true_from"] == versions[item["url"]]
                and item["retrieved_at"] == event["started_at"]
                for field in event["fields"].values() for item in field["candidates"]
            ))
        else:
            require(event["fields"] is None and not versions)
    require(spend == dossier["spent_units"])
    latest = selected_snapshot(timeline)
    if latest:
        require(dossier["fields"] == latest["fields"])
    else:
        require(all(field["value"] is None and not field["candidates"] for field in dossier["fields"].values()))
    require(dossier["researched_at"] == (latest["started_at"] if latest else None))
    for field, entries in history.items():
        require(isinstance(entries, list))
        for index, entry in enumerate(entries):
            require(isinstance(entry, dict) and entry.keys() ==
                    {"type", "value", "true_from", "learned_at", "citations"})
            require(entry["type"] in (("initial", "change", "correction") if index == 0 else ("change", "correction")))
            timestamp(entry["learned_at"])
            require(entry["true_from"] is None or date_text(entry["true_from"]))
            require(isinstance(entry["citations"], list))
            if entry["value"] is not None:
                validate_field_value(field, entry["value"])
            for citation in entry["citations"]:
                require(isinstance(citation, dict) and citation.keys() == {"url", "excerpt", "provider"})
                validate_citation(citation)


def validate_feed(state):
    feed = state["changes"]
    require(isinstance(feed, list))
    previous = 0
    for entry in feed:
        require(isinstance(entry, dict) and entry.keys() ==
                {"seq", "domain", "field", "type", "from", "to", "true_from", "learned_at"})
        require(type(entry["seq"]) is int and entry["seq"] > previous)
        previous = entry["seq"]
        require(isinstance(entry["domain"], str) and entry["domain"] in state["dossiers"])
        require(entry["field"] in FIELDS and entry["type"] in ("change", "correction"))
        require(entry["from"] != entry["to"] and (entry["true_from"] is None or date_text(entry["true_from"])))
        for value in (entry["from"], entry["to"]):
            if value is not None:
                validate_field_value(entry["field"], value)
        timestamp(entry["learned_at"])


def validate_snapshot(value):
    require(isinstance(value, dict) and value.get("track") == "dossier")
    require(type(value.get("format_version")) is int and value["format_version"] == 1)
    state = value.get("state")
    require(isinstance(state, dict))
    current = "changes" in state
    modern = "batches" in state
    required = new_state().keys()
    require(state.keys() == (required if modern else required - {"batches"} if current
                             else required - {"batches", "changes"}))
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
    dossier_shape = new_dossier("").keys()
    for domain, dossier in state["dossiers"].items():
        require(isinstance(dossier, dict) and dossier.keys() ==
                (dossier_shape if current else dossier_shape - {"timeline", "history"}))
        require(checked_domain(domain) == dossier["domain"] and valid_id(dossier["dossier_id"]))
        require(dossier["dossier_id"] not in dossier_ids and dossier["state"] in ("ready", "failed"))
        dossier_ids.add(dossier["dossier_id"])
        fields = dossier["fields"]
        require(isinstance(fields, dict))
        legacy = not current and all(isinstance(field, dict) and "candidates" not in field for field in fields.values())
        validate_fields(fields, legacy, temporal=current, modern=modern)
        require(isinstance(dossier["builds"], list))
        require(type(dossier["spent_units"]) is int and dossier["spent_units"] >= 0)
        spend = 0
        last_ready = None
        outcome = "failed"
        builds = {}
        for index, build in enumerate(dossier["builds"]):
            require(isinstance(build, dict) and build.keys() == {
                "id", "started_at", "completed_at", "elapsed_ms", "outcome", "spent_units", "calls",
                "pages", "claims",
            })
            require(valid_id(build["id"]) and build["id"] not in builds)
            builds[build["id"]] = (index, build)
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
                require(call.get("provider") == "nimble" and isinstance(call.get("argument"), dict)
                        and isinstance(call.get("operation"), str))
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
        if current:
            validate_timeline(dossier, builds, modern)
            if not modern:
                state["dossiers"][domain] = migrate_stage_three(dossier)
        else:
            state["dossiers"][domain] = migrate_dossier(dossier, stage_one=legacy)
    if current:
        validate_feed(state)
    else:
        state["changes"] = []
    if not modern:
        state["batches"] = {}
    require(isinstance(state["batches"], dict))
    for batch_id, batch in state["batches"].items():
        require(isinstance(batch, dict) and batch.keys() ==
                {"batch_id", "owner", "domains", "pending", "budget_units", "spent_units"})
        require(valid_id(batch_id) and batch["batch_id"] == batch_id)
        require(isinstance(batch["owner"], str) and batch["owner"] in user_ids)
        budget, spend = batch["budget_units"], batch["spent_units"]
        require(type(budget) is int and 1 <= budget <= 100000 and type(spend) is int and 0 <= spend <= budget)
        domains = batch["domains"]
        require(isinstance(domains, list) and 1 <= len(domains) <= 50
                and all(isinstance(domain, str) and domain in state["dossiers"] for domain in domains))
        require(len(set(domains)) == len(domains) and isinstance(batch["pending"], list))
        require(all(isinstance(domain, str) and domain in domains for domain in batch["pending"])
                and len(set(batch["pending"])) == len(batch["pending"]))
    replays = set()
    for replay in state["replays"]:
        require(isinstance(replay, list) and len(replay) == 5)
        owner, path, key, body, response = replay
        require(isinstance(owner, str) and owner in user_ids and isinstance(path, str))
        require(isinstance(key, str) and 1 <= len(key) <= 255 and isinstance(body, dict))
        require((owner, path, key) not in replays)
        replays.add((owner, path, key))
        if path == "/batches":
            require(isinstance(response, dict) and response.keys() ==
                    {"batch_id", "state", "budget_units", "spent_units", "dossiers"})
            ident = response["batch_id"]
            require(isinstance(ident, str) and ident in state["batches"])
            batch = state["batches"][ident]
            require(batch["owner"] == owner and response["state"] in ("running", "done")
                    and response["spent_units"] == 0 and response["budget_units"] == batch["budget_units"])
            require(isinstance(response["dossiers"], list) and len(response["dossiers"]) == len(batch["domains"]))
            for domain, item in zip(batch["domains"], response["dossiers"]):
                require(isinstance(item, dict) and item.keys() == {"domain", "state"}
                        and item["domain"] == domain and item["state"] in ("building", "ready", "failed"))
            try:
                require(batch_request(body) == (batch["domains"], batch["budget_units"]))
            except Problem:
                bad("Invalid imported batch replay.")
            continue
        require(isinstance(response, dict) and response.keys() == {"dossier_id", "domain", "state"})
        domain = response["domain"]
        require(isinstance(domain, str) and domain in state["dossiers"])
        require(response["dossier_id"] == state["dossiers"][domain]["dossier_id"])
        require(response["state"] in ("building", "ready", "failed"))
        if path == "/dossiers":
            require(body.keys() == {"domain"} and isinstance(body["domain"], str))
            require(normal_domain(body["domain"]) == domain)
        else:
            require(path.startswith("/dossiers/") and path.endswith("/refresh") and not body)
            require(normal_domain(path[len("/dossiers/"):-len("/refresh")]) == domain)
    return state


class Store:
    def __init__(self, state_path=None):
        self.lock = threading.RLock()
        self.state_path = Path(state_path) if state_path else None
        self.clock = None
        state = new_state()
        pending = {}
        if self.state_path is not None and self.state_path.exists():
            with self.state_path.open(encoding="utf-8") as saved:
                persisted = json.load(saved)
            state = validate_snapshot(persisted["snapshot"])
            self.clock = timestamp(persisted["clock"]) if persisted["clock"] else None
            pending = persisted.get("active", {})
        self.replace(state)
        if pending:
            self.recover(pending)

    def now(self):
        return self.clock or datetime.now(timezone.utc)

    def set_clock(self, body):
        next_time = timestamp(string(body, "now"))
        with self.lock:
            if next_time < self.now():
                bad("The clock cannot move backwards.")
            self.clock = next_time
            self.persist()

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
            self.persist()

    def replace(self, state):
        self.state = state
        self.replays = {tuple(item[:3]): item for item in state["replays"]}
        self.before_build = {}
        self.running_times = {}
        self.active = {}

    def snapshot(self):
        state = self.state | {"dossiers": self.state["dossiers"] | self.before_build}
        return {"track": "dossier", "format_version": 1, "state": state}

    def export(self):
        with self.lock:
            return copy.deepcopy(self.snapshot())

    def persist(self):
        if self.state_path is None:
            return
        self.save_file(self.state_path, {"snapshot": self.snapshot(), "active": self.active,
                                        "clock": self.clock.isoformat() if self.clock else None})

    def progress_path(self, entry):
        return self.state_path.with_name(f".{self.state_path.name}.active.{entry['record']['id']}")

    def persist_progress(self, entry):
        if self.state_path is not None:
            self.save_file(self.progress_path(entry), entry)

    def save_file(self, path, document):
        directory = path.parent
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, prefix=".state-", delete=False) as file:
                temporary = Path(file.name)
                json.dump(document, file, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            with_directory = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(with_directory)
            finally:
                os.close(with_directory)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def recover(self, pending):
        for domain, saved in pending.items():
            baseline = saved["record"]["spent_units"]
            path = self.progress_path(saved)
            if path.exists():
                with path.open(encoding="utf-8") as file:
                    entry = json.load(file)
            else:
                entry = saved
            record = entry["record"]
            interrupt(record, entry["reserved"])
            record.update(completed_at=self.now().isoformat(), elapsed_ms=0, outcome="failed")
            dossier = self.state["dossiers"][domain]
            dossier["spent_units"] += record["spent_units"]
            dossier["state"] = "failed"
            dossier["builds"].append(record)
            dossier["timeline"].append(snapshot_for_build(dossier, record, None))
            batch = self.state["batches"].get(entry["batch_id"])
            if batch is not None:
                # The main snapshot already includes settlements made before it.
                batch["spent_units"] += record["spent_units"] - baseline
                batch["pending"].remove(domain)
        self.persist()
        for entry in pending.values():
            self.progress_path(entry).unlink(missing_ok=True)

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
            self.persist()
            return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def write(self, owner, path, key, body, received, domain_path=None):
        scope = (owner, path, key)
        prior = self.replays.get(scope)
        if prior is not None:
            same_budget = ("budget_units" not in prior[3] or
                           type(prior[3]["budget_units"]) is type(body.get("budget_units")))
            if prior[3] != body or not same_budget:
                raise Problem(409, "idempotency_key_reuse", "That key was already used with a different body.")
            return 200, prior[4]
        if path == "/batches":
            response = self.create_batch(owner, body, received)
            self.remember(scope, body, response)
            return 202, response
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
        self.remember(scope, body, result)
        return status, result

    def remember(self, scope, body, result):
        replay = [*scope, body, result]
        self.replays[scope] = replay
        self.state["replays"].append(replay)
        self.persist()

    def create_batch(self, owner, body, received):
        domains, budget = batch_request(body)
        batch_id = secrets.token_urlsafe(18)
        existing = self.state["dossiers"]
        new_domains = [domain for domain in domains if domain not in existing]
        batch = {"batch_id": batch_id, "owner": owner, "domains": domains, "pending": new_domains.copy(),
                 "budget_units": budget, "spent_units": 0}
        self.state["batches"][batch_id] = batch
        for domain in new_domains:
            dossier = existing[domain] = new_dossier(domain)
            self.start(dossier, received, batch_id)
        return self.batch_detail(batch)

    def batch_detail(self, batch):
        dossiers = self.state["dossiers"]
        return {"batch_id": batch["batch_id"], "state": "running" if batch["pending"] else "done",
                "budget_units": batch["budget_units"], "spent_units": batch["spent_units"],
                "dossiers": [{"domain": domain, "state": dossiers[domain]["state"]}
                             for domain in batch["domains"]]}

    def get_batch(self, owner, batch_id):
        batch = self.state["batches"].get(batch_id)
        if batch is None or batch["owner"] != owner:
            raise Problem(404, "not_found", "Batch not found.")
        return self.batch_detail(batch)

    def start(self, dossier, received, batch_id=None):
        domain = dossier["domain"]
        prior = dossier.copy()
        self.before_build[domain] = prior
        self.running_times[domain] = timestamp(received)
        dossier["state"] = "building"
        record = {"id": secrets.token_urlsafe(18), "started_at": received, "completed_at": None,
                  "elapsed_ms": None, "outcome": "failed", "spent_units": 0,
                  "calls": [], "pages": [], "claims": []}
        entry = {"batch_id": batch_id, "record": copy.deepcopy(record), "reserved": {}}
        self.active[domain] = entry
        ledger = BuildLedger(self, dossier, entry)
        worker = threading.Thread(target=self.build, args=(dossier, prior, record, ledger), daemon=True)
        worker.start()

    def build(self, dossier, prior, record, ledger):
        domain = dossier["domain"]
        started = time.monotonic()
        def current():
            with self.lock:
                return ledger.current()

        try:
            fields = gather(domain, record, current, ledger)
        except Exception:
            # Preserve completed observations even when interpretation cannot complete.
            fields = None
        with self.lock:
            if not current():
                return
            entry = ledger.entry
            batch = ledger.batch()
            reservations = entry["reserved"]
            if reservations:
                interrupt(record, reservations)
                held = sum(reservations.values())
                dossier["spent_units"] += held
                if batch is not None:
                    batch["spent_units"] += held
            record["completed_at"] = self.now().isoformat()
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            if fields is not None:
                record["outcome"] = "ready"
            snapshot = snapshot_for_build(dossier, record, fields)
            if fields is not None:
                feed = self.state["changes"]
                seq = feed[-1]["seq"] + 1 if feed else 1
                dossier["history"], added = updates(dossier, snapshot, seq)
                feed.extend(added)
                dossier["fields"] = snapshot["fields"]
                dossier["researched_at"] = record["started_at"]
            dossier["state"] = record["outcome"]
            dossier["builds"] = prior["builds"] + [record]
            dossier["timeline"] = prior["timeline"] + [snapshot]
            self.before_build.pop(domain, None)
            self.running_times.pop(domain, None)
            self.active.pop(domain)
            if batch is not None:
                batch["pending"].remove(domain)
            self.persist()
            if self.state_path is not None:
                self.progress_path(entry).unlink(missing_ok=True)

    def dossier(self, domain):
        dossier = self.state["dossiers"].get(normal_domain(domain))
        if dossier is None:
            raise Problem(404, "not_found", "Dossier not found.")
        return dossier

    def get(self, domain, as_of=None):
        dossier = self.dossier(domain)
        if as_of is None:
            return public_detail(dossier)
        builds, latest = self.ready_at(dossier, as_of)
        spend = sum(event["spent_units"] for event in builds)
        domain = dossier["domain"]
        running = self.running_times.get(domain)
        if running is not None and running <= as_of:
            spend += dossier["spent_units"] - self.before_build[domain]["spent_units"]
        return public_detail(dossier) | {
            "state": "ready", "researched_at": latest["started_at"],
            "spent_units": spend, "fields": latest["fields"],
        }

    def ready_at(self, dossier, as_of):
        builds = qualifying_builds(dossier["timeline"], as_of)
        latest = selected_snapshot(builds)
        if latest is None:
            raise Problem(404, "not_found", "Dossier has no completed research at that time.")
        return builds, latest

    def values(self, domain, date, as_of):
        instant = timestamp(as_of)
        dossier = self.dossier(domain)
        builds, _ = self.ready_at(dossier, instant)
        return {"domain": dossier["domain"], "true_at": date, "as_of": as_of,
                "fields": effective_fields(builds, date)}

    def history(self, domain):
        dossier = self.dossier(domain)
        return {"domain": dossier["domain"], "fields": dossier["history"]}

    def changes(self, since, limit):
        feed = self.state["changes"]
        index = bisect_right(feed, since, key=lambda entry: entry["seq"])
        return {"changes": feed[index:index + limit], "has_more": len(feed) > index + limit}

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


STORE = Store(os.environ.get("DOSSIER_STATE_PATH"))
DETAIL = re.compile(r"/dossiers/([^/]*)")
REFRESH = re.compile(r"/dossiers/([^/]*)/refresh")
EVIDENCE = re.compile(r"/dossiers/([^/]*)/evidence")
HISTORY = re.compile(r"/dossiers/([^/]*)/history")
VALUES = re.compile(r"/dossiers/([^/]*)/values")
BATCH = re.compile(r"/batches/([^/]+)")
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
            for batch in snapshot["batches"].values():
                batch["pending"] = []
            with STORE.lock:
                STORE.replace(snapshot)
                STORE.persist()
            return 204, None

        refresh = REFRESH.fullmatch(path)
        detail = DETAIL.fullmatch(path)
        authorization = self.headers.get("Authorization")
        with STORE.lock:
            owner = None
            if not (path == "/health" or path.startswith("/_test/")):
                owner = STORE.authenticate(authorization)
            if method == "GET":
                query = parse_qs(target.query, keep_blank_values=True)
                if path == "/dossiers":
                    q = query.get("q", [""])[0].casefold()
                    return 200, STORE.listed(q, paging(query, "limit", 50, 1, 200),
                                             paging(query, "offset", 0, 0))
                if path == "/changes":
                    return 200, STORE.changes(paging(query, "since", 0, 0), paging(query, "limit", 50, 1, 200))
                if match := BATCH.fullmatch(path):
                    return 200, STORE.get_batch(owner, match[1])
                if detail:
                    as_of = timestamp(query["as_of"][0]) if "as_of" in query else None
                    return 200, STORE.get(detail[1], as_of)
                if match := HISTORY.fullmatch(path):
                    return 200, STORE.history(match[1])
                if match := VALUES.fullmatch(path):
                    date = date_text(query.get("true_at", [""])[0])
                    if date is None:
                        bad("Expected a true_at date in YYYY-MM-DD format.")
                    return 200, STORE.values(match[1], date, query.get("as_of", [received])[0])
        if method == "POST" and (refresh or path in ("/dossiers", "/batches")):
            key = self.headers.get("Idempotency-Key", "").strip()
            if not key:
                raise Problem(400, "missing_idempotency_key", "An Idempotency-Key is required.")
            if len(key) > 255:
                bad("Idempotency-Key must be 1 to 255 characters.")
            if refresh:
                body = {}
            else:
                parsed = self.payload()
                keys = ("domains", "budget_units") if path == "/batches" else ("domain",)
                body = {key: parsed[key] for key in keys if key in parsed}
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
