"""Appendix A sentence boundaries, value formats and citation selection."""
from bisect import bisect_left
from datetime import datetime
from decimal import Decimal, localcontext
from urllib.parse import urlsplit

import regex as re

PHRASES = {
    "legal_name": "legal name|registered name|registered as|registered company|legal entity|name of record",
    "hq_city": "headquartered in|headquarters in|head office in|based in|registered office in|registered seat in",
    "ceo": "chief executive officer|chief executive|CEO",
    "founded_year": "founded|founding|established|incorporated",
    "headcount_range": "employs|employees|staff|people|headcount|workforce",
    "funding_total": "raised|funding|invested|investment",
}
BOUNDS = [10, 50, 200, 500, 1000, 5000, 10000]
RANGES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10001+"]
LEFT, RIGHT = r"(?<![\p{L}\p{N}])", r"(?![\p{L}\p{N}])"


def words(pattern):
    return LEFT + "(?:" + pattern + ")" + RIGHT


def phrase(pattern):
    return re.compile(words("(?i:" + pattern + ")"))


STATEMENTS = {k: phrase(v) for k, v in PHRASES.items()}
NEGATIONS = phrase("in talks to|plans to|planning to|wants to|expects to|hopes to|aims to|seeking|could|would|might|reportedly|rumoured|former|formerly|will become|not")
SUFFIXES = "Inc. Corp. LLC LLP L.P. Ltd Limited plc PLC GmbH AG KG SE AS A/S ASA AB Oy Oyj B.V. N.V. S.A. S.A.S. S.L. S.r.l. S.p.A. s.r.o. a.s. K.K.".split() + ["Pty Ltd"]
SUFFIX = "|".join(map(re.escape, SUFFIXES))
DOTTED_END = re.compile(LEFT + "(?:" + "|".join(map(re.escape, [x for x in SUFFIXES if x.endswith(".")])) + ")$")
STOP = re.compile(r'([.!?])["”’)]*(?=\s)')
CAP = words(r"\p{Lu}\p{Ll}+")
ENTITY_WORD = words(r"\p{Lu}\p{Ll}+|\p{Lu}{2,}")
PEOPLE = re.compile(CAP + "(?: " + CAP + ")*")
CITY = re.compile(STATEMENTS["hq_city"].pattern + " (" + CAP + "(?:[ -]" + CAP + ")*)")
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NUM_START, NUM_END = r"(?<![0-9][,.])", r"(?![,.][0-9])"
PLAIN = re.compile(LEFT + NUM_START + NUMBER + NUM_END + RIGHT)
LONG_SCALE = "thousand|million|billion"
AMOUNT = re.compile(LEFT + NUM_START + r"(?:(?:US\$|\$|USD) ?(?P<num>" + NUMBER +
                    r")(?P<scale>mn|bn|m|k| (?:" + LONG_SCALE + r"))?|(?P<num>" + NUMBER +
                    r")(?P<scale> (?:" + LONG_SCALE + r"))? (?:US )?dollars)" + NUM_END + RIGHT, re.I)
SCALES = {"": 1, "k": 1000, "thousand": 1000, "m": 10**6, "mn": 10**6, "million": 10**6,
          "bn": 10**9, "billion": 10**9}
HEADER = re.compile(r"^[A-Z][a-z]*(?:-[A-Z][a-z]*)*: ")


def prose(text):
    lines = text.splitlines()
    if lines and HEADER.match(lines[0]):
        for i, line in enumerate(lines):
            if not line.strip():
                return lines[i + 1:], lines[:i]
        return [], lines
    return lines, []


# Keep the visible parts of links available as prose. The sentinel separates
# source spans so a citation is always a contiguous slice of the served body.
BREAK = "\x00"
HTML_HIDDEN = re.compile(r"""
    <!--.*?-->|<(script|style)\b[^>]*>.*?</(?:script|style)\s*>
    | </?[A-Za-z][\w:-]*(?=[\s/>])(?:[^>'"]++|'[^']*'|"[^"]*")*>
    | ^[ \t]{0,3}\[[^\]\r\n]+\]:[^\r\n]*
    """, re.VERBOSE | re.DOTALL | re.MULTILINE | re.IGNORECASE)
DELIMITER = re.compile(r"\\.|[\[\]()]")
LINK_EDGE = re.compile(r"\\.|!\[|\[|\]")


def mask_links(text):
    # Pair the delimiters in one pass. Provider text can include malformed
    # or deeply nested brackets; repeated lookahead from each opener is costly.
    stacks = {"[": [], "(": []}
    pairs = {}
    for match in DELIMITER.finditer(text):
        char = match[0]
        if char in stacks:
            stacks[char].append(match.start())
        elif char in ("]", ")"):
            stack = stacks["[" if char == "]" else "("]
            if stack:
                pairs[stack.pop()] = match.start()
    parts = []
    end = 0
    for match in LINK_EDGE.finditer(text):
        start = match.start()
        if start < end:
            continue
        token = match[0]
        if token == "![" and start + 1 in pairs:
            close = pairs[start + 1]
            stop = pairs.get(close + 1, close) + 1
        elif token == "[" and start in pairs and pairs[start] + 1 in pairs:
            stop = start + 1
        elif token == "]" and start + 1 in pairs:
            stop = pairs[start + 1] + 1
        else:
            continue
        parts.extend((text[end:start], BREAK, "\n" * text.count("\n", start, stop), BREAK))
        end = stop
    parts.append(text[end:])
    return "".join(parts)


def qualified_spans(lines):
    if lines and lines[0].lstrip().startswith("%PDF-"):
        # Some extracts return the PDF file bytes as text. Only the browser's
        # rendered prose can support a candidate.
        return
    source = "\n".join(lines)

    def mask(match):
        token = match[0]
        if token.startswith("<") and re.fullmatch(r"<[a-z][a-z0-9+.-]*://[^\s<>]+>", token, re.I):
            return token
        return BREAK + "\n" * token.count("\n") + BREAK

    marked = mask_links(HTML_HIDDEN.sub(mask, source))
    for sentence in sentences(marked.splitlines()):
        fragments = [s.strip().lstrip("[").strip() for s in sentence.split(BREAK)]
        fragments = [s for s in fragments if s]
        if fragments:
            yield " ".join(fragments), fragments


def sentences(lines):
    for raw in lines:
        line = " ".join(raw.split())
        start = 0
        for end in STOP.finditer(line):
            if end[1] == "." and DOTTED_END.search(line, max(0, end.start()-12), end.start()+1):
                continue
            yield line[start:end.end()].strip()
            start = end.end()
        if line[start:].strip():
            yield line[start:].strip()


def unknowns():
    return {k: {"value": None, "status": "unknown", "citations": [], "candidates": []} for k in PHRASES}


class Evidence:
    def __init__(self, domain, retrieved_at):
        self.retrieved_at = retrieved_at
        self.domain = domain
        name = domain.split(".")[0].replace("-", " ")
        self.name = phrase(re.escape(name))
        self.subject = phrase(re.escape(domain) + "|" + re.escape(name))
        self.legal = re.compile(self.subject.pattern + "(?: " + ENTITY_WORD + ")*?,? (?:" + SUFFIX + ")" + RIGHT)
        self.choices = {f: {} for f in PHRASES}

    def values(self, field, sentence):
        if field == "legal_name":
            return self.legal.findall(sentence)
        if field == "hq_city":
            return CITY.findall(sentence)
        if field == "ceo":
            masked = STATEMENTS[field].sub("|", self.name.sub("|", sentence))
            return [run for run in PEOPLE.findall(masked) if 2 <= len(run.split()) <= 3]
        if field == "funding_total":
            amounts = []
            for match in AMOUNT.finditer(sentence):
                value = Decimal(match["num"].replace(",", ""))
                with localcontext() as ctx:
                    ctx.prec = len(match["num"]) + 12
                    dollars = value * SCALES[(match["scale"] or "").strip().lower()]
                if dollars == dollars.to_integral_value():
                    amounts.append(int(dollars))
            return amounts
        numbers = PLAIN.findall(AMOUNT.sub("|", sentence))
        if field == "founded_year":
            return [int(n) for n in numbers if len(n) == 4 and n.isdigit() and 1800 <= int(n) <= 2099]
        counts = [int(n.replace(",", "")) for n in numbers if "." not in n]
        return [RANGES[bisect_left(BOUNDS, n)] for n in counts if n >= 1]

    def add(self, provider, url, lines, kind, published, claim=None, *, literal=False):
        # Stage 1 exports retain the support contract of the build that
        # collected them. Fresh builds use only reader-visible evidence.
        spans = ((s, [s]) for s in sentences(lines)) if literal else qualified_spans(lines)
        for sentence, fragments in spans:
            if not self.subject.search(sentence) or NEGATIONS.search(sentence):
                continue
            for field, marker in STATEMENTS.items():
                if (claim and field != claim[0]) or not marker.search(sentence):
                    continue
                values = set(self.values(field, sentence))
                if len(values) != 1:
                    continue
                value = values.pop()
                if claim and value != claim[1]:
                    continue
                # Check ambiguity over the full visible sentence. The quoted
                # span must itself name the subject, state the field, and carry
                # precisely that value, without rejoining text across a URL.
                excerpt = next((part for part in fragments if len(part) <= 500
                                and self.subject.search(part) and marker.search(part)
                                and set(self.values(field, part)) == {value}), None)
                if excerpt is None:
                    continue
                candidate = {"url": url, "excerpt": excerpt, "provider": provider, "value": value,
                             "retrieved_at": self.retrieved_at, "kind": kind, "published_at": published}
                key = (url, value)
                previous = self.choices[field].get(key)
                if previous is None or excerpt_order(candidate) < excerpt_order(previous):
                    self.choices[field][key] = candidate

    def fields(self):
        result = unknowns()
        for field, candidates in self.choices.items():
            ranked = sorted(candidates.values(), key=rank)
            if ranked:
                value = ranked[0]["value"]
                citations = [{k: c[k] for k in ("url", "excerpt", "provider")} for c in ranked if c["value"] == value]
                result[field] = {"value": value, "status": "known" if len(citations) == len(ranked) else "contested",
                                 "citations": citations, "candidates": [dict(c, selected=i == 0) for i, c in enumerate(ranked)]}
        return result


PROVIDERS = {"nimble": 0, "tavily": 1, "kernel": 2, "browserbase": 3}
AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2, None: 2}
STAMP = re.compile(r"(\d{4}-\d\d-\d\d[Tt]\d\d:\d\d:\d\d)(\.\d+)?([Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)", re.ASCII)


def publication_instant(value):
    match = STAMP.fullmatch(value or "")
    if match:
        try:
            dt = datetime.fromisoformat(match[1] + match[3].upper().replace("Z", "+00:00"))
            # Integer seconds and a separate arbitrary-precision fraction keep
            # ties exact, including for dates near midnight in another offset.
            seconds = dt.toordinal() * 86400 + dt.hour * 3600 + dt.minute * 60 + dt.second - int(dt.utcoffset().total_seconds())
            return seconds, Decimal(match[2] or "0")
        except ValueError:
            pass
    return None


def rank(c):
    stamp = publication_instant(c["published_at"])
    seconds, fraction = stamp or (0, Decimal(0))
    return (AUTHORITY[c["kind"]], stamp is None, -seconds, fraction.copy_negate(),
            c["url"], PROVIDERS[c["provider"]], c["value"])


def excerpt_order(c):
    text = c["excerpt"]
    return (PROVIDERS[c["provider"]], bool(re.search(r"<[^>]+>|\]\(|\|", text)), len(text), text)


def page_metadata(headers, url, domain, imported):
    try:
        host = (urlsplit(url).hostname or "").lower().removesuffix(".").removeprefix("www.")
    except ValueError:
        host = ""
    pairs = dict(h.split(": ", 1) for h in headers if ": " in h)
    kind = pairs.get("Kind")
    if kind not in ("own", "filing", "news", "aggregator"):
        kind = None if imported and "Kind" not in pairs else ("own" if host == domain else "aggregator")
    published = pairs.get("Published")
    return kind, published if publication_instant(published) else None


def resolve(domain, retrieved_at, pages, *, imported=False, discovery=False):
    evidence = Evidence(domain, retrieved_at)
    by_url = {}
    for page in pages:
        by_url.setdefault(page["url"], []).append(page)
    for url, versions in by_url.items():
        parsed = [(p, *prose(p["text"])) for p in versions]
        # Search and ordinary extracts can show a page before scripts replace
        # its text. They can guide URL discovery but cannot prove current
        # browser-visible prose, even if a browser request failed or timed out.
        if not imported and not discovery:
            parsed = [row for row in parsed if row[0]["method"] == "render"]
        headers = next((hdr for _, _, hdr in reversed(parsed) if hdr), [])
        kind, published = page_metadata(headers, url, domain, imported)
        if imported and published is None:
            published = next((p["date"] for p in versions if publication_instant(p.get("date"))), None)
        # A rendered copy supersedes any pre-load text. Historical imports
        # instead make every text served to that Stage 1 build eligible.
        rendered = [(p, lines, h) for p, lines, h in parsed if p["method"] == "render"]
        full = [(p, lines, h) for p, lines, h in parsed if p["method"] in ("extract", "deep")]
        chosen = parsed if imported else (rendered or full or parsed)
        for page, lines, _ in chosen:
            evidence.add(page["provider"], url, lines, kind, published, page.get("claim"),
                         literal=imported or page.get("plain", False))
    return evidence.fields()
