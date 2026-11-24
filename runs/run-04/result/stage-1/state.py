"""API validation and the portable, completed portion of the service state."""

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone

from evidence import PHRASES, empty_fields, values


class ApiError(Exception):
    def __init__(self, status, code, message=None):
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()


def invalid(message="Invalid value"):
    raise ApiError(422, "validation_failed", message)


def malformed():
    raise ApiError(400, "malformed_request", "Expected a JSON object with correctly typed fields")


def field(obj, key, expected=str):
    if key not in obj:
        invalid(f"Missing {key}")
    if type(obj[key]) is not expected:
        malformed()
    return obj[key]


HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
EMAIL = re.compile(r"[^\s@]+@[^\s@]+")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)", re.ASCII)


def domain_name(raw):
    name = raw.strip().lower().removesuffix(".").removeprefix("www.")
    validate_host(name)
    return name


def validate_host(name):
    labels = name.split(".")
    if len(name) > 253 or len(labels) < 2 or not all(HOST_LABEL.fullmatch(s) for s in labels):
        invalid("Invalid company domain")


def timestamp(raw):
    if not TIMESTAMP.fullmatch(raw):
        invalid("Expected an RFC 3339 timestamp with an explicit offset")
    try:
        dt = datetime.fromisoformat(raw.upper())
        # Compare fractional seconds without losing precision to datetime's microsecond limit.
        fraction = raw.split(".", 1)[1] if "." in raw else ""
        fraction = re.match(r"\d*", fraction)[0].rstrip("0")
        return dt.replace(microsecond=0), fraction
    except (ValueError, OverflowError):
        invalid("Invalid date or time")


def now_system():
    return datetime.now(timezone.utc).isoformat()


def email_key(email):
    if not EMAIL.fullmatch(email):
        invalid("Invalid email")
    return email.casefold()


def display_name(name):
    if not 1 <= len(name) <= 100:
        invalid("Display name must be 1 to 100 characters")
    return name


def new_id(prefix):
    return prefix + secrets.token_hex(16)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=bytes.fromhex(salt),
                            n=16384, r=8, p=1, dklen=32)
    return salt + ":" + digest.hex()


def check_password(password, encoded):
    return hmac.compare_digest(encoded, password_hash(password, encoded.split(":")[0]))


def blank():
    return {"users": {}, "tokens": {}, "dossiers": {}, "replays": {}, "builds": {}}


def initial(domain):
    return {"domain": domain, "dossier_id": new_id("d_"), "state": "failed", "researched_at": None,
            "spent_units": 0, "fields": empty_fields()}


def canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def checksum(data):
    return hashlib.sha256(canonical(data).encode("ascii")).hexdigest()


def snapshot(data):
    return {"track": "dossier", "format_version": 1, "state": {"data": data, "sha256": checksum(data)}}


def valid_id(identifier):
    return isinstance(identifier, str) and 0 < len(identifier) <= 64


def validate_store(data):
    if set(data) != set(blank()) or not all(isinstance(v, dict) for v in data.values()):
        return False
    ids = set()
    for email, user in data["users"].items():
        uid = user["id"]
        if email_key(email) != email or not valid_id(uid) or uid in ids:
            return False
        if not isinstance(user["display_name"], str) or not display_name(user["display_name"]):
            return False
        if not re.fullmatch(r"[a-f0-9]{32}:[a-f0-9]{64}", user["password_hash"]):
            return False
        ids.add(uid)
    if any(not valid_id(token) or uid not in ids for token, uid in data["tokens"].items()):
        return False
    dossier_ids = set()
    for name, doc in data["dossiers"].items():
        validate_host(name)
        if name != doc["domain"] or not valid_id(doc["dossier_id"]):
            return False
        if doc["dossier_id"] in dossier_ids or doc["state"] not in {"failed", "ready"}:
            return False
        dossier_ids.add(doc["dossier_id"])
        if type(doc["spent_units"]) is not int or doc["spent_units"] < 0 or set(doc["fields"]) != set(PHRASES):
            return False
        if doc["researched_at"] is None:
            if doc["state"] == "ready" or doc["fields"] != empty_fields():
                return False
        else:
            timestamp(doc["researched_at"])
        for name_field, entry in doc["fields"].items():
            if entry["value"] is None:
                if entry != {"value": None, "status": "unknown", "citations": []}:
                    return False
                continue
            if entry["status"] != "known" or not isinstance(entry["citations"], list) or not entry["citations"]:
                return False
            for cite in entry["citations"]:
                if cite["provider"] not in {"nimble", "tavily"} or not cite["url"]:
                    return False
                if values(name, cite["excerpt"]).get(name_field) != entry["value"]:
                    return False
    for key, replay in data["replays"].items():
        uid, method, path, idem = json.loads(key)
        if uid not in ids or method != "POST" or not isinstance(path, str) or not 1 <= len(idem) <= 255:
            return False
        body = replay["response"]
        if body["domain"] not in data["dossiers"] or data["dossiers"][body["domain"]]["dossier_id"] != body["dossier_id"]:
            return False
        if body["state"] not in {"building", "failed", "ready"} or not isinstance(replay["body"], dict):
            return False
    for name, history in data["builds"].items():
        if name not in data["dossiers"] or not isinstance(history, list):
            return False
        total = 0
        for build in history:
            timestamp(build["time"])
            if not isinstance(build["pages"], list) or not isinstance(build["claims"], list):
                return False
            units = [call["units"] for call in build["calls"]]
            if any(type(cost) is not int or cost < 0 for cost in units) or sum(units) > 80:
                return False
            total += sum(units)
        if total != data["dossiers"][name]["spent_units"]:
            return False
    return True


def restore(obj):
    try:
        if obj.get("track") != "dossier" or type(obj.get("format_version")) is not int or obj["format_version"] != 1:
            invalid()
        state = obj["state"]
        data = state["data"]
        if not isinstance(data, dict) or state["sha256"] != checksum(data) or not validate_store(data):
            invalid()
        return data
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError, RecursionError, ApiError):
        invalid("Invalid dossier export")
