"""Accumulate visible, cited evidence and deterministically project the six fields."""
import re
from datetime import timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

from evidence import FIELDS, TITLES, HEADER, Support, sentences
from timestamps import calendar_date, parse_stamp


AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2, None: 2}
PROVIDERS = {name: n for n, name in enumerate(("nimble", "tavily", "kernel", "browserbase"))}
BLOCKS = set("address article aside blockquote br dd div dl dt figcaption figure footer h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section table td th tr ul".split())
VOID = set("area base br col embed hr img input link meta param source track wbr".split())
IGNORE = {"script", "style", "template", "noscript", "head", "svg", "iframe"}


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.out = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (tag in IGNORE or "hidden" in attrs or attrs.get("aria-hidden") == "true"
                  or re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", attrs.get("style") or "", re.I))
        if self.stack:
            parent, parent_hidden, closed = self.stack[-1]
            hidden = hidden or parent_hidden or (closed and tag != "summary")
        if not hidden and (tag in BLOCKS or tag == "img"):
            self.out.append("\n")
        if tag not in VOID:
            self.stack.append((tag, hidden, tag == "details" and "open" not in attrs))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                hidden = self.stack[i][1]
                del self.stack[i:]
                if not hidden and tag in BLOCKS:
                    self.out.append("\n")
                break

    def handle_data(self, value):
        if not self.stack or not (self.stack[-1][1] or self.stack[-1][2]):
            self.out.append(value)


MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
MARKUP = re.compile(r"[\[*_`]|~~|^ {0,3}(?:#{1,6} |>|[-*+] )", re.M)
HTML_TAG = re.compile(r"</?[A-Za-z][\w:-]*(?:\s+[^<>]*|/?)>")


def html_text(source):
    reader = VisibleText()
    reader.feed(source)
    reader.close()
    return "".join(reader.out).strip()


def visible_text(source):
    # Provider extracts can mix HTML and Markdown. Decode both representations
    # before applying the sentence rules, so link targets and image labels
    # never become words or amounts in a citation.
    text = html_text(source) if HTML_TAG.search(source) else source.strip()
    if not MARKUP.search(text):
        return text

    header = ""
    lines = text.splitlines(keepends=True)
    if lines and HEADER.match(lines[0]):
        boundary = next((i for i, line in enumerate(lines) if not line.strip()), len(lines))
        header = "".join(lines[:boundary]).rstrip() + "\n\n"
        text = "".join(lines[boundary:])
    rendered = html_text(MARKDOWN.render(text))
    # Incomplete links sometimes occur at the edge of a truncated extract.
    # Their visible label and destination cannot reliably be separated.
    prose = "\n".join(line for line in rendered.splitlines() if "](" not in line and "][" not in line)
    return (header + prose).strip()


def host_of(url):
    try:
        return (urlsplit(url).hostname or "").lower().removesuffix(".").removeprefix("www.")
    except ValueError:
        return ""


def metadata(text):
    lines = text.splitlines()
    attrs = {}
    if lines and HEADER.match(lines[0]):
        for line in lines:
            if not line.strip():
                break
            key, sep, value = line.partition(":")
            if sep:
                attrs[key] = value.strip()
    kind = attrs.get("Kind")
    published = attrs.get("Published")
    if published:
        try:
            parse_stamp(published)
        except ValueError:
            published = None
    try:
        effective = calendar_date(attrs.get("Effective"))
    except ValueError:
        effective = None
        if published:
            try:
                effective = parse_stamp(published)[0].astimezone(timezone.utc).date().isoformat()
            except OverflowError:
                pass
    return (kind if kind in AUTHORITY else None), published or None, effective


def rank(entries):
    # Stable passes keep full subsecond precision for descending publication time.
    entries.sort(key=lambda c: (c["url"], PROVIDERS[c["provider"]], c["value"]))
    entries.sort(key=lambda c: (c["published_at"] is not None, parse_stamp(c["published_at"]) if c["published_at"] else ()), reverse=True)
    entries.sort(key=lambda c: AUTHORITY[c["kind"]])
    return entries


def select_field(field, candidates):
    """Use the same ordering and citation rules for current and effective-date reads."""
    groups = {title: [] for title in TITLES} if field == "executives" else {None: []}
    for candidate in candidates:
        groups[candidate.get("title")].append(candidate)
    entries, citations, members, dates = [], [], [], []
    value = None
    contested = False
    for title, group in groups.items():
        if not group:
            continue
        ordered = rank(group)
        chosen = ordered[0]["value"]
        dates.append(ordered[0]["true_from"])
        if title:
            members.append({"title": title, "name": chosen})
        else:
            value = chosen
        for i, candidate in enumerate(ordered):
            entries.append({**candidate, "selected": i == 0})
            if candidate["value"] == chosen:
                citations.append({k: candidate[k] for k in ("url", "excerpt", "provider")})
            else:
                contested = True
    if members:
        value = members
    status = "contested" if contested else "known" if entries else "unknown"
    return {"value": value, "status": status, "citations": citations, "candidates": entries,
            "true_from": max(dates) if dates and all(dates) else None, "learned_at": None}


class Candidates:
    def __init__(self, domain, retrieved_at, imported=False, executives=True):
        self.domain = domain
        self.support = Support(domain)
        self.time = retrieved_at
        self.imported = imported
        self.meta = {}
        self.by_field = {f: {} for f in (*FIELDS, *TITLES) if executives or f in FIELDS}

    def add(self, field, value, url, provider, sentence):
        if provider not in PROVIDERS or not url or field not in self.by_field:
            return
        slot = self.by_field[field]
        key = url, value
        previous = slot.get(key)
        if previous is None or (PROVIDERS[provider], sentence) < (PROVIDERS[previous["provider"]], previous["excerpt"]):
            slot[key] = {"value": value, "url": url, "provider": provider, "excerpt": sentence, "retrieved_at": self.time}

    def page(self, provider, url, text):
        kind, published, effective = metadata(text)
        old = self.meta.get(url, (None, None, None))
        self.meta[url] = kind or old[0], published or old[1], effective or old[2]
        for sentence in sentences(text):
            for field, value in self.support.parse(sentence).items():
                self.add(field, value, url, provider, sentence)

    def fields(self):
        grouped = {field: [] for field in (*FIELDS, "executives")}
        for field, candidates in self.by_field.items():
            for c in candidates.values():
                kind, published, effective = self.meta.get(c["url"], (None, None, None))
                if kind is None and not self.imported:
                    kind = "own" if host_of(c["url"]) == self.domain else "aggregator"
                entry = {**c, "kind": kind, "published_at": published, "true_from": effective, "learned_at": self.time}
                if field in TITLES:
                    entry["title"] = field
                    grouped["executives"].append(entry)
                else:
                    grouped[field].append(entry)
        return {field: select_field(field, entries) for field, entries in grouped.items()}


def legacy_book(domain, build, stage_one):
    book = Candidates(domain, build["time"], imported=stage_one, executives=False)
    for page in build["pages"]:
        book.page(page["provider"], page["url"], page["text"])
    if stage_one:
        for candidate in build["candidates"]:
            citation = candidate["citation"]
            book.add(candidate["field"], candidate["value"], citation["url"], citation["provider"], citation["excerpt"])
    return book
