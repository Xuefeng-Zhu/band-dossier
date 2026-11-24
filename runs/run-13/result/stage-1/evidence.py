"""Appendix A sentence boundaries, value formats and citation selection."""
from bisect import bisect_left
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
    return {k: {"value": None, "status": "unknown", "citations": []} for k in PHRASES}


class Evidence:
    def __init__(self, domain):
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

    def add(self, provider, url, text, *, claim=None, date="", source="extract"):
        if not url or not isinstance(text, str):
            return
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return
        own = host == self.domain or host.endswith("." + self.domain)
        lines, headers = prose(text)
        for h in headers:
            if h.startswith(("Effective: ", "Published: ")):
                date = max(date or "", h.partition(": ")[2][:10])
        for s in sentences(lines):
            if not 0 < len(s) <= 500 or not self.subject.search(s) or NEGATIONS.search(s):
                continue
            for field, marker in STATEMENTS.items():
                if (claim and field != claim[0]) or not marker.search(s):
                    continue
                vals = set(self.values(field, s))
                if len(vals) != 1:
                    continue
                value = vals.pop()
                if claim and value != claim[1]:
                    continue
                # Keep the original sentence even when it is marked up. Prefer a direct,
                # company-wide assertion to a testimonial or a navigation fragment.
                context = bool(re.search(r"(?i)\b(?:customer|client|partner|testimonial|portfolio|per employee|grant)\b", s))
                noisy = bool(re.search(r"<[^>]+>|\]\(|https?://|\|", s))
                direct = bool(re.search(self.subject.pattern + r"(?: is| was| has| employs| raised|['’]s)", s, re.I))
                score = (not context, not noisy, direct, (date or "")[:10], own, source != "search", -len(s))
                citation = {"url": url, "excerpt": s, "provider": provider}
                old = self.choices[field].get(value)
                if old is None or score > old[0]:
                    self.choices[field][value] = (score, citation)

    def fields(self):
        result = unknowns()
        for field, values in self.choices.items():
            if values:
                value, (_, citation) = max(values.items(), key=lambda pair: pair[1][0])
                result[field] = {"value": value, "status": "known", "citations": [citation]}
        return result

    def gaps(self):
        return [k for k, v in self.choices.items() if not v]
