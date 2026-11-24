"""The committed snapshot and validation rules for the in-memory service."""
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_hex
from uuid import uuid4

from evidence import FIELD_NAMES, blank_fields

class Problem(Exception):
    def __init__(self, status=422, code="validation_failed", message="Invalid request"):
        self.status, self.code, self.message = status, code, message

def require(condition, message="Invalid request"):
    if not condition:
        raise Problem(message=message)

def prop(obj, name, typ=str):
    require(name in obj, f"Missing {name}")
    if type(obj[name]) is not typ:
        raise Problem(400, "malformed_request", f"Incorrect type for {name}")
    return obj[name]

@dataclass(frozen=True, order=True)
class Instant:
    second: datetime
    # Canonical fractional digits sort chronologically, including beyond microseconds.
    fraction: str

    def isoformat(self):
        whole = self.second.isoformat(timespec="seconds")
        fraction = "." + self.fraction if self.fraction else ""
        return whole[:19] + fraction + whole[19:]


def timestamp(value):
    match = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]+))?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value)
    require(match)
    try:
        whole = datetime.fromisoformat((match[1] + match[3]).upper())
        return Instant(whole, (match[2] or "").rstrip("0"))
    except ValueError:
        raise Problem(message="Invalid timestamp")

def validate_hostname(name):
    labels = name.split(".")
    require(len(labels) >= 2 and len(name) <= 253 and
            all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels),
            "Invalid company domain")

def domain(value):
    normalized = value.strip().lower().removesuffix(".").removeprefix("www.")
    validate_hostname(normalized)
    return normalized

def opaque_id(prefix):
    return prefix + uuid4().hex

def password_hash(password, salt=None):
    salt = salt or token_hex(16)
    digest = hashlib.scrypt(password.encode("utf8", "surrogatepass"), salt=bytes.fromhex(salt),
                            n=16384, r=8, p=1, dklen=32)
    return salt + ":" + digest.hex()

def validate_email(email):
    require(re.fullmatch(r"[^@\s]+@[^@\s]+", email), "Invalid email")

def new_user(obj, seeded=False):
    password = prop(obj, "password")
    email = prop(obj, "email")
    name = prop(obj, "display_name")
    uid = prop(obj, "id") if seeded else opaque_id("u_")
    require(0 < len(uid) <= 64)
    if not seeded:
        validate_email(email)
        require(len(password) >= 8 and 0 < len(name) <= 100)
    return {"id": uid, "email": email, "display_name": name, "hash": password_hash(password)}

def fresh_dossier(name):
    return {"dossier_id": opaque_id("d_"), "domain": name, "researched_at": None,
            "spent_units": 0, "state": "failed", "fields": blank_fields()}

def digest(payload):
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

class Store:
    def __init__(self):
        self.users = {}
        self.tokens = {}
        self.dossiers = {}
        self.replays = {}
        self.history = {}
        self.running = {}
        self.clock = None

    def now(self):
        return self.clock or timestamp(datetime.now(timezone.utc).isoformat())

    def add_user(self, user):
        if user["email"] in self.users:
            raise Problem(409, "email_taken", "Email is already registered")
        self.users[user["email"]] = user

    def session(self, user):
        token = token_hex(32)
        self.tokens[token] = user["id"]
        return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def detail(self, name):
        if name not in self.dossiers:
            raise Problem(404, "not_found", "Unknown dossier")
        row = self.dossiers[name].copy()
        if job := self.running.get(name):
            row.update(state="building", spent_units=row["spent_units"] + job.spent)
        return row

    def export(self):
        payload = {"users": self.users, "tokens": self.tokens, "dossiers": self.dossiers,
                   "history": self.history, "replays": list(self.replays.values())}
        return {"track": "dossier", "format_version": 1, "state": {"data": payload, "sha256": digest(payload)}}

    @classmethod
    def restore(cls, obj):
        require(obj.get("track") == "dossier" and type(obj.get("format_version")) is int and obj["format_version"] == 1)
        try:
            state = obj["state"]
            data = state["data"]
            require(hmac.compare_digest(digest(data), state["sha256"]))
            fresh = cls()
            users, tokens, dossiers, history = (data[k] for k in ("users", "tokens", "dossiers", "history"))
            require(all(type(item) is dict for item in (users, tokens, dossiers, history)))
            ids = set()
            for email, u in users.items():
                uid = prop(u, "id")
                require(prop(u, "email") == email and 0 < len(uid) <= 64 and uid not in ids)
                prop(u, "display_name")
                require(re.fullmatch(r"[a-f0-9]{32}:[a-f0-9]{64}", prop(u, "hash")))
                ids.add(uid)
            require(all(uid in ids for uid in tokens.values()))
            for key, row in dossiers.items():
                validate_hostname(key)
                require(key == row["domain"] and row["state"] in ("ready","failed"))
                require(0 < len(prop(row, "dossier_id")) <= 64 and prop(row, "spent_units", int) >= 0)
                if row["researched_at"] is not None:
                    timestamp(row["researched_at"])
                require(set(row["fields"]) == set(FIELD_NAMES))
                for field in row["fields"].values():
                    citations = prop(field, "citations", list)
                    if field["status"] == "unknown":
                        require(field["value"] is None and not citations)
                    else:
                        require(field["status"] == "known" and field["value"] is not None and citations)
                        for cit in citations:
                            require(cit["provider"] in ("nimble", "tavily") and prop(cit, "url") and 0 < len(prop(cit, "excerpt")) <= 500)
            require(set(history) <= set(dossiers) and all(type(items) is list for items in history.values()))
            fresh.users, fresh.tokens, fresh.dossiers, fresh.history = users, tokens, dossiers, history
            for record in prop(data, "replays", list):
                uid, path, key = record["scope"]
                require(uid in ids and type(path) is str and 1 <= len(key) <= 255)
                require(record["response"]["domain"] in dossiers and type(record["body"]) is dict)
                fresh.replays[(uid, path, key)] = record
            return fresh
        except (KeyError, ValueError, TypeError, AttributeError, Problem, RecursionError):
            raise Problem(message="Invalid exported state")
