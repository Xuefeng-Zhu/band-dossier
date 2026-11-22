"""Page metadata, evidence collection, ranking and offline Stage 1 upgrade."""

from datetime import date, datetime, timezone
import re
from urllib.parse import urlsplit

from evidence import Appendix, EXECUTIVE_PHRASES, FIELDS, is_header


AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2, None: 2}
PROVIDERS = ("nimble", "tavily", "kernel", "browserbase")
CITATION_KEYS = ("url", "excerpt", "provider")
CANDIDATE_KEYS = {"value", "url", "excerpt", "provider", "kind", "published_at", "retrieved_at", "selected"}
RFC3339 = re.compile(
    r"(\d{4}-\d{2}-\d{2})[Tt](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|z|[+-]\d{2}:\d{2})",
    re.ASCII,
)


def publication_key(value):
    if not isinstance(value, str) or not (match := RFC3339.fullmatch(value)):
        return ()
    date, clock, fraction, offset = match.groups()
    offset = "+00:00" if offset in ("Z", "z") else offset
    if int(offset[1:3]) > 23 or int(offset[4:]) > 59:
        return ()
    try:
        instant = datetime.fromisoformat(f"{date}T{clock}{offset}")
        # Offset comparisons preserve ordering even at the boundaries of datetime's range.
        return (instant, (fraction or "").rstrip("0"))
    except ValueError:
        return ()


def page_headers(text):
    lines = text.splitlines()
    headers = {}
    if lines and is_header(lines[0]):
        for line in lines:
            if not line.strip():
                break
            name, _, value = line.partition(":")
            headers.setdefault(name, value.strip())
    return headers


def day_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def effective_date(text, publication):
    value = page_headers(text).get("Effective")
    if day_key(value):
        return value
    if key := publication_key(publication):
        try:
            return key[0].astimezone(timezone.utc).date().isoformat()
        except (OverflowError, ValueError):
            pass
    return None


def page_metadata(domain, page, legacy):
    headers = page_headers(page["text"])
    kind = headers.get("Kind")
    published = headers.get("Published")
    if legacy:
        if not kind:
            kind = page.get("kind")
        if not published:
            published = page.get("published_at") or page.get("published_date")
    if kind not in ("own", "filing", "news", "aggregator"):
        if legacy:
            kind = None
        else:
            host = (urlsplit(page["url"]).hostname or "").removesuffix(".").removeprefix("www.")
            kind = "own" if host == domain else "aggregator"
    return kind, published if publication_key(published) else None


def ranked(candidates):
    ordered = sorted(candidates, key=lambda c: (c["url"], PROVIDERS.index(c["provider"]), c["value"], c["excerpt"]))
    ordered.sort(key=lambda c: publication_key(c["published_at"]), reverse=True)
    ordered.sort(key=lambda c: AUTHORITY[c["kind"]])
    # Multiple observations of a page contribute at most one candidate per value.
    unique = {}
    for item in ordered:
        unique.setdefault((item["value"], item["url"]), item)
    return list(unique.values())


def unknown_fields():
    return {name: {"value": None, "status": "unknown", "citations": [], "candidates": []}
            for name in FIELDS}


def select(raw, retrieved_at):
    fields = unknown_fields()
    for field, candidates in raw.items():
        if not candidates:
            continue
        candidates = [
            {**c, "retrieved_at": retrieved_at, "selected": index == 0}
            for index, c in enumerate(ranked(candidates))
        ]
        value = candidates[0]["value"]
        selected_value = [c for c in candidates if c["value"] == value]
        status = "known" if len(selected_value) == len(candidates) else "contested"
        fields[field] = {
            "value": value, "status": status, "candidates": candidates,
            "citations": [{key: candidate[key] for key in CITATION_KEYS} for candidate in selected_value],
        }
    return fields


class Candidates:
    def __init__(self, domain, *, executives=False):
        self.domain = domain
        self.appendix = Appendix(domain, executives=executives)
        self.items = {field: [] for field in (*FIELDS, *(EXECUTIVE_PHRASES if executives else ()))}
        self.seen = set()
        self.dates = {}

    def add(self, page, *, legacy=False, text_is_safe=lambda _: True):
        url, text, provider = page["url"], page["text"], page["provider"]
        if provider not in PROVIDERS:
            return
        try:
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None:
                return
        except ValueError:
            return
        kind, published = page_metadata(self.domain, page, legacy)
        self.dates.setdefault(url, effective_date(text, published))
        version = (url, text, provider, kind, published)
        if version in self.seen:
            return
        self.seen.add(version)
        for field, value, excerpt in self.appendix.excerpts(text):
            if text_is_safe(excerpt):
                self.items[field].append({
                    "value": value, "url": url, "excerpt": excerpt, "provider": provider,
                    "kind": kind, "published_at": published,
                })

    def gaps(self):
        return [key for key in FIELDS if not self.items[key]]

    def serialized(self):
        return {key: ranked(values) for key, values in self.items.items()}


def upgrade_fields(dossier, last_ready):
    if not last_ready:
        return unknown_fields()
    collector = Candidates(dossier["domain"])
    for call in last_ready["calls"]:
        for page in call.get("pages", []):
            collector.add(page, legacy=True)
            snippet = page.get("description")
            if isinstance(snippet, str) and snippet != page["text"]:
                collector.add({**page, "text": snippet}, legacy=True)
    # Stage 1 could cite a provider-served research quotation without fetching its page.
    # Keep that provenance, and use the gathered page metadata whenever it exists.
    for field, values in last_ready["candidates"].items():
        source_keys = {(item["value"], item["url"]) for item in collector.items[field]}
        for candidate in values:
            value = candidate["value"]
            for citation in candidate["citations"]:
                if (value, citation["url"]) in source_keys:
                    continue
                if collector.appendix.claim_supports(citation["excerpt"], field, value):
                    collector.items[field].append({**citation, "value": value, "kind": None, "published_at": None})
    return select(collector.items, dossier["researched_at"])
