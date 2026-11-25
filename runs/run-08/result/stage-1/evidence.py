"""Recognition of a single provider-served sentence under Appendix A."""
import re
from decimal import Decimal, localcontext
from functools import lru_cache
from urllib.parse import urlsplit

import regex

PHRASES = {
    "legal_name": ("legal name", "registered name", "registered as", "registered company", "legal entity", "name of record"),
    "hq_city": ("headquartered in", "headquarters in", "head office in", "based in", "registered office in", "registered seat in"),
    "ceo": ("chief executive officer", "chief executive", "CEO"),
    "founded_year": ("founded", "founding", "established", "incorporated"),
    "headcount_range": ("employs", "employees", "staff", "people", "headcount", "workforce"),
    "funding_total": ("raised", "funding", "invested", "investment"),
}
SUFFIXES = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.")
LEFT = r"(?<![\p{L}\p{N}])"
RIGHT = r"(?![\p{L}\p{N}])"
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT


def alternatives(words):
    return "(?:" + "|".join(regex.escape(w) for w in sorted(words, key=len, reverse=True)) + ")"


def words(items):
    return LEFT + "(?i:" + alternatives(items) + ")" + RIGHT


TESTS = {f: regex.compile(words(ps)) for f, ps in PHRASES.items()}
NEGATIVE = regex.compile(words(("in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to", "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured", "former", "formerly", "will become", "not")))
SUFFIX_END = regex.compile(LEFT + alternatives(s for s in SUFFIXES if s.endswith(".")) + "$")
BREAK = re.compile(r"""([.!?])["”’)]*(?=\s)""")
CITY = regex.compile(TESTS["hq_city"].pattern + " (" + CAP + "(?:[ -]" + CAP + ")*)")
NAME_RUN = regex.compile(CAP + "(?: " + CAP + ")*")
DIGITS = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NSTART = r"(?<![0-9][.,]+)"
NEND = r"(?![.,]+[0-9])"
NUM = regex.compile(LEFT + NSTART + DIGITS + NEND + RIGHT)
AMOUNT = regex.compile(LEFT + r"(?:(?:US\$|USD|\$) ?(?P<num>" + DIGITS + ")" + NEND +
                       r"(?P<scale>mn|bn|k|m| thousand| million| billion)?|" + NSTART +
                       r"(?P<num>" + DIGITS + r")(?P<scale> thousand| million| billion)? (?:US )?dollars)" + RIGHT, regex.I)
SCALE = {"": 1, "k": 1000, "thousand": 1000, "m": 10**6, "mn": 10**6, "million": 10**6, "bn": 10**9, "billion": 10**9}
BINS = ((10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"), (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000"))
HEADER = regex.compile(r"^\p{Lu}\p{Ll}+(?:-\p{Lu}\p{Ll}+)*:[^\n]*")
BLANK = re.compile(r"\n[ \t]*\n")


def prose(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if HEADER.match(text):
        end = BLANK.search(text)
        return text[end.end():] if end else ""
    return text


def sentences(text):
    for raw in text.splitlines():
        line = " ".join(raw.split())
        start = 0
        for match in BREAK.finditer(line):
            if match[1] == "." and SUFFIX_END.search(line[max(start, match.start()-10):match.start()+1]):
                continue
            yield line[start:match.end()].strip()
            start = match.end()
        if tail := line[start:].strip():
            yield tail


def excerpts(text, claim):
    if claim is None:
        yield from sentences(prose(text))
        return
    # A research citation is one supplied quotation. Its full text must
    # qualify; selecting a sentence from inside it would change the claim.
    quote = " ".join(text.split())
    if 0 < len(quote) <= 500 and list(sentences(quote)) == [quote]:
        yield quote


@lru_cache(maxsize=512)
def company_patterns(domain):
    name = domain.split(".")[0].replace("-", " ")
    company = words((domain, name))
    # A suffix may itself be a prefix ending in punctuation, e.g. S.A. in S.A.S.
    legal = regex.compile(company + "(?: (?:" + CAP + "|" + UPPER + "))*?,? (?:" +
                          "|".join(regex.escape(s) + RIGHT for s in sorted(SUFFIXES, key=len)) + ")")
    return regex.compile(company), legal


def headcount(n):
    return next((label for upper, label in BINS if n <= upper), "10001+")


def values(domain, sentence):
    company, legal = company_patterns(domain)
    if not 0 < len(sentence) <= 500 or not company.search(sentence) or NEGATIVE.search(sentence):
        return {}
    amounts = list(AMOUNT.finditer(sentence))
    plain = AMOUNT.sub("|", sentence)
    nums = [m[0] for m in NUM.finditer(plain)]
    supported = {}
    for field, phrase in TESTS.items():
        if not phrase.search(sentence):
            continue
        if field == "legal_name":
            candidates = legal.findall(sentence, overlapped=True)
        elif field == "hq_city":
            candidates = CITY.findall(sentence)
        elif field == "ceo":
            clean = phrase.sub("|", company.sub("|", sentence))
            candidates = [s for s in NAME_RUN.findall(clean) if 2 <= len(s.split()) <= 3]
        elif field == "founded_year":
            candidates = [int(n) for n in nums if len(n) == 4 and n.isdigit() and 1800 <= int(n) <= 2099]
        elif field == "headcount_range":
            integers = [int(s.replace(",", "")) for s in nums if "." not in s]
            candidates = [headcount(n) for n in integers if n > 0]
        else:
            candidates = []
            with localcontext() as ctx:
                ctx.prec = 520
                for m in amounts:
                    amount = Decimal(m["num"].replace(",", "")) * SCALE[(m["scale"] or "").strip().lower()]
                    if amount == amount.to_integral_value():
                        candidates.append(int(amount))
        if len(set(candidates)) == 1:
            supported[field] = candidates[0]
    return supported


def unknown_fields():
    return {f: {"status": "unknown", "value": None, "citations": []} for f in PHRASES}


def specificity(domain, field, value, sentence):
    """Prefer a direct company fact among excerpts that pass Appendix A."""
    visible = re.sub(r"https?://[^\s)]+", "", sentence).replace("*", "")
    if field in ("funding_total", "founded_year", "headcount_range"):
        if "?" in visible or values(domain, visible).get(field) != value:
            return 0
    if field == "headcount_range":
        if re.search(r"\b(more|fewer) employees than\b", visible, re.I):
            return 0
        direct = re.search(r"\d[\d,]*(?:\+| or so)? (?:full[- ]time |part[- ]time |global |total |permanent |worldwide )*(?:employees|staff|people|workers|team members)\b|"
                           r"\b(?:employs|headcount|workforce)(?: of| is| was|:| approximately| about| roughly| over| nearly| around| more than| stands at)* [\d,]+", visible, re.I)
        return 2 if direct else 0
    if field == "funding_total":
        if re.search(r"\b(charity|campaign|donated|debt financing|secondary offering|valuation|IPO|revenue|for its fund)\b", visible, re.I):
            return 0
        return 2 if re.search(r"\b(total|cumulative|altogether|to date|in equity|across .* rounds)\b", visible, re.I) else 1
    if field == "founded_year":
        company = company_patterns(domain)[0].pattern
        founding = r"(?:was |is |originally |first |officially |co-)*(?:founded|established)"
        if regex.search(company + r"\s+" + founding + r" (?:in )?" + str(value), visible, regex.I):
            return 3
        if re.search(r"\b(founded|established|founding)\b", visible, re.I):
            return 2 if re.search(r"\b(?:founded|established)(?: in|:)? " + str(value), visible, re.I) else 1
        return 1
    if field == "ceo":
        name = re.escape(value)
        title = r"(?:co-)?(?:CEO|chief executive(?: officer)?)"
        direct = (name + r"(?:,? (?:is|as|to|serves|the|new|current|president|and|of|company.s|\S+.s)){0,6}[,: -]+" + title
                  + "|" + title + r"[,: -]+(?:is |was |named )?" + name)
        return 2 if re.search(direct, visible, re.I) else 1
    return 2


class Evidence:
    def __init__(self, domain):
        self.domain = domain
        self.fields = unknown_fields()
        self.ranks = {}

    def add(self, provider, url, text, *, claim=None, date="", snippet=False):
        if not isinstance(text, str) or not url:
            return
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return
        own = host == self.domain or host.endswith("." + self.domain)
        body = prose(text) if claim is None else text
        if match := re.search(r"(?m)^Published(?:-At)?: (\d{4}-\d\d-\d\d)", text[:text.find(body) if body else 0]):
            date = match[1]
        links_company = self.domain in body.lower()
        final_line = " ".join(body.splitlines()[-1].split()) if body.splitlines() else ""
        for sentence in excerpts(text, claim):
            # A search result can end halfway through a city, amount or denial.
            # Extract the full page before using an unfinished trailing sentence.
            if snippet and final_line.endswith(sentence) and not re.search(r'[.!?]["”’)]*$', sentence):
                continue
            if len(sentence) > 500:
                continue
            for field, value in values(self.domain, sentence).items():
                if claim is not None and (field != claim[0] or type(value) is not type(claim[1]) or value != claim[1]):
                    continue
                total = field == "funding_total" and bool(re.search(r"\b(total|to date|in all|altogether|cumulative)\b", sentence, re.I))
                rank = (specificity(self.domain, field, value, sentence), total, (date or "")[:10], own, links_company, -len(sentence))
                if field not in self.ranks or rank > self.ranks[field]:
                    self.ranks[field] = rank
                    self.fields[field] = {"status": "known", "value": value, "citations": [
                        {"provider": provider, "url": url, "excerpt": sentence}
                    ]}
