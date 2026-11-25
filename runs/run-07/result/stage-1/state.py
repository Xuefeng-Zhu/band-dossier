"""State for a single ASGI event loop. A completed dossier is immutable during a build."""
import asyncio
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone


FIELDS = ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total")
ERRORS = {
    "malformed_request": 400, "missing_idempotency_key": 400, "unauthenticated": 401,
    "not_found": 404, "email_taken": 409, "idempotency_key_reuse": 409, "validation_failed": 422,
}


class Problem(Exception):
    def __init__(self, code="validation_failed", message="Invalid request"):
        self.code = code
        self.message = message
        self.status = ERRORS[code]


def require(condition, message):
    if not condition:
        raise Problem(message=message)


def member(obj, key, kind=str):
    require(key in obj, f"Missing {key}")
    if type(obj[key]) is not kind:
        raise Problem("malformed_request", f"Invalid type for {key}")
    return obj[key]


@dataclass(order=True, frozen=True)
class Instant:
    second: datetime
    fraction: str  # Right-trimmed digits sort exactly as their decimal fractions do.
    display: str = field(compare=False)

    def isoformat(self):
        return self.display


def parse_time(value):
    match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2})"
                         r"(?:\.([0-9]+))?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value)
    require(match, "Expected an RFC 3339 timestamp with an offset")
    whole, fraction, offset = match.groups()
    offset = "+00:00" if offset.upper() == "Z" else offset
    try:
        second = datetime.fromisoformat(whole.upper() + offset)
    except ValueError:
        raise Problem(message="Invalid date or time")
    display = whole.upper() + ("." + fraction if fraction else "") + offset
    return Instant(second, (fraction or "").rstrip("0"), display)


def normalize(raw):
    name = raw.strip().lower().removesuffix(".").removeprefix("www.")
    labels = name.split(".")
    require(len(name) <= 253 and len(labels) >= 2 and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in labels
    ), "Invalid domain")
    return name


def user_input(body):
    email = member(body, "email")
    password = member(body, "password")
    display = member(body, "display_name")
    require(re.fullmatch(r"[^\s@]+@[^\s@]+", email), "Invalid email address")
    require(len(password) >= 8, "Password must be at least eight characters")
    require(1 <= len(display) <= 100, "Invalid display name")
    return email, password, display


def derive(password, salt):
    return hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt),
                          n=16384, r=8, p=1).hex()


async def new_account(uid, email, password, display):
    salt = secrets.token_hex(16)
    hashed = await asyncio.to_thread(derive, password, salt)
    return {"id": uid, "email": email, "display_name": display, "salt": salt, "scrypt": hashed}


def uid(prefix):
    return prefix + secrets.token_hex(16)


def unknown_fields():
    return {f: {"value": None, "status": "unknown", "citations": []} for f in FIELDS}


def new_dossier(domain):
    return {"dossier_id": uid("d_"), "domain": domain, "state": "failed", "fields": unknown_fields(),
            "researched_at": None, "spent_units": 0}


@dataclass
class ActiveBuild:
    started: str
    spent: int = 0
    task: asyncio.Task | None = None


@dataclass
class Store:
    users: dict = field(default_factory=dict)     # email -> account
    tokens: dict = field(default_factory=dict)    # bearer token -> user id
    dossiers: dict = field(default_factory=dict)  # completed state, including before a first build
    replays: dict = field(default_factory=dict)   # (user, method, raw path, key) -> (body, response)
    history: dict = field(default_factory=dict)   # domain -> completed research records
    active: dict = field(default_factory=dict)

    def session(self, user):
        token = secrets.token_urlsafe(32)
        self.tokens[token] = user["id"]
        return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def view(self, domain):
        doc = self.dossiers[domain]
        if build := self.active.get(domain):
            return {**doc, "state": "building", "spent_units": doc["spent_units"] + build.spent}
        return doc

    def snapshot(self):
        data = {"users": self.users, "tokens": self.tokens, "dossiers": self.dossiers, "history": self.history,
                "replays": [[list(k), *v] for k, v in self.replays.items()]}
        return {"track": "dossier", "format_version": 1, "state": {"data": data, "sha256": digest(data)}}

    @classmethod
    def from_snapshot(cls, envelope):
        require(envelope.get("track") == "dossier" and type(envelope.get("format_version")) is int
                and envelope["format_version"] == 1, "Invalid export format")
        state = envelope.get("state")
        require(isinstance(state, dict), "Invalid export state")
        data = state.get("data")
        require(isinstance(data, dict) and digest(data) == state.get("sha256"), "Invalid snapshot data")
        try:
            users, tokens, docs, history = (data[k] for k in ("users", "tokens", "dossiers", "history"))
            user_ids = set()
            for email, user in users.items():
                identity = user["id"]
                require(email == user["email"] and isinstance(identity, str) and 1 <= len(identity) <= 64
                        and identity not in user_ids and isinstance(user["display_name"], str)
                        and re.fullmatch("[0-9a-f]{32}", user["salt"])
                        and re.fullmatch("[0-9a-f]{128}", user["scrypt"]), "Invalid account")
                user_ids.add(identity)
            require(all(v in user_ids for v in tokens.values()), "Invalid session")
            for domain, doc in docs.items():
                require(domain == normalize(domain) == doc["domain"] and doc["state"] in ("ready", "failed")
                        and type(doc["spent_units"]) is int and doc["spent_units"] >= 0
                        and isinstance(doc["dossier_id"], str) and 1 <= len(doc["dossier_id"]) <= 64
                        and set(doc["fields"]) == set(FIELDS), "Invalid dossier")
                if doc["researched_at"] is not None:
                    parse_time(doc["researched_at"])
                for item in doc["fields"].values():
                    require(isinstance(item["citations"], list) and
                            (item["status"], bool(item["citations"])) ==
                            (("unknown", False) if item["value"] is None else ("known", True)), "Invalid field")
            require(isinstance(history, dict) and all(k in docs and isinstance(v, list) for k, v in history.items()),
                    "Invalid research history")
            require(isinstance(data["replays"], list), "Invalid replay history")
            replays = {}
            for key, body, response in data["replays"]:
                require(len(key) == 4 and all(isinstance(x, str) for x in key) and key[0] in user_ids
                        and key[1] == "POST" and isinstance(body, dict) and response["domain"] in docs,
                        "Invalid saved response")
                replays[tuple(key)] = (body, response)
            return cls(users=users, tokens=tokens, dossiers=docs, history=history, replays=replays)
        except (TypeError, ValueError, KeyError, AttributeError):
            raise Problem(message="Invalid export state")


def digest(data):
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class Database:
    def __init__(self):
        self.state = Store()
        self.clock = None

    def now(self):
        return self.clock or parse_time(datetime.now(timezone.utc).isoformat())

    def replace(self, state):
        for build in self.state.active.values():
            build.task.cancel()
        self.state = state

    async def reset(self, body):
        stamp = parse_time(member(body, "now"))
        rows = member(body, "users", list) if "users" in body else []
        next_state = Store()
        ids = set()
        for row in rows:
            if not isinstance(row, dict):
                raise Problem("malformed_request", "Invalid fixture user")
            identity = member(row, "id")
            email, password, display = user_input(row)
            require(email not in next_state.users and identity not in ids and 1 <= len(identity) <= 64,
                    "Invalid or duplicate fixture identity")
            ids.add(identity)
            next_state.users[email] = await new_account(identity, email, password, display)
        self.replace(next_state)
        self.clock = stamp

    async def login(self, body):
        email, password = member(body, "email"), member(body, "password")
        while user := self.state.users.get(email):
            computed = await asyncio.to_thread(derive, password, user["salt"])
            if self.state.users.get(email) is not user:
                continue
            if hmac.compare_digest(computed, user["scrypt"]):
                return self.state.session(user)
            break
        raise Problem("unauthenticated", "Invalid login")
