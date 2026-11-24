"""Appendix A grammar. All offsets and quotations refer to provider text."""
from decimal import Decimal
from functools import lru_cache
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
LEFT, RIGHT = r"(?<![\p{L}\p{N}])", r"(?![\p{L}\p{N}])"
CAP = r"\p{Lu}\p{Ll}+"
UPPER = r"\p{Lu}{2,}"
SUFFIXES = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc",
            "PLC", "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj",
            "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.")
SUFFIX = "(?:" + "|".join(map(re.escape, SUFFIXES)) + ")" + RIGHT


def words(pattern):
    return LEFT + "(?i:" + pattern + ")" + RIGHT


STATEMENTS = {k: re.compile(words(v)) for k, v in PHRASES.items()}
NEGATED = re.compile(words("in talks to|plans to|planning to|wants to|expects to|hopes to|aims to|seeking|could|would|might|reportedly|rumoured|former|formerly|will become|not"))
PROTECTED = re.compile(LEFT + "(?:" + "|".join(re.escape(s) for s in SUFFIXES if s.endswith(".")) + ")$")
END = re.compile(r'[.!?]["”’)]*(?=\s)')
PLACE = re.compile(words(PHRASES["hq_city"]) + " (" + CAP + "(?:[ -]" + CAP + ")*" + RIGHT + ")")
NAMES = re.compile(LEFT + CAP + RIGHT + "(?: " + CAP + RIGHT + ")*")
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
BEFORE_NUMBER, AFTER_NUMBER = r"(?<![0-9][.,])", r"(?![.,][0-9])"
COUNT = re.compile(LEFT + BEFORE_NUMBER + NUMBER + AFTER_NUMBER + RIGHT)
CURRENCY = re.compile(LEFT + BEFORE_NUMBER + r"(?:(?:US\$|\$|USD) ?(?P<n>" + NUMBER +
                      r")(?P<scale>mn|bn|k|m| thousand| million| billion)?|(?P<n>" + NUMBER +
                      r")(?P<scale> thousand| million| billion)? (?:US )?dollars)" + AFTER_NUMBER + RIGHT, re.I)
SCALES = {"k": 1000, "thousand": 1000, "m": 10**6, "mn": 10**6, "million": 10**6,
          "bn": 10**9, "billion": 10**9, "": 1}
BOUNDS = [(10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
          (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000")]


@lru_cache(maxsize=512)
def patterns(domain):
    company = words(re.escape(domain) + "|" + re.escape(domain.split(".")[0].replace("-", " ")))
    legal = company + "(?: (?:" + CAP + "|" + UPPER + "))*?,? " + SUFFIX
    return re.compile(company), re.compile(legal)


def prose(text):
    if re.match(r"^[A-Z][A-Za-z]*(?:-[A-Z][A-Za-z]*)*: ", text):
        separator = re.search(r"\r?\n[ \t]*\r?\n", text)
        return text[separator.end():] if separator else ""
    return text


def sentences(text):
    for line in text.splitlines():
        line = " ".join(line.split())
        start = 0
        for match in END.finditer(line):
            if match[0][0] == "." and PROTECTED.search(line, start, match.start() + 1):
                continue
            yield line[start:match.end()].strip()
            start = match.end()
        if tail := line[start:].strip():
            yield tail


def values(domain, sentence):
    company, legal = patterns(domain)
    if not sentence or len(sentence) > 500 or not company.search(sentence) or NEGATED.search(sentence):
        return {}
    currency = list(CURRENCY.finditer(sentence))
    numeric_text = CURRENCY.sub(" ", sentence)
    numbers = [token.replace(",", "") for token in COUNT.findall(numeric_text)]
    output = {}
    for field, pattern in STATEMENTS.items():
        if not pattern.search(sentence):
            continue
        if field == "legal_name":
            matches = legal.findall(sentence)
        elif field == "hq_city":
            matches = PLACE.findall(sentence)
        elif field == "ceo":
            masked = company.sub("|", pattern.sub("|", sentence))
            matches = [name for name in NAMES.findall(masked) if 2 <= len(name.split()) <= 3]
        elif field == "founded_year":
            matches = [int(n) for n in numbers if len(n) == 4 and n.isdigit() and 1800 <= int(n) <= 2099]
        elif field == "headcount_range":
            counts = [int(n) for n in numbers if "." not in n]
            matches = [next((label for maximum, label in BOUNDS if count <= maximum), "10001+")
                       for count in counts if count > 0]
        else:
            matches = []
            for amount in currency:
                number = Decimal(amount["n"].replace(",", ""))
                scale = SCALES[(amount["scale"] or "").strip().lower()]
                # Scaling by a power of ten is exact for arbitrarily long digit sequences.
                digits = number.as_tuple()
                scaled = Decimal((digits.sign, digits.digits, digits.exponent + len(str(scale)) - 1))
                if scaled == scaled.to_integral_value():
                    matches.append(int(scaled))
        if len(set(matches)) == 1:
            output[field] = matches[0]
    return output


def empty_fields():
    return {k: {"value": None, "status": "unknown", "citations": []} for k in PHRASES}


class Evidence:
    def __init__(self, domain):
        self.domain = domain
        self.pages = []
        self.full_text = {}
        self.candidates = {field: [] for field in PHRASES}

    def claim_is_prose(self, url, excerpt):
        source = self.full_text.get(url)
        if source:
            body = prose(source)
            normalized = " ".join(excerpt.split())
            if normalized in " ".join(body.split()):
                return True
            header = source[:len(source) - len(body)]
            if normalized in " ".join(header.split()):
                return False
        # Research can serve a different revision from a later extract. Its
        # own excerpt is evidence unless it quotes an identifiable page header.
        return prose(excerpt) == excerpt

    def add(self, provider, url, text, title="", date="", claim=None):
        if not url or not text:
            return
        self.pages.append(dict(provider=provider, url=url, text=text, title=title, date=date, claim=claim))
        host = (urlsplit(url).hostname or "").lower()
        own = host == self.domain or host.endswith("." + self.domain)
        published = re.search(r"(?m)^Published: (\d{4}-\d\d-\d\d)", text)
        body = text if claim else prose(text)
        excerpts = sentences(body)
        if claim:
            if not self.claim_is_prose(url, text):
                return
            parts = tuple(excerpts)
            if len(parts) != 1:
                return
            excerpts = parts
        for sentence in excerpts:
            for field, value in values(self.domain, sentence).items():
                if claim and (field != claim[0] or value != claim[1]):
                    continue
                citation = dict(url=url, excerpt=sentence, provider=provider)
                rank = (published[1] if published else (date or "")[:10], own,
                        not sentence.startswith(("#", "[", "!", "<")), -len(sentence))
                self.candidates[field].append((rank, value, citation))

    def fields(self):
        result = empty_fields()
        for field, options in self.candidates.items():
            if options:
                _, value, citation = max(options, key=lambda option: option[0])
                result[field] = dict(value=value, citations=[citation], status="known")
        return result
