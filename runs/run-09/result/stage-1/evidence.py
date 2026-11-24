"""Appendix A support checks and ranking of the original provider passages."""
from datetime import datetime
from functools import lru_cache
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
SUFFIXES = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.")
LEFT, RIGHT = r"(?<![\p{L}\p{N}])", r"(?![\p{L}\p{N}])"
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT
NUM = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NUM_LEFT, NUM_RIGHT = r"(?<![0-9][.,])", r"(?![.,][0-9])"
NUMBER = re.compile(LEFT + NUM_LEFT + NUM + NUM_RIGHT + RIGHT)
LONG_SCALE = r" (?:million|billion|thousand)"
AMOUNT = re.compile(LEFT + NUM_LEFT + rf"(?:(?:US\$|\$|USD) ?(?P<n>{NUM})(?P<s>mn|bn|m|k|{LONG_SCALE})?|(?P<n>{NUM})(?P<s>{LONG_SCALE})? (?:US )?dollars)" + NUM_RIGHT + RIGHT, re.I)
SCALES = {"": 1, "m": 10**6, "mn": 10**6, "million": 10**6, "k": 1000, "thousand": 1000, "bn": 10**9, "billion": 10**9}
BUCKETS = [(10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"), (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000")]

def alternatives(words):
    return "(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + ")"

def words(*terms):
    return LEFT + "(?i:" + alternatives(terms) + ")" + RIGHT

MATCH = {f: re.compile(words(*phrases)) for f, phrases in PHRASES.items()}
NEG = re.compile(words(*"in talks to|plans to|planning to|wants to|expects to|hopes to|aims to|seeking|could|would|might|reportedly|rumoured|former|formerly|will become|not".split("|")))
SUFFIX = alternatives(SUFFIXES)
SUFFIX_END = re.compile(LEFT + SUFFIX + "$")
CITY = re.compile(words(*PHRASES["hq_city"]) + rf" ({CAP}(?:[ -]{CAP})*)")
NAMES = re.compile(rf"{CAP}(?: {CAP})+")
HEADER = re.compile(r"^[A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)*: *")
DATE = re.compile(r"\b(?:19|20)\d\d-[01]\d-[0-3]\d\b")

@lru_cache(maxsize=256)
def subject(domain):
    name = domain.split(".")[0].replace("-", " ")
    named = words(domain, name)
    legal = re.compile(named + rf"(?: (?:{CAP}|{UPPER}))*?,? {SUFFIX}" + RIGHT)
    return re.compile(named), re.compile(words(name)), legal

def unknown():
    return {field: {"value": None, "status": "unknown", "citations": []} for field in PHRASES}

def sentences(line):
    start = 0
    for stop in re.finditer(r"""([.!?])["”’)]*(?=\s)""", line):
        if stop[1] == "." and SUFFIX_END.search(line[max(0, stop.start()-12):stop.start()+1]):
            continue
        yield line[start:stop.end()].strip()
        start = stop.end()
    yield line[start:].strip()

def passages(text):
    lines = text.splitlines()
    meta = {}
    if lines and HEADER.match(lines[0]):
        for i, line in enumerate(lines):
            if not line.strip():
                lines = lines[i+1:]
                break
            key, _, val = line.partition(":")
            meta[key] = val.strip()
        else:
            lines = []
    # Keep the source spelling of inline markup. A clean label or text node
    # can also stand on its own if the rendered sentence supports the same fact.
    for line in lines:
        for raw in sentences(" ".join(line.split())):
            if not raw:
                continue
            rendered = re.sub(r"<[^<>]+>", "", raw)
            rendered = re.sub(r"!?(?:\[([^\]]*)\])\([^()]*\)", r"\1", rendered)
            rendered = rendered.replace("**", "").replace("__", "").strip("*_`")
            weak = bool(re.search(r"^\s*(?:#|[-*+>] |!?\[)|</?(?:h[1-6]|figcaption|a)\b", raw, re.I))
            fragments = re.split(r"<[^<>]+>|\]\([^()]*\)", raw)
            seen = set()
            for fragment in [*fragments, raw]:
                fragment = re.sub(r"^\s*(?:#{1,6}\s+|[-*+]\s+|>\s+|!?\[)", "", fragment)
                s = fragment.strip().strip("*_`")
                if s and s not in seen and len(s) <= 500:
                    seen.add(s)
                    yield s, meta, weak, rendered

def dollars(match):
    digits = match["n"].replace(",", "")
    whole, _, fraction = digits.partition(".")
    scale = SCALES[(match["s"] or "").strip().lower()]
    value, remainder = divmod(int(whole + fraction) * scale, 10 ** len(fraction))
    return None if remainder else value

def supported(domain, s):
    named, company, legal = subject(domain)
    if not named.search(s) or NEG.search(s):
        return {}
    fields = {f for f, p in MATCH.items() if p.search(s)}
    values = {}
    if "legal_name" in fields:
        values["legal_name"] = legal.findall(s, overlapped=True)
    if "hq_city" in fields:
        values["hq_city"] = CITY.findall(s)
    if "ceo" in fields:
        separated = MATCH["ceo"].sub("|", company.sub("|", s))
        values["ceo"] = [n for n in NAMES.findall(separated) if len(n.split()) in (2, 3)]
    if fields & {"headcount_range", "founded_year", "funding_total"}:
        amounts = list(AMOUNT.finditer(s))
        numbers = NUMBER.findall(AMOUNT.sub("|", s))
        if "funding_total" in fields:
            values["funding_total"] = [v for m in amounts if (v := dollars(m)) is not None]
        if "founded_year" in fields:
            values["founded_year"] = [int(n) for n in numbers if re.fullmatch(r"(?:18|19|20)\d\d", n)]
        if "headcount_range" in fields:
            counts = [int(n.replace(",", "")) for n in numbers if "." not in n]
            values["headcount_range"] = [next((b for top,b in BUCKETS if n <= top), "10001+") for n in counts if n > 0]
    return {f: vs[0] for f, vs in values.items() if len(set(vs)) == 1}

def own(url, domain):
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host == domain or host.endswith("." + domain)

# Identify antecedents of relative clauses, e.g. "works with North Line,
# which employs ...". First-party publication does not transfer that fact.
ENTITY = r"(?:[\p{Lu}][\p{L}\p{N}&.-]*(?: [\p{Lu}][\p{L}\p{N}&.-]*)*)"
RELATIVE = re.compile(rf"(?P<entity>{ENTITY})\s*,?\s+(?i:which|who|whose|that|an? (?:company|business|startup|firm) (?:that|which)?)\b(?P<clause>[^,;]*)")
ROLE = re.compile(rf"(?i:\b(?:portfolio company|client|customer|subsidiary|vendor|supplier|partner))[, :]+(?P<entity>{ENTITY})(?P<clause>[^;]*)")
ROUND = re.compile(r"\b(?:round|tranche|series [a-z]\d?|(?:pre[- ]?)?seed (?:investment|funding|financing))\b", re.I)
CUMULATIVE = re.compile(r"\b(?:to date|cumulative|lifetime|all[- ]time|aggregate (?:equity |venture )?(?:funding|financing)|(?:full|entire) (?:funding|financing) history|(?:entirety|whole) of (?:its |the )?(?:equity |venture )?(?:funding|financing)|(?:only|sole) (?:fundraising |funding |financing )?round|(?:over|across) (?:[0-9]+|all|multiple|several|[a-z]+) (?:funding |financing )?rounds|total (?:equity )?(?:funding|investment|raised)|funding total|bringing (?:its |the )?total|in total)\b", re.I)

COUNT_NOUN = r"(?:employees|staff(?: members)?|people|workers|team members|professionals)"
COUNT_MOD = r"(?:(?:about|roughly|around|approximately|over|nearly|between|more than|at least|up to|just over) )?"
COUNT_NUM = NUM_LEFT + NUM + NUM_RIGHT + r"(?:[+]|[-–—] ?[0-9,]+)?"
COUNT_UNIT = re.compile(LEFT + COUNT_NUM + rf" (?:total |full[- ]time |permanent |worldwide |global )*{COUNT_NOUN}" + RIGHT, re.I)
COUNT_PREDICATE = re.compile(rf"\b(?:employs|(?:workforce|headcount|staff|number of employees)(?: size)?(?: in (?:19|20)\d\d)?(?: (?:of|is|was|stands at|stood at|numbers|totals|has reached|has))?[:=]?) [~≈]?{COUNT_MOD}{COUNT_NUM}(?![%\p{{L}}\p{{N}}])", re.I)
PERSON_LINK = re.compile(r"(?:\s|[,()—–:-]|'s|’s|&|/(?=\w)|\b(?:a|the|our|its|as|of|at|is|was|has|been|serves|served|became|named|appointed|current|acting|interim|new|lead|led|leads|and|founder|co-founder|president|chair|chairman|since|also|company|chief|executive|officer)\b)*", re.I)

def is_executive(domain, sentence, value):
    # Names can occur in headlines, book titles or quotations. Require a
    # grammatical connection between the purported person and the role.
    for name in re.finditer(re.escape(value), sentence):
        for role in MATCH["ceo"].finditer(sentence):
            left, right = sorted((name,role), key=lambda x: x.start())
            gap = subject(domain)[0].sub("",sentence[left.end():right.start()])
            employer = re.match(rf" (?i:of|at|for) ({ENTITY})",sentence[role.end():])
            if employer and not subject(domain)[0].search(employer[1]):
                continue
            if PERSON_LINK.fullmatch(gap):
                return True
            if name.end() <= role.start() and re.fullmatch(r"(?i)\s*,?\s*(?:who|and who)\b[^,;:!?“”\"]{0,110}\b(?:as|is|was|became|remains)(?: (?:its|the|our|their|current|acting|new|interim))* ",gap):
                return True
    return False

AS_OF = re.compile(r"(?i)(?:,? as (?:of|at) | on | \()(?P<date>(?:[A-Za-z]{3,9} \d{1,2},? (?:19|20)\d\d|(?:19|20)\d\d-\d\d-\d\d|[A-Za-z]{3,9} (?:19|20)\d\d))(?:\))?[.!]?$")
SECONDARY = re.compile(r"(?i)\b(?:selling|existing) (?:share|stock)holders?\b|\bsecondary (?:share sales?|tender offers?|sales? proceeds)\b")
PUBLIC_TRANCHE = re.compile(r"(?i)(?:latest|last|most recent) (?:funding |round )?(?:was|included)[^.;]{0,95}(?:IPO|public offering)|(?:latest|last|most recent) (?:funding |round )?(?:was|included)[^;\n]{0,90}post[- ]IPO")
ISSUER_ONLY = re.compile(r"(?i)\b(?:net proceeds (?:to|received by) (?:the company|the issuer)|excluding (?:all )?(?:secondary|selling|existing)|primary (?:shares|proceeds) only)\b")

def dated_count(sentence):
    match = AS_OF.search(sentence)
    if not match or NEG.search(sentence):
        return None
    raw_date = match["date"].replace(",","")
    for form in ("%Y-%m-%d","%B %d %Y","%b %d %Y","%B %Y","%b %Y"):
        try:
            date = datetime.strptime(raw_date,form).date().isoformat()
        except ValueError:
            continue
        return sentence[:match.start()].strip(),date
    return None

def is_company_count(domain, sentence):
    if sentence.rstrip().endswith("?") or re.search(r"(?i)\b(?:layoffs?|laid off|lay off|cutting|dismissed)\b", sentence):
        return False
    if re.search(r"(?i)\b(?:its|the|their) (?:largest|smallest|local|regional) (?:office|region|division|team)\b",sentence):
        return False
    # Remove the grammatical owner from noun phrases such as "employees at
    # Company" and "the worldwide headcount for Company", before measuring.
    count_clause = subject(domain)[0].sub("SUBJECT",sentence)
    count_clause = re.sub(r"(?i)\b(?:at|of|for|within|employed by|working (?:at|for)) (?:the company|SUBJECT)(?: worldwide| globally)?\b","",count_clause)
    count_clause = " ".join(count_clause.split())
    if COUNT_PREDICATE.search(count_clause):
        return True
    for unit in COUNT_UNIT.finditer(count_clause):
        before, after = count_clause[:unit.start()],count_clause[unit.end():]
        if re.match(r"(?i)\s+(?:use|using|used|access|signed|joined|logged|to (?:edit|use|test|review)|in @)", after):
            continue
        if re.search(r"(?i)\b(?:invited|participants?|customers?|workshop|testers?|users?)\b", before) and not re.search(r"\bSUBJECT (?:has|had|employs|employed) ", before):
            continue
        if re.search(r"(?i)\bpeople$", unit.group()) and not (
            re.search(r"\bSUBJECT\b",before) or re.match(r"(?i)\s+(?:work|are employed|are on staff) (?:for|at|by) SUBJECT\b",after)
        ):
            continue
        return True
    return False

def another_subject(domain, field, sentence, value):
    name = subject(domain)[0]
    # A proper name immediately before a relative clause or after a
    # relationship label identifies the entity governed by that clause.
    for pattern in (RELATIVE, ROLE):
        for match in pattern.finditer(sentence):
            if field == "ceo" and value in match["entity"]:
                # In a personal relative clause the named executive is the
                # antecedent of "who serves as CEO", not a second company.
                continue
            phrase = MATCH[field].search(match["clause"])
            if phrase and not name.search(match["entity"]) and not name.search(match["clause"][:phrase.start()]):
                return True
    return False

class Evidence:
    def __init__(self, domain):
        self.domain = domain
        self.pages = []
        self.candidates = {f: [] for f in PHRASES}
        self.seen = set()
        self.unattributed = set()
        self.unverified_funding = set()

    def add(self, url, text, provider, kind, title="", date="", claim=None):
        if not url or not text:
            return
        identity = (url, text, provider, kind, repr(claim))
        if identity in self.seen:
            return
        self.seen.add(identity)
        self.pages.append(dict(url=url, text=text, provider=provider, kind=kind, title=title, date=date, claim=claim))
        first = own(url, self.domain)
        try:
            host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        except ValueError:
            return
        label = self.domain.split(".")[0]
        namesake = not first and host.split(".")[0] == label
        # A same-named business on its own different domain needs a link to
        # this company. Syndicated/editorial sources can identify it in prose.
        identified = re.search(words(self.domain), text) or re.search(words(self.domain), title)
        header = {}
        if text.splitlines() and HEADER.match(text.splitlines()[0]):
            block = re.split(r"\r?\n\s*\r?\n", text, maxsplit=1)[0]
            header = dict((k,v.strip()) for k,_,v in (line.partition(":") for line in block.splitlines()))
        foreign_profile = header.get("Kind", "").lower() == "own" and not first and header.get("Registrant", "").lower() != self.domain
        title_domain = re.search(r"(?i)\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)\s+(?:(?:company|corporate)\s+)?profile\b", title)
        different_profile = title_domain and title_domain[1].lower().removeprefix("www.") != self.domain
        linked = any(own(p["url"], self.domain) and url in p["text"] for p in self.pages)
        if (namesake or foreign_profile or different_profile) and not (first or identified or linked):
            self.unattributed.add(url)
        if url in self.unattributed:
            return
        # An offering figure can include shares sold by prior owners. A
        # source rolling it into lifetime financing must identify issuer-only
        # proceeds before its total can support the requested equity field.
        if SECONDARY.search(text) or PUBLIC_TRANCHE.search(text):
            self.unverified_funding.add(url)
        article_date = re.search(r"(?im)^(?:published(?: on)?|updated(?: on)?|date)[: ]+((?:19|20)\d\d-\d\d-\d\d)", text)
        for s, meta, weak, rendered in passages(text):
            if kind == "snippet" and (s.endswith(("…", "...")) or (len(text) >= 300 and text.rstrip().endswith(s) and not re.search(r'[.!?]["”’)]*$',s))):
                continue
            values = supported(self.domain, s)
            visible = supported(self.domain, rendered) if s != rendered else values
            count_excerpt = dated_count(s) if MATCH["headcount_range"].search(s) else None
            if count_excerpt:
                # A complete count proposition may precede a trailing date.
                # Recheck the literal shorter excerpt independently; the date
                # qualifies its vintage, not the count or its bucket.
                short, _ = count_excerpt
                count_value = supported(self.domain, short).get("headcount_range")
                if count_value is not None and not NEG.search(rendered) and short in rendered:
                    values["headcount_range"] = visible["headcount_range"] = count_value
            for f, v in values.items():
                if visible.get(f) != v:
                    continue
                if claim and (claim[0] != f or str(claim[1]) != str(v)):
                    continue
                if f == "ceo" and not is_executive(self.domain, rendered, v):
                    continue
                if f == "headcount_range" and not is_company_count(self.domain, rendered):
                    continue
                if another_subject(self.domain, f, rendered, v):
                    continue
                lookalike = re.findall(r"\b" + re.escape(self.domain.split(".")[0]) + r"\.[a-z]{2,}(?:\.[a-z]{2,})?\b", s, re.I)
                if lookalike and self.domain not in [x.lower() for x in lookalike]:
                    continue
                # Round size is not a company's cumulative equity funding.
                if f == "funding_total" and not CUMULATIVE.search(rendered):
                    event = re.search(r"(?i)\braised\b[^;]{0,75}\bfrom ", rendered) and not re.search(r"(?i)\b(?:has|have|had) raised\b", rendered)
                    if ROUND.search(rendered) or event:
                        continue
                dated = meta.get("Effective") or meta.get("Published") or date or (article_date[1] if article_date else "")
                if not dated:
                    dates = DATE.findall(s) or DATE.findall(title)
                    dated = max(dates, default="")
                equity_total = f == "funding_total" and bool(re.search(r"(?i)\b(?:venture|equity) (?:capital|funding|financing|investment)\b", rendered))
                excerpt = s
                if f == "headcount_range" and count_excerpt and supported(self.domain, count_excerpt[0]).get(f) == v:
                    excerpt, dated = count_excerpt
                rank = (str(dated)[:10], first, equity_total, not weak, kind != "snippet")
                cite = {"url": url, "excerpt": excerpt, "provider": provider}
                self.candidates[f].append({"value": v, "citation": cite, "rank": rank, "weak": weak})
    def fields(self):
        result = unknown()
        for f, items in self.candidates.items():
            eligible = [item for item in items if item["citation"]["url"] not in self.unattributed]
            if f == "funding_total":
                eligible = [item for item in eligible if item["citation"]["url"] not in self.unverified_funding or ISSUER_ONLY.search(item["citation"]["excerpt"])]
            if eligible:
                best = max(eligible, key=lambda x: x["rank"])
                result[f] = {"value": best["value"], "status": "known", "citations": [best["citation"]]}
        return result
