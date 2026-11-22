"""Apply the Stage 1 Appendix A rules to provider text."""

from dataclasses import dataclass
from functools import lru_cache

import regex as re


PHRASES = {
    "legal_name": ("legal name", "registered name", "registered as",
                   "registered company", "legal entity", "name of record"),
    "hq_city": ("headquartered in", "headquarters in", "head office in", "based in",
                "registered office in", "registered seat in"),
    "ceo": ("chief executive officer", "chief executive", "CEO"),
    "founded_year": ("founded", "founding", "established", "incorporated"),
    "headcount_range": ("employs", "employees", "staff", "people", "headcount", "workforce"),
    "funding_total": ("raised", "funding", "invested", "investment"),
}
FIELDS = tuple(PHRASES)
EXECUTIVE_TITLES = ("cfo", "coo", "cto")
PHRASES.update({
    "cfo": ("chief financial officer", "CFO"),
    "coo": ("chief operating officer", "COO"),
    "cto": ("chief technology officer", "CTO"),
})
INTEGER_FIELDS = {"founded_year", "funding_total"}
NEGATIONS = ("in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to",
             "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured",
             "former", "formerly", "will become", "not")
LEGAL_FORMS = ("Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc",
               "PLC", "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj",
               "B.V.", "N.V.", "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.",
               "a.s.", "K.K.")
HEADCOUNT = ((10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
             (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000"))
SCALES = {"k": 10**3, "thousand": 10**3, "m": 10**6, "mn": 10**6, "million": 10**6,
          "bn": 10**9, "billion": 10**9}
BOUNDARY = r"[\p{L}\p{N}]"
LEFT, RIGHT = rf"(?<!{BOUNDARY})", rf"(?!{BOUNDARY})"
CAPITALISED = rf"{LEFT}\p{{Lu}}\p{{Ll}}+{RIGHT}"
UPPERCASE = rf"{LEFT}\p{{Lu}}{{2,}}{RIGHT}"
NUMBER = r"(?<![0-9][.,])(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?(?![.,][0-9])"
BARE_NUMBER = re.compile(LEFT + NUMBER + RIGHT)
PREFIX_AMOUNT = re.compile(
    rf"{LEFT}(?P<prefix>US\$|USD|\$) ?(?P<number>{NUMBER})"
    rf"(?P<scale>mn|bn|[km]| (?:thousand|million|billion))?{RIGHT}", re.I
)
DOLLARS_AMOUNT = re.compile(
    rf"{LEFT}(?P<number>{NUMBER})(?P<scale> (?:thousand|million|billion))?"
    rf" (?P<suffix>US dollars|dollars){RIGHT}", re.I
)
# An otherwise ambiguous dollar spelling can be explicitly denominated by
# an adjacent ISO code, currency name, regional dollar sign, or symbol.
FOREIGN_CODES = (
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN "
    "BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD "
    "FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY "
    "KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP "
    "MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR "
    "RMB RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB "
    "TJS TMT TND TOP TRY TTD TWD TZS UAH UGX UYU UZS VES VND VUV WST XAF XCD XCG XOF XPF YER "
    "ZAR ZMW ZWG ZWL"
).split()
DOLLAR_REGIONS = (
    r"Canadian|Australian|New Zealand|Hong Kong|Singapore(?:an)?|Taiwan(?:ese)?|"
    r"New Taiwan|Bahamian|Bermudian|Brunei|Cayman Islands|East Caribbean|Fijian|"
    r"Guyanese|Jamaican|Liberian|Namibian|Solomon Islands|Surinamese|"
    r"Trinidad and Tobago|Zimbabwean"
)
FOREIGN_NAMES = (
    r"euros?|sterling|(?:British )?pounds?|(?:Japanese )?yen|(?:Chinese )?yuan|"
    r"(?:South Korean |Korean )?won|(?:Indian )?rupees?|(?:Russian )?roubles?|"
    r"(?:Russian )?rubles?|(?:Swiss )?francs?|(?:Mexican )?pesos?|(?:Brazilian )?reais|"
    rf"(?:{DOLLAR_REGIONS})[ -]dollars?"
)
AMBIGUOUS_CODES = {"ALL", "ANG", "AWG", "BAM", "BOB", "ERN", "GEL", "HNL", "KES", "KIP",
                   "MOP", "PEN", "RON", "SIT", "SOS", "TRY", "WON"}
FOREIGN_MARKER = (
    rf"(?:{'|'.join(code for code in FOREIGN_CODES if code not in AMBIGUOUS_CODES)}|"
    rf"(?-i:{'|'.join(sorted(AMBIGUOUS_CODES & set(FOREIGN_CODES)))})|{FOREIGN_NAMES})"
)
FOREIGN_BEFORE = re.compile(
    rf"(?:{LEFT}{FOREIGN_MARKER}(?:-denominated)?(?: *[$(:-])? *"
    rf"|[€£¥₹₩₽₫₪₱฿₴₦₺₿] *)$", re.I
)
REGIONAL_CODES = "CA|CAN|C|AU|AUS|NZ|HK|SG|S|NT|MX|R|B|FJ|TT|EC|J|RD|Z"
# A$ denotes Australian dollars. A followed by a space can be an article.
REGIONAL_DOLLAR = re.compile(rf"{LEFT}(?:(?:{REGIONAL_CODES}) |(?i:{REGIONAL_CODES}) *\$ *|[Aa]\$ *)$")
FOREIGN_AFTER = re.compile(
    rf"(?: (?:mn|bn|[km]))?(?:(?: +| *[(\[)\],–—-] *)(?:(?:denominated |stated )?in )?"
    rf"{FOREIGN_MARKER}{RIGHT}"
    rf"(?! *(?:\$|[0-9]|equivalent\b))| *[€£¥₹₩₽₫₪₱฿₴₦₺₿](?! *[0-9]))", re.I
)
HEADER = re.compile(r"^\p{Lu}\p{Ll}+(?:-\p{Lu}\p{Ll}+)*:.*$")
END_OF_SENTENCE = re.compile(r'[.!?]["”’)]*(?=\s)')
PERSON_RUN = re.compile(rf"{CAPITALISED}(?: {CAPITALISED})*")
PLACE_RUN = re.compile(rf"{CAPITALISED}(?:[ -]{CAPITALISED})*")


def alternation(words):
    return "|".join(re.escape(word) for word in words)


def whole(words):
    return re.compile(rf"{LEFT}(?:{alternation(words)}){RIGHT}", re.I | re.FULLCASE)


STATEMENTS = {field: whole(phrases) for field, phrases in PHRASES.items()}
NEGATING = whole(NEGATIONS)
SUFFIX_AT_END = re.compile(
    rf"{LEFT}(?:{alternation(form for form in LEGAL_FORMS if form.endswith('.'))})\Z"
)


@lru_cache(maxsize=512)
def company_patterns(domain):
    company = domain.split(".")[0].replace("-", " ")
    names = "|".join(re.escape(name) for name in (domain, company))
    company_pattern = whole((domain, company))
    legal_pattern = re.compile(
        rf"{LEFT}(?i:{names}){RIGHT}(?: (?:{CAPITALISED}|{UPPERCASE}))*?"
        rf",? (?:{alternation(LEGAL_FORMS)}){RIGHT}", re.FULLCASE
    )
    return company_pattern, legal_pattern


def collapse(text):
    return " ".join(text.split())


def prose(text):
    lines = text.splitlines()
    if not lines or not HEADER.fullmatch(lines[0]):
        return lines
    return next((lines[i + 1:] for i, line in enumerate(lines) if not line.strip()), [])


def sentences(line):
    start = 0
    for ending in END_OF_SENTENCE.finditer(line):
        position = ending.start()
        if line[position] == "." and SUFFIX_AT_END.search(line, max(0, position - 12), position + 1):
            continue
        part = line[start:ending.end()].strip()
        if part:
            yield part
        start = ending.end()
    if remainder := line[start:].strip():
        yield remainder


@dataclass(frozen=True)
class Value:
    start: int
    end: int
    value: str | int | None


def foreign_currency(sentence, start, end, *, dollar_sign=False):
    before = sentence[max(0, start - 100):start]
    after = sentence[end:end + 100]
    return (FOREIGN_BEFORE.search(before) is not None
            or (dollar_sign and REGIONAL_DOLLAR.search(before) is not None)
            or FOREIGN_AFTER.match(after) is not None)


def integer(digits):
    # Parse arbitrarily long provider numbers without changing process-wide
    # JSON limits. The cap is comfortably beyond any plausible company figure.
    return int(digits) if len(digits) <= 1000 else None


def dollars(number, scale):
    whole_part, _, fractional_part = number.replace(",", "").partition(".")
    digits = integer(whole_part + fractional_part.rstrip("0"))
    if digits is None:
        return None
    denominator = 10 ** len(fractional_part.rstrip("0"))
    value, remainder = divmod(digits * SCALES.get(scale, 1), denominator)
    return value if not remainder else None


def amounts(sentence):
    prefixed = list(PREFIX_AMOUNT.finditer(sentence))
    # A suffix can qualify a prefixed amount, e.g. "$12 million US dollars".
    # Treat the combined spelling as one amount and inspect context outside it.
    suffixed = {match.start(): match for match in DOLLARS_AMOUNT.finditer(sentence)}
    for match in prefixed:
        end_match = suffixed.pop(match.start("number"), None)
        end = end_match.end() if end_match else match.end()
        if foreign_currency(sentence, match.start(), end, dollar_sign=match["prefix"] == "$"):
            continue
        yield Value(match.start(), end, dollars(match["number"], (match["scale"] or "").strip().lower()))
    for match in suffixed.values():
        if not foreign_currency(sentence, *match.span(), dollar_sign=True):
            yield Value(*match.span(), dollars(match["number"], (match["scale"] or "").strip().lower()))


def numeric_values(field, sentence, dollar_amounts):
    for match in BARE_NUMBER.finditer(sentence):
        if any(amount.start <= match.start() < amount.end for amount in dollar_amounts):
            continue
        number = match.group()
        if field == "founded_year":
            if len(number) == 4 and number.isascii() and number.isdigit() and 1800 <= int(number) <= 2099:
                yield Value(*match.span(), int(number))
        elif "." not in number:
            digits = number.replace(",", "").lstrip("0")
            if digits:
                count = int(digits) if len(digits) <= 5 else 10001
                bucket = next((label for maximum, label in HEADCOUNT if count <= maximum), "10001+")
                yield Value(*match.span(), bucket)


def names_of_executives(sentence, company, phrases):
    # Mask the excluded text with a non-word, non-space delimiter. Removing it
    # outright would join separate runs and shift the offsets used in citations.
    masked = list(sentence)
    for match in [*company.finditer(sentence), *phrases]:
        masked[match.start():match.end()] = "#" * (match.end() - match.start())
    for name in PERSON_RUN.finditer("".join(masked)):
        if 1 <= name.group().count(" ") <= 2:
            yield Value(*name.span(), name.group())


def values_for(field, sentence, company, legal, phrases):
    if field == "legal_name":
        return [Value(*match.span(), match.group()) for match in legal.finditer(sentence)]
    if field == "hq_city":
        cities = []
        for phrase in phrases:
            start = phrase.end() + 1
            if sentence[phrase.end():start] != " ":
                continue
            if place := PLACE_RUN.match(sentence, start):
                cities.append(Value(*place.span(), place.group()))
        return cities
    if field == "ceo" or field in EXECUTIVE_TITLES:
        return list(names_of_executives(sentence, company, phrases))
    dollar_amounts = list(amounts(sentence))
    if field == "funding_total":
        return [amount for amount in dollar_amounts if amount.value is not None]
    return list(numeric_values(field, sentence, dollar_amounts))


def statements(domain, sentence, fields=FIELDS):
    """Yield values and the spans that make the sentence self-contained."""
    company, legal = company_patterns(domain)
    company_mentions = list(company.finditer(sentence))
    if not company_mentions or NEGATING.search(sentence):
        return
    for field in fields:
        phrases = list(STATEMENTS[field].finditer(sentence))
        if not phrases:
            continue
        values = values_for(field, sentence, company, legal, phrases)
        if values and all(item.value == values[0].value for item in values):
            yield field, values[0].value, values, company_mentions, phrases


def supports(domain, field, value, excerpt):
    if field not in PHRASES or not 1 <= len(excerpt) <= 500:
        return False
    expected_type = int if field in INTEGER_FIELDS else str
    if type(value) is not expected_type or len(list(sentences(excerpt))) != 1:
        return False
    return any(found == value for _, found, *_ in statements(domain, excerpt, (field,)))


def bounded_excerpt(domain, sentence, field, value, values, mentions, phrases):
    if len(sentence) <= 500:
        return sentence
    value_start = min(item.start for item in values)
    value_end = max(item.end for item in values)
    for mention in mentions:
        for phrase in phrases:
            start = min(value_start, mention.start(), phrase.start())
            end = max(value_end, mention.end(), phrase.end())
            excerpt = sentence[start:end]
            if supports(domain, field, value, excerpt):
                return excerpt
    return None


def from_page(domain, text, fields=FIELDS):
    for line in prose(text):
        for original in sentences(line):
            sentence = collapse(original)
            for field, value, values, mentions, phrases in statements(domain, sentence, fields):
                excerpt = bounded_excerpt(domain, sentence, field, value, values, mentions, phrases)
                if excerpt and supports(domain, field, value, excerpt):
                    yield field, value, excerpt


def unknown_fields():
    return {field: {"value": None, "status": "unknown", "citations": []} for field in FIELDS}
