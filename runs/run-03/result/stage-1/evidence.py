"""Company fact extraction following Appendix A of the service contract."""
from fractions import Fraction
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
FIELDS = tuple(PHRASES)
SUFFIXES = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH",
            "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.",
            "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.")
RANGES = ((10,"1-10"), (50,"11-50"), (200,"51-200"), (500,"201-500"), (1000,"501-1000"),
          (5000,"1001-5000"), (10000,"5001-10000"))
LEFT, RIGHT = r"(?<![\p{L}\p{N}])", r"(?![\p{L}\p{N}])"
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT
CAP_RUN = re.compile(rf"{CAP}(?: {CAP})*")
DIGITS = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NUMBER = re.compile(LEFT + r"(?<![0-9][,.])" + DIGITS + r"(?![,.][0-9])" + RIGHT)
AMOUNT = re.compile(LEFT + r"(?<![0-9][,.])" +
    rf"(?:(?:US\$|USD|\$) ?(?P<n>{DIGITS})(?P<s>mn|bn|k|m| thousand| million| billion)?"
    rf"|(?P<n>{DIGITS})(?P<s> thousand| million| billion)? (?:US )?dollars)" +
    r"(?![,.][0-9])" + RIGHT, re.I)
SCALES = {"":1, "k":1000, "thousand":1000, "m":10**6, "mn":10**6, "million":10**6,
          "bn":10**9, "billion":10**9}


def alternatives(values):
    return "(?:" + "|".join(map(re.escape, values)) + ")"


def word_phrase(values):
    return LEFT + "(?i:" + alternatives(values) + ")" + RIGHT


STATEMENTS = {field: re.compile(word_phrase(phrases)) for field, phrases in PHRASES.items()}
NEGATION = re.compile(word_phrase(("in talks to", "plans to", "planning to", "wants to", "expects to",
    "hopes to", "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured",
    "former", "formerly", "will become", "not")))
SUFFIX = alternatives(SUFFIXES) + RIGHT
SUFFIX_END = re.compile(LEFT + alternatives([s for s in SUFFIXES if s.endswith(".")]) + "$")
CITY = re.compile(word_phrase(PHRASES["hq_city"]) + rf" ({CAP}(?:[ -]{CAP})*)")
BOUNDARY = re.compile(r"""([.!?])["”’)]*(?=\s)""")
HEADER = re.compile(r"^[A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)*: ")


def sentences(text):
    lines = text.splitlines()
    if lines and HEADER.match(lines[0]):
        cut = next((i for i, line in enumerate(lines) if not line.strip()), len(lines))
        lines = lines[cut + 1:]
    for line in lines:
        line = " ".join(line.split())
        start = 0
        for match in BOUNDARY.finditer(line):
            if match[1] == "." and SUFFIX_END.search(line, 0, match.start() + 1):
                continue
            yield line[start:match.end()].strip()
            start = match.end()
        if tail := line[start:].strip():
            yield tail


@lru_cache(maxsize=1024)
def company_patterns(domain):
    name = domain.split(".")[0].replace("-", " ")
    company = re.compile(word_phrase((domain, name)))
    legal = re.compile(company.pattern + rf"(?: (?:{CAP}|{UPPER}))*?,? {SUFFIX}")
    separators = re.compile(word_phrase((name, *PHRASES["ceo"])))
    return company, legal, separators


def values(domain, sentence):
    company, legal, separators = company_patterns(domain)
    if len(sentence) > 500 or not company.search(sentence) or NEGATION.search(sentence):
        return {}
    found = {}
    for field, phrase in STATEMENTS.items():
        if not phrase.search(sentence):
            continue
        candidates = set()
        if field == "legal_name":
            candidates.update(m[0] for m in legal.finditer(sentence, overlapped=True))
        elif field == "hq_city":
            candidates.update(CITY.findall(sentence))
        elif field == "ceo":
            candidates.update(m[0] for m in CAP_RUN.finditer(separators.sub("|", sentence))
                              if 2 <= len(m[0].split()) <= 3)
        elif field == "funding_total":
            for match in AMOUNT.finditer(sentence):
                amount = Fraction(match["n"].replace(",", "")) * SCALES[(match["s"] or "").strip().lower()]
                if amount.denominator == 1:
                    candidates.add(amount.numerator)
        else:
            without_amounts = AMOUNT.sub("|", sentence)
            for match in NUMBER.finditer(without_amounts):
                raw = match[0]
                if "." in raw:
                    continue
                number = int(raw.replace(",", ""))
                if field == "founded_year":
                    if len(raw) == 4 and 1800 <= number <= 2099:
                        candidates.add(number)
                elif number >= 1:
                    candidates.add(next((label for maximum, label in RANGES if number <= maximum), "10001+"))
        if len(candidates) == 1:
            found[field] = candidates.pop()
    return found


def empty_fields():
    return {field: {"value": None, "status": "unknown", "citations": []} for field in FIELDS}
