"""Apply the Stage 1 sentence and value rules directly to provider text."""
from datetime import datetime
from decimal import Decimal, localcontext
from urllib.parse import urlsplit
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
SUFFIXES = "Inc.|Corp.|LLC|LLP|L.P.|Ltd|Limited|Pty Ltd|plc|PLC|GmbH|AG|KG|SE|AS|A/S|ASA|AB|Oy|Oyj|B.V.|N.V.|S.A.|S.A.S.|S.L.|S.r.l.|S.p.A.|s.r.o.|a.s.|K.K.".split("|")
NEGATIONS = "in talks to|plans to|planning to|wants to|expects to|hopes to|aims to|seeking|could|would|might|reportedly|rumoured|former|formerly|will become|not".split("|")
LEFT, RIGHT = r"(?<![\p{L}\p{Nd}])", r"(?![\p{L}\p{Nd}])"

def either(options):
    return "(?:" + "|".join(re.escape(s) for s in options) + ")"

def word(options):
    return LEFT + "(?i:" + either(options) + ")" + RIGHT

STATEMENT = {k: re.compile(word(v)) for k, v in PHRASES.items()}
NEGATIVE = re.compile(word(NEGATIONS))
SUFFIX = either(SUFFIXES)
SUFFIX_END = re.compile(LEFT + SUFFIX + "$")
SENTENCE_END = re.compile(r'([.!?])["”’)]*(?=\s)')
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT
CITY = re.compile(word(PHRASES["hq_city"]) + " (" + CAP + "(?:[ -]" + CAP + ")*)")
PERSON = re.compile(CAP + "(?: " + CAP + ")*")
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NL = LEFT + r"(?<![0-9][,.])"
NR = RIGHT + r"(?![,.][0-9])"
NUM = re.compile(NL + NUMBER + NR)
AMOUNT = re.compile(NL + r"(?:(?:US\$|\$|USD) ?(?P<n1>" + NUMBER + r")(?P<s1>mn|bn|k|m| thousand| million| billion)?|(?P<n2>" + NUMBER + r")(?P<s2> thousand| million| billion)? (?:US )?dollars)" + NR, re.I)
SCALE = {"":1, "k":1000, "thousand":1000, "m":10**6, "mn":10**6, "million":10**6, "bn":10**9, "billion":10**9}
RANGES = [(10,"1-10"), (50,"11-50"), (200,"51-200"), (500,"201-500"), (1000,"501-1000"), (5000,"1001-5000"), (10000,"5001-10000")]
HEADER = re.compile(r"^[A-Z][a-z]+(?:-[A-Z][a-z]+)*:[ \t]")

KINDS = {"own": 2, "filing": 2, "news": 1, "aggregator": 0, None: 0}
PROVIDERS = ("nimble", "tavily", "kernel", "browserbase")

def time_key(value):
    parts = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]+))?([Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",value or "")
    if not parts:
        return None
    second,fraction,offset = parts.groups()
    try:
        return datetime.fromisoformat(second+offset.upper()), (fraction or "").rstrip("0")
    except ValueError:
        return None

def page_headers(text):
    lines = text.splitlines()
    headers = {}
    if lines and HEADER.match(lines[0]):
        for line in lines:
            if not line.strip():
                break
            name,sep,value = line.partition(":")
            if sep:
                headers[name] = value.strip()
    return headers

def ranked(candidates):
    # Stable sorts preserve the lower-priority comparisons while ranking
    # recency and authority in descending order.
    ordered = sorted(candidates,key=lambda c:(c["url"],PROVIDERS.index(c["provider"]),c["value"]))
    ordered.sort(key=lambda c:(bool(c["published_at"]),time_key(c["published_at"])),reverse=True)
    ordered.sort(key=lambda c:KINDS[c["kind"]],reverse=True)
    if not ordered:
        return {"value":None,"status":"unknown","citations":[],"candidates":[]}
    value = ordered[0]["value"]
    citations = []
    distinct = set()
    rows = []
    for i,c in enumerate(ordered):
        rows.append({**c,"selected":i==0})
        distinct.add(c["value"])
        if c["value"]==value:
            citations.append({k:c[k] for k in ("url","excerpt","provider")})
    return {"value":value,"status":"contested" if len(distinct)>1 else "known","citations":citations,"candidates":rows}

def unknown():
    return {field: {"value": None, "status": "unknown", "citations": [], "candidates": []} for field in FIELDS}

def sentences(text):
    lines = text.splitlines()
    if lines and HEADER.match(lines[0]):
        boundary = next((i for i, line in enumerate(lines) if not line.strip()), len(lines))
        lines = lines[boundary + 1:]
    for line in lines:
        line = " ".join(line.split())
        start = 0
        for match in SENTENCE_END.finditer(line):
            if match[1] == "." and SUFFIX_END.search(line[max(0,match.start()-12):match.start()+1]):
                continue
            yield line[start:match.end()].strip()
            start = match.end()
        if line[start:].strip():
            yield line[start:].strip()

class Evidence:
    def __init__(self, domain, at, imported=False):
        self.at = at
        self.imported = imported
        self.metadata = {}
        self.domain = domain
        self.name = word([domain, domain.split(".")[0].replace("-", " ")])
        self.subject = re.compile(self.name)
        self.legal = re.compile(self.name + "(?: (?:" + CAP + "|" + UPPER + "))*?,? " + SUFFIX + RIGHT)
        self.candidates = {f: {} for f in FIELDS}

    def values(self, sentence):
        if not self.subject.search(sentence) or NEGATIVE.search(sentence):
            return
        amounts = list(AMOUNT.finditer(sentence))
        free_text = AMOUNT.sub(" / ", sentence)
        numbers = NUM.findall(free_text)
        for field, pattern in STATEMENT.items():
            if not pattern.search(sentence):
                continue
            if field == "legal_name":
                values = self.legal.findall(sentence)
            elif field == "hq_city":
                values = CITY.findall(sentence)
            elif field == "ceo":
                separated = pattern.sub("|", self.subject.sub("|", sentence))
                values = [name for name in PERSON.findall(separated) if 2 <= len(name.split()) <= 3]
            elif field == "founded_year":
                values = [int(n) for n in numbers if len(n)==4 and n.isdigit() and 1800<=int(n)<=2099]
            elif field == "headcount_range":
                values = [next((label for cap,label in RANGES if n<=cap), "10001+")
                          for raw in numbers if "." not in raw and (n:=int(raw.replace(",",""))) > 0]
            else:
                values = []
                for m in amounts:
                    raw = (m["n1"] or m["n2"]).replace(",","")
                    with localcontext() as ctx:
                        ctx.prec = len(raw)+12
                        amount = Decimal(raw) * SCALE[(m["s1"] or m["s2"] or "").strip().lower()]
                    if amount == amount.to_integral_value():
                        values.append(int(amount))
            if values and len(set(values)) == 1:
                yield field, values[0]

    def add(self, url, text, provider, *, claim=None):
        if not isinstance(url,str) or not isinstance(text,str) or not url or not text:
            return
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return
        headers = page_headers(text)
        if headers or url not in self.metadata:
            kind = headers.get("Kind")
            if kind not in KINDS or kind is None:
                host = host.removesuffix(".").removeprefix("www.")
                kind = None if self.imported else ("own" if host==self.domain else "aggregator")
            published = headers.get("Published")
            self.metadata[url] = (kind, published if time_key(published) else None)
        if claim is None:
            excerpts = sentences(text)
        else:
            excerpt = " ".join(text.split())
            excerpts = [excerpt] if list(sentences(excerpt)) == [excerpt] else []
        for sentence in excerpts:
            if not 1 <= len(sentence) <= 500:
                continue
            # Markdown image descriptions and link destinations are metadata.
            # A URL slug hidden behind a link cannot identify the subject of the prose.
            supported = dict(self.values(sentence))
            if not self.imported and ("![" in sentence or "](" in sentence):
                visible = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", sentence)
                visible = re.sub(r"\]\([^)]*\)", "]", visible)
                visible_values = dict(self.values(visible))
                supported = {k:v for k,v in supported.items() if visible_values.get(k)==v}
            for field,value in supported.items():
                if claim is not None and (field != claim[0] or str(value) != str(claim[1])):
                    continue
                key = (url,value)
                cite = {"url":url,"value":value,"excerpt":sentence,"provider":provider,"retrieved_at":self.at}
                old = self.candidates[field].get(key)
                # Provider priority is fixed. Within a page a shorter complete
                # supporting sentence is easier to review.
                def excerpt_order(c):
                    return PROVIDERS.index(c["provider"]),len(c["excerpt"]),c["excerpt"]
                if old is None or excerpt_order(cite)<excerpt_order(old):
                    self.candidates[field][key] = cite

    def fields(self):
        result = {}
        for field,candidates in self.candidates.items():
            rows = []
            for c in candidates.values():
                kind,published = self.metadata[c["url"]]
                rows.append({**c,"kind":kind,"published_at":published})
            result[field] = ranked(rows)
        return result
