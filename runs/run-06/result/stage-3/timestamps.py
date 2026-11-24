"""Comparable RFC 3339 instants without rounding a fractional second."""
import re
from datetime import date, datetime


STAMP = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.([0-9]+))?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def parse_stamp(text):
    match = STAMP.fullmatch(text)
    if not match:
        raise ValueError("Invalid RFC 3339 timestamp")
    return datetime.fromisoformat((match[1] + match[3]).upper()), (match[2] or "").rstrip("0")

def calendar_date(text):
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise ValueError("Invalid calendar date")
    return date.fromisoformat(text).isoformat()
