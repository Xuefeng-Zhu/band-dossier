"""Appendix A evidence matching (R15, R21)."""

from functools import lru_cache
import re


FIELDS = {
    "legal_name": str, "hq_city": str, "ceo": str, "founded_year": int,
    "headcount_range": str, "funding_total": int,
}
PHRASES = {
    "legal_name": ("legal name", "registered name", "registered as", "registered company",
                   "legal entity", "name of record"),
    "hq_city": ("headquartered in", "headquarters in", "head office in", "based in",
                "registered office in", "registered seat in"),
    "ceo": ("chief executive officer", "chief executive", "CEO"),
    "founded_year": ("founded", "founding", "established", "incorporated"),
    "headcount_range": ("employs", "employees", "staff", "people", "headcount", "workforce"),
    "funding_total": ("raised", "funding", "invested", "investment"),
}
NEGATIONS = (
    "in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to",
    "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured",
    "former", "formerly", "will become", "not",
)
SUFFIXES = (
    "Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC",
    "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.",
    "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.",
)
HEADCOUNTS = (
    (10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
    (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000"),
)

# Unicode alphanumerics are boundaries. An underscore is punctuation for Appendix A.
LEFT, RIGHT = r"(?<![^\W_])", r"(?![^\W_])"
WORD = re.compile(r"[^\W_]+")
SENTENCE_END = re.compile(r'''([.!?])["”’)]*(?=\s)''')


def phrases(values, flags=re.IGNORECASE):
    alternatives = "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))
    return re.compile(LEFT + "(?:" + alternatives + ")" + RIGHT, flags)


FIELD_RULES = {field: phrases(values) for field, values in PHRASES.items()}
NEGATING = phrases(NEGATIONS)
LEGAL_SUFFIX = "|".join(map(re.escape, sorted(SUFFIXES, key=len)))
ABBREVIATION = re.compile(LEFT + "(?:" + "|".join(
    re.escape(suffix) for suffix in SUFFIXES if suffix.endswith(".")
) + ")$")


@lru_cache(maxsize=256)
def company_pattern(domain):
    return phrases((domain, domain.split(".", 1)[0].replace("-", " ")))


def unknown_fields():
    return {field: {"value": None, "status": "unknown", "citations": []} for field in FIELDS}


def sentences(line):
    start = 0
    for ending in SENTENCE_END.finditer(line):
        if ending[1] == "." and ABBREVIATION.search(line, start, ending.start() + 1):
            continue
        sentence = line[start:ending.end()].strip()
        if sentence:
            yield sentence
        start = ending.end()
    if sentence := line[start:].strip():
        yield sentence


def prose_sentences(text):
    lines = text.splitlines()
    if lines and is_header(lines[0]):
        lines = lines[next((index + 1 for index, line in enumerate(lines) if not line.strip()), len(lines)):]
    for line in lines:
        yield from sentences(" ".join(line.split()))


def capitalized(word):
    return len(word) > 1 and word[0].isupper() and word[1:].islower() and word.isalpha()


def is_header(line):
    name, colon, _ = line.partition(":")
    return bool(colon) and all(capitalized(word) for word in name.split("-"))


def capital_end(text, start, joins):
    """End of the longest run of capitalised words joined as requested."""
    end = start
    while (match := WORD.match(text, start)) and capitalized(match[0]):
        end = match.end()
        if end == len(text) or text[end] not in joins:
            break
        start = end + 1
    return end


def legal_values(text, companies):
    suffix = re.compile(r",? (" + LEGAL_SUFFIX + ")" + RIGHT)
    for company in companies:
        end = company.end()
        while end < len(text):
            if match := suffix.match(text, end):
                yield text[company.start():match.end()], (company.start(), match.end())
                break
            word = WORD.match(text, end + 1) if text[end] == " " else None
            if not word or not (capitalized(word[0]) or
                                (len(word[0]) > 1 and word[0].isalpha() and word[0].isupper())):
                break
            end = word.end()


def hq_values(text, statements):
    for statement in statements:
        start = statement.end() + 1
        if text[statement.end():start] != " ":
            continue
        end = capital_end(text, start, " -")
        if end > start:
            yield text[start:end], (start, end)


def ceo_values(text, companies, statements):
    # Replace the removed spans with separators so surviving offsets still point to the source.
    masked = list(text)
    for match in (*companies, *statements):
        start, end = match.span()
        masked[start:end] = "\0" * (end - start)
    previous_end = -2
    start = end = words = 0
    for word in WORD.finditer("".join(masked)):
        joins_run = words and previous_end + 1 == word.start() and text[previous_end] == " "
        is_capitalized = capitalized(word[0])
        if words and (not joins_run or not is_capitalized):
            if words in (2, 3):
                yield text[start:end], (start, end)
            words = 0
        if not is_capitalized:
            continue
        if not words:
            start = word.start()
        end = previous_end = word.end()
        words += 1
    if words in (2, 3):
        yield text[start:end], (start, end)


NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
NUMBER_LEFT = LEFT + r"(?<!\d[.,])"
NUMBER_RIGHT = RIGHT + r"(?![.,]\d)"
BARE_NUMBER = re.compile(NUMBER_LEFT + NUMBER + NUMBER_RIGHT)
LONG_SCALE = r"(?:thousand|million|billion)"
SHORT_SCALE = r"(?:mn|bn|k|m)"
SCALE = {
    "": 0, "k": 3, "thousand": 3, "m": 6, "mn": 6, "million": 6, "bn": 9, "billion": 9,
}

# Currency codes and ordinary names are used only to qualify amounts, never to convert them.
FOREIGN_CODES = """
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV
BRL BSD BTN BWP BYN BYR BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUC CUP
CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW
KWD KYD KZT LAK LBP LKR LRD LSL LTL LVL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR
MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG
QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STD STN SVC
SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX UYU UYW UZS VED VES VND VUV
WST XAF XCD XCG XOF XPF YER ZAR ZMW ZWG ZWL
""".split()
AMBIGUOUS_CODES = {"ALL", "COP", "MAD", "TOP", "TRY"}
CODE = (r"(?i:" + "|".join(code for code in FOREIGN_CODES if code not in AMBIGUOUS_CODES)
        + r")|" + "|".join(sorted(AMBIGUOUS_CODES)))
REGIONAL = (
    r"Australian|Bahamian|Barbadian|Belize(?:an)?|Bermud(?:a|an|ian)|Brunei(?:an)?|"
    r"Canadian|Cayman(?: Islands)?|Eastern Caribbean|East Caribbean|Fiji(?:an)?|"
    r"Guyanese|Hong Kong|Jamaican|Liberian|Namibian|New (?:Taiwan|Zealand)|"
    r"Singapore(?:an)?|Solomon Islands|Surinamese|Taiwan(?:ese)?|"
    r"Trinidad(?: and Tobago)?|Zimbabwean"
)
CURRENCY_NAME = (
    r"(?i:(?:(?:" + REGIONAL + r")[ -](?:dollars?|currency)|British[ -]pounds?|"
    r"pounds?(?: sterling)?|sterling|euros?|yen|yuan|renminbi|"
    r"(?:[a-z]+ )?(?:pesos?|rupees?|rubles?|roubles?|francs?|kronor|kroner|"
    r"kr[oó]na|won|dinars?|ri[ay]als?|dirhams?|ringgit|shekels?|lira|zloty|baht)))"
)
REGIONAL_SYMBOL = r"(?i:(?:AU|CA|CDN|HK|NZ|SG|NT|TW|MX|AR|CL|CO|BR|MEX|CN|FJ|TT|EC|RD) ?|[BRACSJZ])"
CURRENCY_SYMBOL = r"(?:(?:" + REGIONAL_SYMBOL + r"|(?:" + CODE + r") ?)\$|[€£¥￥₹₽₩₪₱₫₦₺₴฿₲₡₵₸])"
FOREIGN = r"(?:" + CURRENCY_NAME + "|" + CODE + "|" + CURRENCY_SYMBOL + ")"
FOREIGN_PREFIX = re.compile(LEFT + FOREIGN + RIGHT + r"(?: ?[:=] ?| ?- ?|[- ]denominated | )\(?$")
FOREIGN_PAREN_PREFIX = re.compile(r"\(" + FOREIGN + r"\) ?$")
REGIONAL_PREFIX = re.compile(LEFT + r"(?i:" + REGIONAL + r")[- ]\(?$")
FOREIGN_SUFFIX = re.compile(
    r"(?: (?:in |denominated in |expressed in )?(?:" + FOREIGN + RIGHT + r")|"
    r"[, ]*?\((?:in )?" + FOREIGN + r"\)|, (?:in )?" + FOREIGN + RIGHT + r"| ?[-/] ?" + FOREIGN + RIGHT + ")"
)
AMOUNT_PREFIX = re.compile(
    NUMBER_LEFT + r"(?P<currency>(?i:US\$|USD)|\$|" + FOREIGN + r") ?"
    r"(?P<number>" + NUMBER + r")(?P<scale>(?i:" + SHORT_SCALE + "| " + LONG_SCALE + "))?"
    + NUMBER_RIGHT
)
AMOUNT_SUFFIX = re.compile(
    NUMBER_LEFT + r"(?P<number>" + NUMBER + r")(?P<scale>(?i: " + LONG_SCALE + r"))? "
    r"(?P<currency>(?i:US dollars|dollars)|" + FOREIGN + ")" + RIGHT
)


def foreign_context(text, start, end):
    """Check labels attached to this amount, without sweeping in neighboring currency clauses."""
    prefix = FOREIGN_PREFIX.search(text, max(0, start - 80), start)
    if prefix is None:
        prefix = FOREIGN_PAREN_PREFIX.search(text, max(0, start - 80), start)
    if prefix is None and text[start] == "$":
        prefix = REGIONAL_PREFIX.search(text, max(0, start - 80), start)
    if prefix is not None:
        # A preceding unmarked foreign number already owns its trailing currency name.
        before = text[max(0, prefix.start() - 100):prefix.start()].rstrip()
        if not re.search(r"\d(?:[.,]\d+)*(?: ?(?:[kKmM]|[mMbB][nN]|thousand|million|billion))?$", before):
            return True
    suffix = FOREIGN_SUFFIX.match(text, end)
    if suffix is None:
        return False
    # In a list, a label followed by another figure belongs to that following amount.
    return not re.match(r" ?(?:\$ ?)?\d", text[suffix.end():])


def integer_amount(number, scale):
    whole, _, decimals = number.replace(",", "").partition(".")
    shift = SCALE[scale.strip().lower()]
    non_dollars = decimals[shift:]
    if non_dollars and any(int(digit) for digit in non_dollars):
        return None
    try:
        return int(whole + decimals[:shift].ljust(shift, "0"))
    except ValueError:
        return None


def amount_parts(text):
    """Return every monetary number span and every unambiguously USD whole-dollar value."""
    monetary = set()
    foreign_numbers = set()
    dollars = []
    for amount in sorted((*AMOUNT_PREFIX.finditer(text), *AMOUNT_SUFFIX.finditer(text)),
                         key=lambda match: (match.start(), -match.end())):
        span = amount.span("number")
        monetary.add(span)
        currency = amount["currency"].lower()
        if (currency not in ("$", "us$", "usd", "us dollars", "dollars")
                or foreign_context(text, amount.start(), amount.end())):
            foreign_numbers.add(span)
            continue
        value = integer_amount(amount["number"], amount["scale"] or "")
        if value is not None:
            dollars.append((value, amount.span(), span))
    # Both patterns can see an amount when a prefix and a suffix are present.
    return monetary, list(dict.fromkeys((value, amount) for value, amount, number in dollars
                                        if number not in foreign_numbers))


class Appendix:
    def __init__(self, domain):
        self.company = company_pattern(domain)

    def analyze(self, text):
        companies = list(self.company.finditer(text))
        if not companies or NEGATING.search(text):
            return {}
        matches = {}
        rules = {field: statements for field, rule in FIELD_RULES.items()
                 if (statements := list(rule.finditer(text)))}
        numeric_rules = {"funding_total", "founded_year", "headcount_range"}
        monetary, dollars = amount_parts(text) if numeric_rules.intersection(rules) else (set(), [])
        numbers = ([match for match in BARE_NUMBER.finditer(text) if match.span() not in monetary]
                   if {"founded_year", "headcount_range"}.intersection(rules) else [])
        for field, statements in rules.items():
            if field == "legal_name":
                values = list(legal_values(text, companies))
            elif field == "hq_city":
                values = list(hq_values(text, statements))
            elif field == "ceo":
                values = list(ceo_values(text, companies, statements))
            elif field == "funding_total":
                values = dollars
            elif field == "founded_year":
                values = [(int(match[0]), match.span()) for match in numbers
                          if len(match[0]) == 4 and match[0].isdecimal() and 1800 <= int(match[0]) <= 2099]
            else:
                values = []
                for match in numbers:
                    digits = match[0].replace(",", "")
                    if not digits.isdecimal():
                        continue
                    # Larger integers always belong to the open-ended bucket.
                    first = next((index for index, digit in enumerate(digits) if int(digit)), len(digits))
                    if first == len(digits):
                        continue
                    count = int(digits[first:first + 6])
                    bucket = next((label for limit, label in HEADCOUNTS if count <= limit), "10001+")
                    values.append((bucket, match.span()))
            if values and len({value for value, _ in values}) == 1:
                matches[field] = (values[0][0], [m.span() for m in companies],
                                  [m.span() for m in statements], [span for _, span in values])
        return matches

    def excerpts(self, text):
        for sentence in prose_sentences(text):
            for field, (value, companies, phrases_, values) in self.analyze(sentence).items():
                if len(sentence) <= 500:
                    yield field, value, sentence
                    continue
                window = self.short_excerpt(sentence, field, value, companies, phrases_, values)
                if window:
                    yield field, value, window

    def short_excerpt(self, sentence, field, value, companies, phrases_, values):
        # Examine only windows containing all three pieces of the assertion. Prefer a
        # contiguous excerpt with room for the surrounding syntactic context.
        for start, _ in sorted(set(companies + phrases_ + values)):
            stop = start + 500
            anchors = [next((span for span in group if start <= span[0] and span[1] <= stop), None)
                       for group in (companies, phrases_, values)]
            if any(anchor is None for anchor in anchors):
                continue
            first, last = min(span[0] for span in anchors), max(span[1] for span in anchors)
            budget = 500 - (last - first)
            left = max(0, first - budget // 2)
            right = min(len(sentence), left + 500)
            if left and sentence[left - 1] != " ":
                left = sentence.find(" ", left, first + 1) + 1 or first
            if right < len(sentence) and sentence[right] != " ":
                right = sentence.rfind(" ", last, right) if " " in sentence[last:right] else last
            for excerpt in (sentence[left:right].strip(), sentence[first:last].strip()):
                if 1 <= len(excerpt) <= 500 and self.claim_supports(excerpt, field, value):
                    return excerpt
        return None

    def claim_supports(self, excerpt, field, value):
        parts = list(sentences(excerpt))
        return len(parts) == 1 and self.analyze(parts[0]).get(field, (None,))[0] == value
