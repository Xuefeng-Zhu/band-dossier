"""Page ownership and the bounded original-publication chain."""
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
HOST = re.compile(LABEL + r"(?:\." + LABEL + r")+")


def normalized_domain(value):
    if not isinstance(value, str):
        return None
    host = value.strip().lower().removesuffix(".").removeprefix("www.")
    return host if len(host) <= 253 and HOST.fullmatch(host) else None


def host_of(url):
    try:
        return normalized_domain(urlsplit(url).hostname) or ""
    except ValueError:
        return ""


def url_key(url):
    """Normalize the authority for chain comparisons, preserving the resource path."""
    if not isinstance(url, str) or any(ch.isspace() for ch in url):
        return None
    try:
        parts = urlsplit(url)
        host = normalized_domain(parts.hostname)
        if parts.scheme not in ("http", "https") or not host:
            return None
        port = parts.port
        netloc = host + (f":{port}" if port is not None else "")
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return None


@dataclass(frozen=True)
class Source:
    registrant: str
    publisher: str | None
    original: str | None
    lookalike: bool

    @classmethod
    def read(cls, url, headers):
        host = host_of(url)
        registrant = normalized_domain(headers.get("Registrant")) or host
        publisher = normalized_domain(headers.get("First-Published-By"))
        target = headers.get("Canonical")
        canonical = url_key(target)
        if canonical == url_key(url):
            canonical = None
        return cls(registrant, publisher, canonical, headers.get("Kind") == "own" and registrant != host)


def origin(domain, url, sources):
    # The bound also gives cycles a deterministic fallback relative to each root.
    for followed in range(4):
        source = sources.get(url)
        if source is None:
            return host_of(url)
        if source.publisher:
            return source.publisher
        if not source.original:
            return domain if source.lookalike else source.registrant
        url = source.original
    return host_of(url)
