"""Normalize and resolve independent origins from gathered pages (R59–R60)."""

import re
from urllib.parse import urlsplit


LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)


def domain(value):
    if not isinstance(value, str):
        return None
    host = value.strip().lower().removesuffix(".").removeprefix("www.")
    labels = host.split(".")
    return host if len(host) <= 253 and len(labels) >= 2 and all(map(LABEL.fullmatch, labels)) else None


def url_key(url):
    if not isinstance(url, str) or not url or any(c.isspace() for c in url):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.username is not None or not (host := domain(parts.hostname)):
            return None
        port = parts.port or (443 if parts.scheme == "https" else 80)
        return parts.scheme, host, port, parts.path or "/", parts.query
    except ValueError:
        return None


def url_host(url):
    key = url_key(url)
    return key[1] if key else None


class Origins:
    def __init__(self, company):
        self.company = company
        self.pages = {}
        self.redirects = {}

    def add(self, url, headers):
        key = url_key(url)
        if key:
            self.pages.setdefault(key, headers)

    def link_redirect(self, requested, served):
        if requested != served and requested not in self.pages and served in self.pages:
            self.redirects.setdefault(requested, served)

    def resolve(self, url):
        """Return the origin and any original still needed inside the three-hop limit."""
        key = url_key(url)
        if key is None:
            return self.company, None
        for hops in range(4):
            key = self.redirects.get(key, key)
            headers = self.pages.get(key)
            if headers is None:
                return key[1], None
            if first := domain(headers.get("First-Published-By")):
                return first, None
            canonical = headers.get("Canonical")
            target = url_key(canonical)
            if target and self.redirects.get(target, target) != key:
                if hops == 3:
                    return target[1], None
                if self.redirects.get(target, target) not in self.pages:
                    return target[1], canonical
                key = target
                continue
            registrant = domain(headers.get("Registrant")) or key[1]
            if headers.get("Kind") == "own" and registrant != key[1]:
                return self.company, None
            return registrant, None
        return key[1], None
