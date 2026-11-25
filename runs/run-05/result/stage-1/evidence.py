"""Sentence-level support and value normalization from Appendix A."""
from functools import lru_cache

import regex as re

PHRASES = {
    "legal_name": ("legal name","registered name","registered as","registered company","legal entity","name of record"),
    "hq_city": ("headquartered in","headquarters in","head office in","based in","registered office in","registered seat in"),
    "ceo": ("chief executive officer","chief executive","CEO"),
    "founded_year": ("founded","founding","established","incorporated"),
    "headcount_range": ("employs","employees","staff","people","headcount","workforce"),
    "funding_total": ("raised","funding","invested","investment"),
}
FIELD_NAMES = tuple(PHRASES)
NEGATION = ("in talks to","plans to","planning to","wants to","expects to","hopes to","aims to","seeking",
            "could","would","might","reportedly","rumoured","former","formerly","will become","not")
SUFFIXES = ("Inc.","Corp.","LLC","LLP","L.P.","Ltd","Limited","Pty Ltd","plc","PLC","GmbH","AG","KG","SE",
            "AS","A/S","ASA","AB","Oy","Oyj","B.V.","N.V.","S.A.","S.A.S.","S.L.","S.r.l.","S.p.A.","s.r.o.","a.s.","K.K.")
LEFT, RIGHT = r"(?<![\p{L}\d])", r"(?![\p{L}\d])"
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT

def words(items):
    return "(?:" + "|".join(re.escape(x) for x in items) + ")"

def phrases(items):
    return LEFT + "(?i:" + words(items) + ")" + RIGHT

NEGATED = re.compile(phrases(NEGATION))
FIELD_PHRASES = {key: re.compile(phrases(items)) for key, items in PHRASES.items()}
SUFFIX_END = re.compile(LEFT + words(s for s in SUFFIXES if s.endswith(".")) + "$")
PUNCT = re.compile(r'([.!?])["”’)]*(?=\s)')
HEADER = re.compile(r"^[A-Z][a-z]*(?:-[A-Z][a-z]*)*:")
CITY = re.compile(phrases(PHRASES["hq_city"]) + " (" + CAP + "(?:[ -]" + CAP + ")*)")
# A Markdown link destination may contain escaped or nested parentheses.
# Its label is visible page text. Its target and optional title are metadata.
LINK_DESTINATION = re.compile(r"""
    (?<=\]) \( \s*
    (?: < (?: \\. | [^<>\n\\]++ )* >
      | (?: \\. | [^()\s\\]++ | (?&balanced) )* )
    (?: \s+ (?: " (?: \\. | [^"\\]++ )* "
                | ' (?: \\. | [^'\\]++ )* '
                | (?&balanced) ) )?
    \s* \)
    (?(DEFINE) (?P<balanced> \( (?: \\. | [^()\\]++ | (?&balanced) )* \) ))
""", re.VERBOSE)
PERSON_RUN = re.compile(CAP + "(?: " + CAP + ")*")
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
NUM_LEFT = LEFT + r"(?<!\d[.,])"
NUM_RIGHT = RIGHT + r"(?![.,]\d)"
COUNT = re.compile(NUM_LEFT + NUMBER + NUM_RIGHT)
AMOUNT = re.compile(
    NUM_LEFT + r"(?:"
    + r"(?:US\$|USD|\$) ?(?P<num>" + NUMBER + r")(?![.,]\d)(?P<scale>mn|bn|k|m| thousand| million| billion)?"
    + r"|(?P<num>" + NUMBER + r")(?P<scale> thousand| million| billion)? (?:US )?dollars)"
    + NUM_RIGHT, re.I)
SCALES = {"":1,"k":1000,"thousand":1000,"m":1000000,"mn":1000000,"million":1000000,
          "bn":1000000000,"billion":1000000000}
BUCKETS = ((10,"1-10"),(50,"11-50"),(200,"51-200"),(500,"201-500"),(1000,"501-1000"),
           (5000,"1001-5000"),(10000,"5001-10000"))

def blank_fields():
    return {field: {"status":"unknown", "value":None, "citations":[]} for field in FIELD_NAMES}

def sentences(text):
    lines = text.splitlines()
    if lines and HEADER.match(lines[0]):
        start = next((i+1 for i,line in enumerate(lines) if not line.strip()), len(lines))
        lines = lines[start:]
    # Preserve a character-for-character map to the served text, including
    # multiline links. Hidden punctuation cannot split a visible sentence.
    source = "\n".join(" ".join(line.split()) for line in lines)
    def mask_link(match):
        return "".join("\n" if char == "\n" else "\0" for char in match[0])

    prose = LINK_DESTINATION.sub(mask_link, source)
    for line, visible in zip(source.split("\n"), prose.split("\n"), strict=True):
        start = 0
        for mark in PUNCT.finditer(visible):
            if mark[1] == "." and SUFFIX_END.search(visible, max(0,mark.start()-12),mark.start()+1):
                continue
            if unit := line[start:mark.end()].strip():
                yield unit, visible[start:mark.end()].strip()
            start = mark.end()
        if unit := line[start:].strip():
            yield unit, visible[start:].strip()

@lru_cache(maxsize=512)
def patterns(domain):
    company = domain.partition(".")[0].replace("-", " ")
    named = phrases((domain,company))
    suffix = words(sorted(SUFFIXES, key=len))
    legal = named + "(?: (?:" + CAP + "|" + UPPER + "))*?,? " + suffix + RIGHT
    return re.compile(named), re.compile(legal), re.compile(phrases((company, *PHRASES["ceo"])))

def amount_values(text):
    output = []
    for m in AMOUNT.finditer(text):
        # Decimal input and integer scaling keep all significant digits.
        raw = m["num"].replace(",", "")
        whole, _, fraction = raw.partition(".")
        scaled = int(whole + fraction) * SCALES[(m["scale"] or "").strip().lower()]
        value, remainder = divmod(scaled, 10 ** len(fraction))
        if not remainder:
            output.append(value)
    return output

def numbers(text):
    return COUNT.findall(AMOUNT.sub(" ",text))

def values(domain, excerpt):
    if not 0 < len(excerpt) <= 500:
        return {}
    named, legal, remove_from_names = patterns(domain)
    if not named.search(excerpt) or NEGATED.search(excerpt):
        return {}
    found = {}
    for key, statement in FIELD_PHRASES.items():
        if not statement.search(excerpt):
            continue
        if key == "legal_name":
            candidates = legal.findall(excerpt, overlapped=True)
        elif key == "hq_city":
            candidates = CITY.findall(excerpt)
        elif key == "ceo":
            runs = PERSON_RUN.findall(remove_from_names.sub("|",excerpt))
            candidates = [r for r in runs if 2 <= len(r.split()) <= 3]
        elif key == "founded_year":
            candidates = [int(x) for x in numbers(excerpt) if x.isdigit() and len(x)==4 and 1800 <= int(x) <= 2099]
        elif key == "headcount_range":
            counts = (int(x.replace(",","")) for x in numbers(excerpt) if "." not in x)
            candidates = [next((label for upper,label in BUCKETS if n <= upper), "10001+") for n in counts if n >= 1]
        else:
            candidates = amount_values(excerpt)
        options = set(candidates)
        if len(options) == 1:
            found[key] = options.pop()
    return found
