"""Interpret provider text according to the stage's citation grammar."""

from decimal import Decimal, localcontext
from functools import lru_cache

import regex as re

PHRASES = {
    "legal_name": ("legal name", "registered name", "registered as", "registered company", "legal entity", "name of record"),
    "hq_city": ("headquartered in", "headquarters in", "head office in", "based in", "registered office in", "registered seat in"),
    "ceo": ("chief executive officer", "chief executive", "CEO"),
    "founded_year": ("founded", "founding", "established", "incorporated"),
    "headcount_range": ("employs", "employees", "staff", "people", "headcount", "workforce"),
    "funding_total": ("raised", "funding", "invested", "investment"),
}
SUFFIXES = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC",
            "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.",
            "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.")
LEFT = r"(?<![\p{L}\p{N}])"
RIGHT = r"(?![\p{L}\p{N}])"
CAPITAL = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
CAPITAL_OR_UPPER = LEFT + r"(?:\p{Lu}\p{Ll}+|\p{Lu}{2,})" + RIGHT


def alternatives(strings):
    return "(?:" + "|".join(map(re.escape, strings)) + ")"


def phrase_pattern(strings):
    return LEFT + "(?i:" + alternatives(strings) + ")" + RIGHT


STATEMENT = {f: re.compile(phrase_pattern(phrases)) for f, phrases in PHRASES.items()}
NEGATION = re.compile(phrase_pattern((
    "in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to",
    "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured", "former",
    "formerly", "will become", "not",
)))
SUFFIX = alternatives(SUFFIXES)
SUFFIX_END = re.compile(LEFT + alternatives(s for s in SUFFIXES if s.endswith(".")) + "$")
BREAK = re.compile(r'([.!?])["”’)]*(?=\s)')
CITY = re.compile(f"{CAPITAL}(?:[ -]{CAPITAL})*")
NAME_RUN = re.compile(f"{CAPITAL}(?: {CAPITAL})*")
HEADER = re.compile(r"^\p{Lu}\p{Ll}+(?:-\p{Lu}\p{Ll}+)*:")
DIGITS = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NUM_LEFT = LEFT + r"(?<![0-9][,.])"
NUM_RIGHT = RIGHT + r"(?![,.][0-9])"
NUMBER = re.compile(NUM_LEFT + DIGITS + NUM_RIGHT)
AMOUNT = re.compile(
    NUM_LEFT + rf"(?:(?:US\$|USD|\$) ?(?P<n>{DIGITS})(?P<u>mn|bn|m|k| thousand| million| billion)?"
    + rf"|(?P<n>{DIGITS})(?P<u> thousand| million| billion)? (?:US )?dollars)" + NUM_RIGHT,
    re.I,
)
SCALE = {"": 1, "k": 1000, "thousand": 1000, "m": 10**6, "mn": 10**6, "million": 10**6,
         "bn": 10**9, "billion": 10**9}
BANDS = ((10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"), (1000, "501-1000"),
         (5000, "1001-5000"), (10000, "5001-10000"))


def band(n):
    return next((label for bound, label in BANDS if n <= bound), "10001+")


def claim_matches(field, claim, supported):
    """A research claim can express the same quantity in a different unit or format."""
    if type(claim) not in (int, str, float):
        return False
    if type(claim) is type(supported) and claim == supported:
        return True
    raw = str(claim).strip()
    if len(raw) > 500:
        return False
    if field == "headcount_range":
        parts = re.split(r"\s*[-–]\s*", raw)
        if 1 <= len(parts) <= 2 and all(NUMBER.fullmatch(n) and "." not in n for n in parts):
            counts = [int(n.replace(",", "")) for n in parts]
            return all(n >= 1 and band(n) == supported for n in counts)
    if field in ("founded_year", "funding_total"):
        if NUMBER.fullmatch(raw):
            return Decimal(raw.replace(",", "")) == supported
        if field == "funding_total" and (match := AMOUNT.fullmatch(raw)):
            return dollars(match) == supported
    return False


def dollars(match):
    with localcontext() as context:
        context.prec = len(match[0]) + 12
        return Decimal(match["n"].replace(",", "")) * SCALE[(match["u"] or "").strip().lower()]


@lru_cache(maxsize=512)
def subject_patterns(domain):
    name = domain.split(".")[0].replace("-", " ")
    company = phrase_pattern((domain, name))
    legal = company + f"(?: {CAPITAL_OR_UPPER})*?,? {SUFFIX}" + RIGHT
    return re.compile(company), re.compile(legal), re.compile(phrase_pattern((name, *PHRASES["ceo"])))


def page_text(text):
    """Keep the header separate so it can never become a citation."""
    lines = text.splitlines()
    if not lines or not HEADER.match(lines[0]):
        return {}, text
    header = {}
    for i, line in enumerate(lines):
        if not line.strip():
            return header, "\n".join(lines[i + 1:])
        name, _, value = line.partition(":")
        header[name] = value.strip()
    return header, ""


def sentences(text):
    for line in text.splitlines():
        line = " ".join(line.split())
        start = 0
        for end in BREAK.finditer(line):
            if end[1] == "." and SUFFIX_END.search(line, start, end.start() + 1):
                continue
            yield line[start:end.end()].strip()
            start = end.end()
        if start < len(line):
            yield line[start:].strip()


def values(domain, excerpt):
    """Return only unambiguous normalized values of one company in one excerpt."""
    if len(excerpt) > 500 or list(sentences(excerpt)) != [excerpt] or NEGATION.search(excerpt):
        return {}
    company, legal, remove_from_names = subject_patterns(domain)
    if not company.search(excerpt):
        return {}
    amounts = list(AMOUNT.finditer(excerpt))
    numeric_text = AMOUNT.sub(" ", excerpt)
    numbers = NUMBER.findall(numeric_text)
    supported = {}
    for field, indicator in STATEMENT.items():
        if not indicator.search(excerpt):
            continue
        if field == "legal_name":
            found = legal.findall(excerpt, overlapped=True)
        elif field == "hq_city":
            found = []
            for m in indicator.finditer(excerpt):
                if excerpt[m.end():m.end()+1] == " " and (city := CITY.match(excerpt, m.end() + 1)):
                    found.append(city[0])
        elif field == "ceo":
            separated = remove_from_names.sub("|", excerpt)
            found = [name for name in NAME_RUN.findall(separated) if 2 <= len(name.split()) <= 3]
        elif field == "founded_year":
            digits = [n.replace(",", "") for n in numbers]
            found = [int(n) for n in digits if len(n) == 4 and n.isdigit() and 1800 <= int(n) <= 2099]
        elif field == "headcount_range":
            integers = [int(n.replace(",", "")) for n in numbers if "." not in n]
            found = [band(n) for n in integers if n > 0]
        else:
            found = []
            for m in amounts:
                value = dollars(m)
                if value == value.to_integral_value():
                    found.append(int(value))
        if len(set(found)) == 1:
            supported[field] = found[0]
    return supported


def empty_fields():
    return {field: {"value": None, "status": "unknown", "citations": []} for field in PHRASES}
