"""Lineage normalization and bounded traversal of canonical sources."""

import re
from urllib.parse import urlsplit

LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
CANONICAL_LIMIT = 3


def normalized_domain(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().removesuffix(".").removeprefix("www.")
    labels = normalized.split(".")
    if len(normalized) <= 253 and len(labels) >= 2 and all(LABEL.fullmatch(label) for label in labels):
        return normalized
    return None


def address(value):
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        if url.scheme in ("https", "http") and url.hostname and url.username is None and url.password is None:
            return url
    except ValueError:
        pass
    return None


def url_host(url):
    parsed = address(url)
    return normalized_domain(parsed.hostname) if parsed else None


def metadata(page, domain):
    headers = page.get("headers", {})
    host = url_host(page["url"])
    registrant = normalized_domain(headers.get("Registrant")) or host or domain
    first = normalized_domain(headers.get("First-Published-By"))
    canonical = headers.get("Canonical")
    if not url_host(canonical) or canonical == page["url"]:
        canonical = None
    declared = headers.get("Kind")
    lookalike = declared == "own" and registrant != host
    if declared in ("own", "filing", "news", "aggregator"):
        kind = declared
    else:
        kind = "own" if host == domain else "aggregator"
    if kind == "own" and registrant != domain:
        kind = "aggregator"
    return {"registrant": registrant, "first": first, "canonical": canonical,
            "kind": kind, "lookalike": lookalike}


def origin(url, pages, domain):
    for depth in range(CANONICAL_LIMIT + 1):
        page = pages.get(url)
        if page is None:
            return url_host(url) or domain
        meta = metadata(page, domain)
        if meta["first"]:
            return meta["first"]
        if not meta["canonical"]:
            return domain if meta["lookalike"] else meta["registrant"]
        url = meta["canonical"]
    return url_host(url) or domain


def missing_originals(pages, roots, domain):
    missing = {}
    for url in roots:
        for _ in range(CANONICAL_LIMIT):
            page = pages.get(url)
            if page is None:
                break
            meta = metadata(page, domain)
            if meta["first"] or not meta["canonical"]:
                break
            url = meta["canonical"]
            if url not in pages:
                missing[url] = None
                break
    return missing.keys()
