"""Company-specific, sentence-level support rules from Appendix A."""
import re
from collections import defaultdict
from decimal import Decimal, localcontext
from urllib.parse import urlsplit

import regex

from state import FIELDS, unknown_fields


PHRASES = {
    "legal_name": ("legal name", "registered name", "registered as", "registered company", "legal entity", "name of record"),
    "hq_city": ("headquartered in", "headquarters in", "head office in", "based in", "registered office in", "registered seat in"),
    "ceo": ("chief executive officer", "chief executive", "CEO"),
    "founded_year": ("founded", "founding", "established", "incorporated"),
    "headcount_range": ("employs", "employees", "staff", "people", "headcount", "workforce"),
    "funding_total": ("raised", "funding", "invested", "investment"),
}
NEGATIONS = ("in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to", "aims to",
             "seeking", "could", "would", "might", "reportedly", "rumoured", "former", "formerly", "will become", "not")
SUFFIXES = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH", "AG", "KG",
            "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.", "S.r.l.",
            "S.p.A.", "s.r.o.", "a.s.", "K.K.")
LEFT = r"(?<![\p{L}\p{N}])"
RIGHT = r"(?![\p{L}\p{N}])"
CAP = LEFT + r"\p{Lu}\p{Ll}+" + RIGHT
UPPER = LEFT + r"\p{Lu}{2,}" + RIGHT


def alternatives(items):
    return "(?:" + "|".join(regex.escape(s) for s in items) + ")"


def words(items):
    return LEFT + "(?i:" + alternatives(items) + ")" + RIGHT


STATEMENTS = {f: regex.compile(words(p)) for f, p in PHRASES.items()}
NEGATIVE = regex.compile(words(NEGATIONS))
SUFFIX_END = regex.compile(LEFT + alternatives(s for s in SUFFIXES if s.endswith(".")) + "$")
BREAK = re.compile(r"""([.!?])["”’)]*(?=\s)""")
HEADER = regex.compile(r"^\p{Lu}\p{Ll}+(?:-\p{Lu}\p{Ll}+)*:")
CITY = regex.compile(words(PHRASES["hq_city"]) + " (" + CAP + "(?:[ -]" + CAP + ")*)")
NAMES = regex.compile(CAP + "(?: " + CAP + ")+")

NUMBER_CORE = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NUM_LEFT = LEFT + r"(?<![0-9][,.])"
NUM_RIGHT = RIGHT + r"(?![,.][0-9])"
NUMBER = regex.compile(NUM_LEFT + NUMBER_CORE + NUM_RIGHT)
SHORT = r"(?:mn|bn|k|m)"
LONG = r"(?:thousand|million|billion)"
AMOUNT = regex.compile(NUM_LEFT + r"(?:(?:US\$|USD|\$) ?(?P<n1>" + NUMBER_CORE + r")(?P<s1>" + SHORT +
                       "| " + LONG + r")?|(?P<n2>" + NUMBER_CORE + r")(?: (?P<s2>" + LONG +
                       r"))? (?:US )?dollars)" + NUM_RIGHT, regex.I)
SCALES = {"": 1, "k": 1000, "thousand": 1000, "m": 10**6, "mn": 10**6, "million": 10**6,
          "bn": 10**9, "billion": 10**9}
BANDS = ((10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"), (1000, "501-1000"),
         (5000, "1001-5000"), (10000, "5001-10000"))


def prose(text):
    lines = text.splitlines()
    if lines and HEADER.match(lines[0]):
        start = next((i + 1 for i, line in enumerate(lines) if not line.strip()), len(lines))
        return lines[start:]
    return lines


def sentences(lines):
    for raw in lines:
        line = " ".join(raw.split())
        start = 0
        for match in BREAK.finditer(line):
            if match[1] == "." and SUFFIX_END.search(line[max(start, match.start() - 12):match.start() + 1]):
                continue
            part = line[start:match.end()].strip()
            if part:
                yield part
            start = match.end()
        if part := line[start:].strip():
            yield part


def numeric_values(sentence):
    amounts = []
    for item in AMOUNT.finditer(sentence):
        n = (item["n1"] or item["n2"]).replace(",", "")
        scale = SCALES[(item["s1"] or item["s2"] or "").strip().lower()]
        with localcontext() as ctx:
            ctx.prec = len(n) + 12
            val = Decimal(n) * scale
        if val == val.to_integral_value():
            amounts.append(int(val))
    numbers = NUMBER.findall(AMOUNT.sub("|", sentence))
    years = [int(n) for n in numbers if len(n) == 4 and n.isdigit() and 1800 <= int(n) <= 2099]
    bands = []
    for n in numbers:
        if "." not in n and (headcount := int(n.replace(",", ""))) > 0:
            bands.append(next((band for cap, band in BANDS if headcount <= cap), "10001+"))
    return {"founded_year": years, "headcount_range": bands, "funding_total": amounts}


class Support:
    def __init__(self, domain):
        self.domain = domain
        self.name = domain.split(".")[0].replace("-", " ")
        subject = words((domain, self.name))
        self.subject = regex.compile(subject)
        self.remove_name = regex.compile(words((self.name,)))
        self.company_form = regex.compile(subject + ",? " + alternatives(SUFFIXES) + RIGHT)
        self.legal = regex.compile(subject + "(?: (?:" + CAP + "|" + UPPER + "))*?,? " +
                                   alternatives(SUFFIXES) + RIGHT)

    def parse(self, sentence):
        if not 0 < len(sentence) <= 500 or not self.subject.search(sentence) or NEGATIVE.search(sentence):
            return {}
        values = {}
        numbers = None
        for f, phrase in STATEMENTS.items():
            if not phrase.search(sentence):
                continue
            if f == "legal_name":
                candidates = self.legal.findall(sentence, overlapped=True)
            elif f == "hq_city":
                candidates = CITY.findall(sentence)
            elif f == "ceo":
                masked = self.remove_name.sub("|", phrase.sub("|", sentence))
                candidates = [s for s in NAMES.findall(masked) if len(s.split()) in (2, 3)]
            else:
                if numbers is None:
                    numbers = numeric_values(sentence)
                candidates = numbers[f]
            if candidates and len(set(candidates)) == 1:
                values[f] = candidates[0]
        return values


def source_date(value):
    if isinstance(value, str):
        match = re.search(r"\b((?:19|20)[0-9]{2})(?:-(0[1-9]|1[0-2])(?:-([0-3][0-9]))?)?\b", value)
        if match:
            return tuple(int(x or 0) for x in match.groups())
    return (0, 0, 0)


def publication_date(published, url, text):
    date = source_date(published)
    if date[0]:
        return date
    path = urlsplit(url).path
    stamped = re.search(r"/((?:19|20)\d{2})[/-](\d{2})[/-](\d{2})(?:/|-|$)", path)
    if stamped:
        return tuple(map(int, stamped.groups()))
    named = re.search(r"(?im)^(?:\W*(?:published|updated)(?:\s+on)?\s*[:|-]?\s*)?"
                      r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
                      r"Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+"
                      r"((?:19|20)\d{2})\s*(?:$|\|)", text[:4096])
    return (int(named[1]), 0, 0) if named else date


def prose_excerpt(sentence):
    # Markdown footnotes and their destinations refer out to another page. The adjacent
    # source text is already contiguous, so it can be quoted without rewriting anything.
    sentence = re.sub(r"(?:\s*\[\\?\[\d+\\?\]\]\(https?://\S+?\))+(?:[.,])?$", "", sentence).strip()
    title_link = re.fullmatch(r"""\[["“]?(.*?)["”]?\]\(https?://[^ ]+\)[.,]?""", sentence)
    return title_link[1] if title_link else sentence


class Evidence:
    def __init__(self, domain, as_of_year=None):
        self.support = Support(domain)
        self.as_of_year = as_of_year
        self.candidates = {f: defaultdict(list) for f in FIELDS}
        self.seen = set()
        self.parsed = {}
        self.staff_observations = {}

    def observe_staff_count(self, excerpt, source_stamp):
        name = self.support.subject.pattern
        count = r"(?P<count>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
        statement = regex.search(name + r"(?:['’]s)?\s+(?i:(?:had|has|employs|employed|headcount reached)"
                                 r"\s+(?:(?:approximately|about|over|roughly)\s+)?)" + count +
                                 r"\s+(?i:(?:full.time\s+|total\s+)?(?:employees|people))\b", excerpt)
        if not statement or NEGATIVE.search(excerpt):
            return
        date_text = re.search(r"(?i)\b(?:as (?:of|at)|(?:at )?the end of|fiscal year ended)\s+"
                              r"([A-Za-z0-9 ,/-]{0,24}?\b(?:19|20)\d{2}\b)", excerpt)
        if date_text:
            stamp = source_date(date_text[1])
        else:
            stamp = source_stamp
        if stamp[0]:
            amount = int(statement["count"].replace(",", ""))
            self.staff_observations[amount] = max(stamp, self.staff_observations.get(amount, (0, 0, 0)))

    def observe(self, url, provider, text, published=None, claim=None):
        if not isinstance(text, str) or not isinstance(url, str) or not url:
            return
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return
        if not host:
            return
        domain = self.support.domain
        first_hand = host == domain or host.endswith("." + domain)
        if claim is None:
            lines = prose(text)
            if text and HEADER.match(text):
                header = re.split(r"\r?\n\s*\r?\n", text, maxsplit=1)[0]
                if date_line := re.search(r"(?im)^(?:Published(?:-At)?|Date|Updated(?:-At)?):\s*(.+)$", header):
                    published = date_line[1]
            excerpts = sentences(lines)
        else:
            if HEADER.match(text) and re.match(r"^(Facts|Title|Date|Published|Source):", text):
                return
            excerpts = list(sentences([" ".join(text.split())]))
            if len(excerpts) != 1:
                return
        date = publication_date(published, url, text)
        for excerpt in excerpts:
            if claim is None:
                cleaned = prose_excerpt(excerpt)
                if cleaned != excerpt:
                    cleaned_values = self.support.parse(cleaned)
                    if cleaned_values and all(cleaned_values.get(k) == val
                                              for k, val in self.support.parse(excerpt).items()):
                        excerpt = cleaned
            if len(excerpt) > 500:
                continue
            if "employ" in excerpt.casefold() or "people" in excerpt.casefold():
                self.observe_staff_count(excerpt, date)
            visible = re.sub(r"https?://\S+", "", excerpt)
            linked_only = not self.support.subject.search(visible)
            if excerpt not in self.parsed:
                self.parsed[excerpt] = self.support.parse(excerpt)
            for f, v in self.parsed[excerpt].items():
                if claim and (claim[0] != f or not self.matches_claim(v, claim[1])):
                    continue
                entity_only = (f in ("legal_name", "headcount_range") and not first_hand and
                        domain not in text.casefold() and re.search(
                            re.escape(self.support.name) + r"\s+(?:opco|subsidiary|division|regional office)\b",
                            excerpt, re.I))
                key = (f, v, url, provider, excerpt, published)
                if key in self.seen:
                    continue
                self.seen.add(key)
                # Prefer the freshest dated source, then the company's own publication.
                context = -1 if linked_only or entity_only else self.relevance(f, v, excerpt)
                # Appendix A determines eligibility. Source quality only orders the eligible
                # alternatives and identifies weak fields for additional retrieval.
                strength = max(-1, min(1, context))
                if f == "funding_total" and context == 3:
                    strength = 2
                if (f == "headcount_range" and not date[0] and not first_hand
                        and re.search(r"\b(?:about|estimated|approximately|roughly|around)\b", excerpt, re.I)):
                    strength = min(strength, 0)
                rank = (strength, date, first_hand, context)
                self.candidates[f][v].append((rank, {"url": url, "provider": provider, "excerpt": excerpt}))

    @staticmethod
    def matches_claim(value, claim):
        if type(value) is type(claim):
            return value == claim
        if type(value) is int and isinstance(claim, str):
            return str(value) == claim.strip().replace(",", "")
        return False

    def relevance(self, field, value, excerpt):
        text = excerpt.casefold()
        company = re.escape(self.support.name.casefold())
        if field == "legal_name":
            if re.search(r"legal entit(?:y|ies) (?:you|the (?:customer|user))|your legal entity", text):
                return -1
            if self.support.company_form.fullmatch(value):
                return 2
            # An extended company name can designate a product subsidiary or regional
            # company. Prefer a sentence that expressly names it as the subject's legal identity.
            alias = re.escape(value.casefold())
            return int(bool(re.search(r"(?:legal name|registered name|registered as|name of record|legal entity)"
                                      r"[\s:,(“\"-]*(?:is\s+)?" + alias, text)))
        if field == "funding_total":
            if (re.search(r"\b(?:valued at|valuation of)\b", text)
                    or re.search(company + r"\s+(?:has )?(?:invested in|led an? investment in)", text)
                    or re.search(r"(?:than (?:that of )?|funding from |investors include )" + company, text)):
                return -1
            if re.search(r"(raised|funding|investment).{0,80}(total|to date|cumulativ)|(?:total|cumulativ).{0,40}(funding|raised|investment)|(?:across|over|in)\s+\d+\s+(?:funding )?rounds", text):
                return 3
            if any(x in text for x in ("series ", "seed round", "invested by", "funding round", "new funding",
                                       "part of a round", "additional $", "funding split", "new investment",
                                       "fresh funding", "new financing")):
                return 0
            # A named investor's commitment or its share of gains is a component of
            # financing. A direct statement of what the subject has raised can stand alone.
            return int(bool(re.search(company + r"(?:(?:,? inc\.?,?)|(?:['’]s)|\s+(?:has|had|successfully|reportedly))*"
                                      r"\s+(?:raised|funding (?:totals|reached|stands at))\b", text)))
        if field == "hq_city":
            if re.search(company + r".{0,80}\bacquired\b.{0,100}\bbased in", text):
                return -1
            return 1 + int("based in" not in text)
        if field == "headcount_range":
            if re.search(r"\byears? (?:of age|old)\b|\b(?:laid off|lays? off|layoffs?|laying off|jobs? (?:cut|cuts)|regional|staff in the region)\b", text):
                return -1
            if re.search(r"\b(?:largest region|of its global workforce|employee profiles|profile coverage|"
                         r"company directory records)\b", text):
                return -1
            if re.search(r"before the cuts|team is now|early team|initial team|\bjoined\b.{0,75}\bwhen\b", text):
                return 0
            dated = re.findall(r"(?:^\W*|\b(?:in|since|as of|during)\s+|(?<=\d)[–—-])((?:19|20)\d{2})\b", text)
            years = [int(y) for y in dated]
            if years and self.as_of_year and max(years) < self.as_of_year - 2:
                return 0
            count = r"\d[\d,-]*\+?"
            if re.search(r"(?:employs|employees|headcount|workforce|staff)(?:\s+(?:about|roughly|around|of|is|at|has|approximately|over|nearly|stands|to|now))*[: ]+" + count, text):
                return 2
            if re.search(count + r"\s+(?:(?:total|full.time|part.time|global|worldwide|permanent|and)\s+)*"
                         r"(?:employees|people|staff)\b", text.replace("**", "")):
                if re.search(r"\b(?:people|employees)\s+(?:use|using|attend|visiting|subscribe|participated|surveyed)\b", text):
                    return -1
                return 2
            return 0
        if field == "ceo":
            # Strip link markup for ranking only. The citation retains the original text.
            readable = re.sub(r"\[([^\]]+)\]\(https?://[^)\s]+\)", r"\1", excerpt).replace("*", "").replace("_", "")
            principal = re.search(r"(?i:\b(?:ceo|chief executive(?: officer)?)\s+(?:of|at|for)\s+(?:the\s+)?)"
                                  r"([A-Z][^,.;:\n]+)", readable)
            if principal and not re.match(r"(?:company|business|group|firm)\b|" + company + r"(?!\w)",
                                          principal[1].casefold()):
                return -1
            if re.search(r"\b(?:depart(?:ed)? as|ousted|fired|resigned|stepped down|step down|departing|ex-ceo)\b", text):
                return -1
            name = re.escape(value.casefold())
            role = r"(?:chief executive(?: officer)?|ceo)"
            title = r"(?:(?:co-founder|founder|president|chairman|chair|current|new|interim|the|and)\s+)*" + role
            spoken = readable.casefold()
            if (re.search(title + r"[\s:,\-–—]+" + name, spoken)
                    or re.search(name + r"[\s,]+(?:(?:is|serves as|was named|became|is now)\s+)?(?:the\s+)?"
                                 + title, spoken)
                    or re.search(name + r".{0,35}\b(?:leads|led|runs|heads)\b.{0,45}\bas\s+(?:its\s+)?" + role, spoken)
                    or re.search(company + r".{0,35}\b(?:named|appointed|selected|chose)\s+" + name +
                                 r"[\s,]+(?:(?:as|its|the|new)\s+)*" + role, spoken)
                    or re.search(name + r"\s+is\s+" + company + r"['’]s\s+" + title, spoken)):
                return 3
            return 0
        if field == "founded_year":
            return 2 if re.search(company + r"\s+(?:was\s+)?(?:co-)?founded\b", text) else 1
        return 1

    def missing(self):
        missing = [f for f, values in self.candidates.items()
                   if not any(rank[0] > 0 for entries in values.values() for rank, _ in entries)]
        if self.staff_observations and "headcount_range" not in missing:
            newest = max(self.staff_observations, key=self.staff_observations.get)
            band = next((band for cap, band in BANDS if newest <= cap), "10001+")
            if band not in self.candidates["headcount_range"]:
                missing.append("headcount_range")
        return missing

    def fields(self):
        fields = unknown_fields()
        for f, values in self.candidates.items():
            if not values:
                continue
            def score(value):
                entries = values[value]
                # Cumulative funding rises between rounds. When provenance and dates tie,
                # an explicitly cumulative larger total covers the smaller one.
                cumulative = value if f == "funding_total" else 0
                rank = max(rank for rank, _ in entries)
                if f == "headcount_range" and rank[3] >= 2:
                    for count, stamp in self.staff_observations.items():
                        band = next((b for cap, b in BANDS if count <= cap), "10001+")
                        if band == value and stamp > rank[1]:
                            rank = (max(1, rank[0]), stamp, rank[2], rank[3])
                return rank, cumulative, len({c["url"] for _, c in entries})
            best = max(values, key=score)
            entries = sorted(values[best], key=lambda x: x[0], reverse=True)
            fields[f] = {"status": "known", "value": best, "citations": [entries[0][1]]}
        return fields
