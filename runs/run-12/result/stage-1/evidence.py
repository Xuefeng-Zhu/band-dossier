"""Parse the Stage 1 evidence grammar directly on the text returned by each provider."""
from decimal import Decimal, localcontext
from functools import lru_cache
import regex as rx

PHRASES = {
    "legal_name": ("legal name", "registered name", "registered as", "registered company", "legal entity", "name of record"),
    "hq_city": ("headquartered in", "headquarters in", "head office in", "based in", "registered office in", "registered seat in"),
    "ceo": ("chief executive officer", "chief executive", "CEO"),
    "founded_year": ("founded", "founding", "established", "incorporated"),
    "headcount_range": ("employs", "employees", "staff", "people", "headcount", "workforce"),
    "funding_total": ("raised", "funding", "invested", "investment"),
}
SUFFIXES = "Inc.|Corp.|LLC|LLP|L.P.|Ltd|Limited|Pty Ltd|plc|PLC|GmbH|AG|KG|SE|AS|A/S|ASA|AB|Oy|Oyj|B.V.|N.V.|S.A.|S.A.S.|S.L.|S.r.l.|S.p.A.|s.r.o.|a.s.|K.K.".split("|")
LEFT, RIGHT = r"(?<![\p{L}\p{N}])", r"(?![\p{L}\p{N}])"
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT


def words(choices):
    return LEFT + "(?i:" + "|".join(map(rx.escape, sorted(choices, key=len, reverse=True))) + ")" + RIGHT


STATEMENTS = {f: rx.compile(words(v)) for f, v in PHRASES.items()}
NEGATIVE = rx.compile(words("in talks to|plans to|planning to|wants to|expects to|hopes to|aims to|seeking|could|would|might|reportedly|rumoured|former|formerly|will become|not".split("|")))
SUFFIX = "(?:" + "|".join(map(rx.escape, sorted(SUFFIXES, key=len))) + ")" + RIGHT
SUFFIX_END = rx.compile(LEFT + "(?:" + "|".join(map(rx.escape, (s for s in SUFFIXES if s.endswith(".")))) + ")$")
ENDS = rx.compile(r"""[.!?]["”’)‌]*(?=\s)""".replace("‌", ""))
PLACE = rx.compile(words(PHRASES["hq_city"]) + " (" + CAP + "(?:[ -]" + CAP + ")*)")
PERSON = rx.compile(CAP + "(?: " + CAP + ")+")
DIGITS = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
# The second guards prevent matching just a valid prefix/suffix inside a malformed group.
NUM_LEFT = LEFT + r"(?<![0-9][,.])"
NUM_RIGHT = RIGHT + r"(?![,.][0-9])"
NUMBER = rx.compile(NUM_LEFT + DIGITS + NUM_RIGHT)
AMOUNT = rx.compile(NUM_LEFT + r"(?:(?:US\$|USD|\$) ?(?P<num>" + DIGITS +
                    r")(?P<scale>mn|bn|k|m| thousand| million| billion)?|(?P<num>" + DIGITS +
                    r")(?P<scale> thousand| million| billion)? (?:US )?dollars)" + NUM_RIGHT, rx.I)
SCALES = {"k": 1000, "thousand": 1000, "m": 10**6, "mn": 10**6, "million": 10**6, "bn": 10**9, "billion": 10**9}
RANGES = [(10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"), (1000, "501-1000"),
          (5000, "1001-5000"), (10000, "5001-10000")]


def unknown_fields():
    return {f: {"status": "unknown", "value": None, "citations": []} for f in PHRASES}


@lru_cache(maxsize=512)
def patterns(domain):
    company = domain.split(".")[0].replace("-", " ")
    subject = words((domain, company))
    legal = subject + "(?: (?:" + CAP + "|" + UPPER + "))*?,? " + SUFFIX
    return rx.compile(subject), rx.compile(legal), rx.compile(words((company,) + PHRASES["ceo"]))


def prose(text):
    lines = text.splitlines()
    if lines and rx.fullmatch(r"\p{Lu}\p{Ll}+(?:-\p{Lu}\p{Ll}+)*:.*", lines[0]):
        for i, line in enumerate(lines):
            if not line.strip():
                return lines[i+1:], lines[:i]
        return [], lines
    return lines, []


def sentences(lines):
    for line in lines:
        start = 0
        for match in ENDS.finditer(line):
            if line[match.start()] == "." and SUFFIX_END.search(line[max(0, match.start()-10):match.start()+1]):
                continue
            yield line[start:match.end()].strip()
            start = match.end()
        yield line[start:].strip()


def bucket(n):
    return next((name for bound, name in RANGES if n <= bound), "10001+")


def values(field, sentence, domain):
    _, legal, remove = patterns(domain)
    if field == "legal_name":
        return legal.findall(sentence)
    if field == "hq_city":
        return PLACE.findall(sentence)
    if field == "ceo":
        return [name for name in PERSON.findall(remove.sub("|", sentence)) if 2 <= len(name.split()) <= 3]
    if field == "funding_total":
        vals = []
        for m in AMOUNT.finditer(sentence):
            raw = m["num"].replace(",", "")
            with localcontext() as ctx:
                ctx.prec = len(raw) + 12
                n = Decimal(raw) * SCALES.get((m["scale"] or "").lower().strip(), 1)
            if n == n.to_integral_value():
                vals.append(int(n))
        return vals
    # Keep punctuation between distinct tokens when masking an amount.
    nums = NUMBER.findall(AMOUNT.sub("|", sentence))
    if field == "founded_year":
        return [int(n) for n in nums if n.isdigit() and len(n) == 4 and 1800 <= int(n) <= 2099]
    return [bucket(int(n.replace(",", ""))) for n in nums if "." not in n and int(n.replace(",", "")) > 0]


def supported(domain, lines):
    subject = patterns(domain)[0]
    for raw in sentences(lines):
        sentence = " ".join(raw.split())
        if not sentence or not subject.search(sentence) or NEGATIVE.search(sentence):
            continue
        # Trim markup enclosing the entire sentence only; bytes inside an excerpt stay verbatim.
        sentence = sentence.strip("*_# \t")
        if len(sentence) > 500:
            continue
        for field, phrase in STATEMENTS.items():
            if phrase.search(sentence):
                found = set(values(field, sentence, domain))
                if len(found) == 1:
                    yield field, found.pop(), sentence
