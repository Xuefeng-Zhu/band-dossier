"""Page metadata, evidence candidates, and the Stage 2 ranking rule."""

from datetime import datetime, timedelta
from decimal import Decimal
import re
from urllib.parse import urlsplit

from evidence import EXECUTIVE_TITLES, FIELDS, collapse, from_page, prose, supports


AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2, None: 2}
PROVIDERS = ("nimble", "tavily", "kernel", "browserbase")
PUBLICATION = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})[Tt]([0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(\.[0-9]+)?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def publication_time(text):
    """Represent the timestamp on a common time scale without rounding fractions."""
    match = PUBLICATION.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        return None
    day, clock, fractional, offset = match.groups()
    try:
        moment = datetime.fromisoformat(f"{day}T{clock}{offset.upper()}")
    except ValueError:
        return None
    local_seconds = moment.toordinal() * 86400 + moment.hour * 3600 + moment.minute * 60 + moment.second
    seconds = local_seconds - moment.utcoffset() // timedelta(seconds=1)
    return seconds, Decimal(fractional or "0")


def page_headers(text):
    lines = text.splitlines()
    body = prose(text)
    headers = {}
    for line in lines[:len(lines) - len(body)]:
        name, _, value = line.partition(":")
        if name in ("Kind", "Published", "Effective"):
            headers.setdefault(name, value.strip())
    return headers


def page_metadata(domain, page, imported):
    headers = page_headers(page["text"])
    kind = headers.get("Kind")
    if kind not in ("own", "filing", "news", "aggregator"):
        host = urlsplit(page["url"]).hostname or ""
        kind = None if imported else (
            "own" if host.lower().removesuffix(".").removeprefix("www.") == domain else "aggregator"
        )
    published = headers.get("Published")
    return kind, published if publication_time(published) is not None else None


def rank(candidate):
    instant = publication_time(candidate["published_at"])
    seconds, fraction = instant or (0, Decimal(0))
    return (AUTHORITY[candidate["kind"]], instant is None, -seconds, fraction.copy_negate(),
            candidate["url"], PROVIDERS.index(candidate["provider"]), candidate["value"], candidate["excerpt"])


def select(candidates):
    ordered = sorted(candidates, key=rank)
    if not ordered:
        return {"value": None, "status": "unknown", "citations": [], "candidates": []}
    value = ordered[0]["value"]
    matching = [{key: item[key] for key in ("url", "excerpt", "provider")}
                for item in ordered if item["value"] == value]
    return {
        "value": value, "status": "known" if len(matching) == len(ordered) else "contested",
        "citations": matching,
        "candidates": [{**item, "selected": index == 0} for index, item in enumerate(ordered)],
    }


def empty_fields():
    return {field: select(()) for field in FIELDS}


def quoted_in(text, excerpt):
    text = collapse(" ".join(prose(text)))
    offset = text.find(excerpt)
    while offset != -1:
        end = offset + len(excerpt)
        if (not offset or not (text[offset - 1].isalnum() and excerpt[0].isalnum())) and (
                end == len(text) or not (text[end].isalnum() and excerpt[-1].isalnum())):
            return True
        offset = text.find(excerpt, offset + 1)
    return False


def candidates_from_pages(domain, pages, retrieved_at, *, answers=(), imported=False,
                          previous=None, include_executives=False):
    parsed_fields = (*FIELDS, *EXECUTIVE_TITLES) if include_executives else FIELDS
    by_field = {field: {} for field in parsed_fields}
    versions = {}

    def add(field, value, excerpt, page, kind, published):
        item = {"value": value, "url": page["url"], "excerpt": excerpt,
                "provider": page["provider"], "kind": kind, "published_at": published,
                "retrieved_at": retrieved_at}
        key = (page["url"], value)
        existing = by_field[field].get(key)
        if existing is None or rank(item) < rank(existing):
            by_field[field][key] = item

    for page in pages:
        if page["scope"] not in (("search", "citation", "rendered") if imported else ("rendered",)):
            continue
        kind, published = page_metadata(domain, page, imported)
        versions.setdefault((page["url"], page["provider"]), []).append((page, kind, published))
        for field, value, excerpt in from_page(domain, page["text"], parsed_fields):
            add(field, value, excerpt, page, kind, published)

    def verify(field, value, text, url):
        if field not in FIELDS or not isinstance(text, str):
            return
        excerpt = collapse(text)
        if not supports(domain, field, value, excerpt):
            return
        for provider in PROVIDERS:
            for page, kind, published in versions.get((url, provider), ()):
                if quoted_in(page["text"], excerpt):
                    add(field, value, excerpt, page, kind, published)

    for answer in answers:
        values = answer.get("structured")
        if not isinstance(values, dict):
            continue
        for claim in answer["claims"]:
            path, url = claim.get("field"), claim.get("url")
            if isinstance(path, str) and isinstance(url, str):
                field = path.removeprefix("$.")
                verify(field, values.get(field), claim.get("excerpt"), url)

    # Preserve quotations selected by Stage 1, including evidence that
    # crossed a line break and was verified against the stored page.
    if previous:
        for field, entry in previous.items():
            for citation in entry["citations"]:
                verify(field, entry["value"], citation["excerpt"], citation["url"])

    return {field: select(by_field[field].values()) for field in parsed_fields}
