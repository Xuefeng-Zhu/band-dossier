"""Apply the sentence, phrase, value and ambiguity rules of Appendix A."""
from decimal import Decimal, localcontext

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
TITLES = ("cfo", "coo", "cto")
ALL_FIELDS = (*FIELDS, "executives")
PHRASES.update({
    "cfo": ("chief financial officer", "CFO"),
    "coo": ("chief operating officer", "COO"),
    "cto": ("chief technology officer", "CTO"),
})
SUFFIXES = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.")
LEFT = r"(?<![\p{L}\p{Nd}])"
RIGHT = r"(?![\p{L}\p{Nd}])"
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT


def alternatives(words):
    return "(?:" + "|".join(re.escape(w) for w in words) + ")"


def phrases(words):
    return re.compile(LEFT + "(?i:" + alternatives(words) + ")" + RIGHT)


STATEMENT = {key: phrases(words) for key, words in PHRASES.items()}
NEGATION = phrases(("in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to", "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured", "former", "formerly", "will become", "not"))
PERIOD_SUFFIX = re.compile(LEFT + alternatives(s for s in SUFFIXES if s.endswith(".")) + "$")
SENTENCE_END = re.compile(r'([.!?])["”’)]*(?=\s)')
HEADER = re.compile(r"^[A-Z][a-z]*(?:-[A-Z][a-z]*)*:")
CITY = re.compile(STATEMENT["hq_city"].pattern + " (" + CAP + "(?:[ -]" + CAP + ")*)")
PERSON_RUN = re.compile(CAP + "(?: " + CAP + ")*")
# Do not recover a smaller number from the middle of invalid grouping or a decimal.
NUM = r"(?<![0-9][.,]+)(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?(?![.,]+[0-9])"
NUMBER = re.compile(LEFT + NUM + RIGHT)
SCALE_LONG = "(?:thousand|million|billion)"
AMOUNT = re.compile(
    LEFT + r"(?:(?:US\$|USD|\$) ?(?P<prefix>" + NUM + r")(?P<scale>mn|bn|m|k| " + SCALE_LONG + r")?"
    + r"|(?P<postfix>" + NUM + r")(?P<word> " + SCALE_LONG + r")? (?:US )?dollars)" + RIGHT, re.I,
)
SCALES = {"": 1, "k": 1000, "thousand": 1000, "m": 10**6, "mn": 10**6, "million": 10**6, "bn": 10**9, "billion": 10**9}


def unknown_fields():
    return {f: {"status": "unknown", "value": None, "citations": [], "candidates": [], "true_from": None, "learned_at": None} for f in ALL_FIELDS}


def sentences(text):
    lines = text.splitlines()
    if lines and HEADER.match(lines[0]):
        first_blank = next((i for i, line in enumerate(lines) if not line.strip()), len(lines))
        lines = lines[first_blank + 1:]
    for line in lines:
        start = 0
        for end in SENTENCE_END.finditer(line):
            if end[1] == "." and PERIOD_SUFFIX.search(line, endpos=end.start() + 1):
                continue
            sentence = " ".join(line[start:end.end()].split())
            if sentence:
                yield sentence
            start = end.end()
        last = " ".join(line[start:].split())
        if last:
            yield last


def headcount(number):
    lower = 1
    for upper in (10, 50, 200, 500, 1000, 5000, 10000):
        if number <= upper:
            return f"{lower}-{upper}"
        lower = upper + 1
    return "10001+"


def amounts(sentence):
    values = set()
    for match in AMOUNT.finditer(sentence):
        literal = (match["prefix"] or match["postfix"]).replace(",", "")
        scale = (match["scale"] or match["word"] or "").strip().lower()
        with localcontext() as ctx:
            ctx.prec = len(literal) + 12
            amount = Decimal(literal) * SCALES[scale]
        if amount == amount.to_integral_value():
            values.add(int(amount))
    return values


class Support:
    def __init__(self, domain):
        name = domain.split(".")[0].replace("-", " ")
        self.subject = phrases((domain, name))
        self.company_name = phrases((name,))
        self.legal = re.compile(self.subject.pattern + "(?: (?:" + CAP + "|" + UPPER + "))*?,? " + alternatives(SUFFIXES) + RIGHT)

    def values(self, field, sentence):
        if field == "legal_name":
            return {match[0] for match in self.legal.finditer(sentence, overlapped=True)}
        if field == "hq_city":
            return {match[1] for match in CITY.finditer(sentence)}
        if field == "ceo" or field in TITLES:
            rest = STATEMENT[field].sub("|", self.company_name.sub("|", sentence))
            return {run[0] for run in PERSON_RUN.finditer(rest) if 2 <= len(run[0].split()) <= 3}
        if field == "funding_total":
            return amounts(sentence)
        bare = AMOUNT.sub("|", sentence)
        integers = [m[0] for m in NUMBER.finditer(bare) if "." not in m[0]]
        if field == "founded_year":
            return {int(n) for n in integers if len(n) == 4 and n.isdigit() and 1800 <= int(n) <= 2099}
        return {headcount(n) for raw in integers if (n := int(raw.replace(",", ""))) > 0}

    def parse(self, sentence):
        if not 1 <= len(sentence) <= 500 or not self.subject.search(sentence) or NEGATION.search(sentence):
            return {}
        supported = {}
        for field, statement in STATEMENT.items():
            if statement.search(sentence):
                values = self.values(field, sentence)
                if len(values) == 1:
                    supported[field] = values.pop()
        return supported
