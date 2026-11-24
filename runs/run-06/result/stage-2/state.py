"""In-memory serializable state. All mutations run on the HTTP event loop."""
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from evidence import FIELDS, unknown_fields
from candidates import migrate_fields
from timestamps import parse_stamp


class ApiError(Exception):
    def __init__(self, status, code, message=None):
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()


def require(condition, message=None):
    if not condition:
        raise ApiError(422, "validation_failed", message)


def member(body, key, cls=str):
    require(key in body, f"Missing {key}")
    value = body[key]
    if type(value) is not cls:
        raise ApiError(400, "malformed_request", f"Incorrect type for {key}")
    return value


def instant(value):
    try:
        return parse_stamp(value)
    except ValueError:
        raise ApiError(422, "validation_failed", "Invalid timestamp") from None


def domain_name(value):
    name = value.strip().lower().removesuffix(".").removeprefix("www.")
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    require(len(name) <= 253 and re.fullmatch(label + "(?:[.]" + label + ")+", name), "Invalid company domain")
    return name


def opaque_id(prefix):
    return prefix + uuid4().hex


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
    return salt + "." + digest.hex()


def password_matches(password, stored):
    return hmac.compare_digest(stored, password_hash(password, stored.split(".")[0]))


def digest(data):
    packed = json.dumps(data, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(packed).hexdigest()


class Store:
    def __init__(self):
        self.users = {}       # email to account
        self.tokens = {}      # bearer token to user id
        self.dossiers = {}    # domain to last completed version
        self.replays = {}     # (user id, method, raw path, key) to (request, response)
        self.history = {}     # domain to completed builds and their source evidence
        self.running = {}     # domain to the transient build
        self.clock = None

    def now(self):
        return self.clock or datetime.now(timezone.utc).isoformat()

    def new_dossier(self, domain):
        self.dossiers[domain] = {
            "domain": domain, "dossier_id": opaque_id("d_"), "state": "failed",
            "fields": unknown_fields(), "researched_at": None, "spent_units": 0,
        }
        self.history[domain] = []

    def view(self, domain):
        if domain not in self.dossiers:
            raise ApiError(404, "not_found")
        view = self.dossiers[domain].copy()
        if build := self.running.get(domain):
            view.update(state="building", spent_units=view["spent_units"] + build.spent)
        return view

    def snapshot(self):
        data = {
            "stage": 2, "users": self.users, "tokens": self.tokens, "dossiers": self.dossiers,
            "history": self.history,
            "replays": [[*key, *pair] for key, pair in self.replays.items()],
        }
        return {"track": "dossier", "format_version": 1, "state": {"data": data, "sha256": digest(data)}}

    @classmethod
    def restore(cls, envelope):
        require(envelope.get("track") == "dossier" and type(envelope.get("format_version")) is int and envelope["format_version"] == 1)
        state = envelope.get("state")
        require(type(state) is dict and type(state.get("data")) is dict)
        data = state["data"]
        restored = cls()
        try:
            require(digest(data) == state.get("sha256"), "Snapshot integrity check failed")
            restored.users = data["users"]
            restored.tokens = data["tokens"]
            restored.dossiers = data["dossiers"]
            restored.history = data["history"]
            require(all(type(v) is dict for v in (restored.users, restored.tokens, restored.dossiers, restored.history)))
            ids = set()
            for email, account in restored.users.items():
                require(isinstance(account["display_name"], str) and re.fullmatch(r"[0-9a-f]{32}\.[0-9a-f]{64}", account["hash"]))
                require(isinstance(account["id"], str) and 0 < len(account["id"]) <= 64 and account["id"] not in ids)
                ids.add(account["id"])
            require(all(token and uid in ids for token, uid in restored.tokens.items()))
            require(restored.history.keys() == restored.dossiers.keys())
            for name, dossier in restored.dossiers.items():
                require(name == dossier["domain"] and domain_name(name) == name)
                require(dossier["state"] in ("ready", "failed") and set(dossier["fields"]) == set(FIELDS))
                require(type(dossier["spent_units"]) is int and dossier["spent_units"] >= 0 and isinstance(dossier["dossier_id"], str))
                if dossier["researched_at"] is not None:
                    instant(dossier["researched_at"])
                require(isinstance(restored.history[name], list))
                if data.get("stage", 1) == 1:
                    dossier["fields"] = migrate_fields(dossier, restored.history[name])
                for field in dossier["fields"].values():
                    require(isinstance(field["candidates"], list))
                    require(field["status"] in (("unknown",) if field["value"] is None else ("known", "contested")))
                    require(isinstance(field["citations"], list) and bool(field["citations"]) == (field["value"] is not None))
                require(isinstance(restored.history[name], list))
            for uid, method, path, key, request, response in data["replays"]:
                require(uid in ids and method == "POST" and isinstance(key, str) and isinstance(path, str))
                require(isinstance(request, dict) and response["domain"] in restored.dossiers)
                restored.replays[uid, method, path, key] = (request, response)
        except (AttributeError, IndexError, KeyError, RecursionError, TypeError, ValueError):
            raise ApiError(422, "validation_failed", "Invalid snapshot state") from None
        return restored
