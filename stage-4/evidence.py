"""Appendix A support and citation selection."""

import re
from datetime import datetime
from decimal import Decimal, localcontext
from functools import lru_cache
from urllib.parse import urlsplit

from lineage import metadata as lineage_metadata, origin as resolve_origin, url_host
from visible import visible_text


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
EXECUTIVE_PHRASES = {
    "cfo": ("chief financial officer", "CFO"),
    "coo": ("chief operating officer", "COO"),
    "cto": ("chief technology officer", "CTO"),
}
FIELDS = (*PHRASES, "executives", "investors")
INVESTOR_PHRASES = ("investor", "investors", "led by", "backed by", "participated")
INVESTOR_ENDINGS = {"Ventures", "Capital", "Partners", "Fund", "Investments", "Holdings", "Equity"}
NEGATIONS = (
    "in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to",
    "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured", "former",
    "formerly", "will become", "not",
)
SUFFIXES = (
    "Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC",
    "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.",
    "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.",
)
RANGES = (
    (10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
    (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000"),
)
REDACTED = "[credential removed]"
AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2, None: 2}
PROVIDERS = ("nimble", "tavily", "kernel", "browserbase")
RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)

ALNUM = r"[^\W_]"
LETTER = r"[^\W\d_]"
WORD = re.compile(LETTER + "+")
HEADER = re.compile(r"^[A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)*:")
SENTENCE_END = re.compile(r"""[.!?]["”’)]*(?=\s)""")
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
NUMBER_TOKEN = re.compile(
    rf"(?<!{ALNUM})(?<![0-9][,.]){NUMBER}(?!{ALNUM}|[,.][0-9])"
)
LONG_SCALE = r"thousand|million|billion"
SCALES = {
    "": 1, "k": 1000, "thousand": 1000, "m": 1000000, "mn": 1000000,
    "million": 1000000, "bn": 1000000000, "billion": 1000000000,
}
AMOUNT = re.compile(
    rf"(?<!{ALNUM})(?<![0-9][,.])(?:"
    rf"(?P<prefix>US\$|USD|\$) ?(?P<first>{NUMBER})(?P<first_scale>mn|bn|k|m| (?:{LONG_SCALE}))?"
    rf"|(?P<second>{NUMBER})(?P<second_scale> (?:{LONG_SCALE}))? (?P<suffix>US dollars|dollars)"
    rf")(?!{ALNUM}|[,.][0-9])", re.I,
)

CURRENCY_CODES = (
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD "
    "BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB "
    "EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK "
    "JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA "
    "MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK "
    "PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN "
    "SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX UYU UZS VES VND VUV WST XAF "
    "XCD XOF XPF YER ZAR ZMW ZWG CNH RMB"
).split()
LOCAL_DOLLAR = (
    r"(?:Canadian|Australian|New Zealand|Hong Kong|Singapore(?:an)?|Taiwan(?:ese)?|"
    r"(?:New )?Taiwan(?:ese)?|Mexican|Fijian|Jamaican|Bahamian|Barbadian|Belize|"
    r"Brunei|Bermudian|Guyanese|Liberian|Namibian|Zimbabwean|Cayman(?: Islands)?|"
    r"East Caribbean|Solomon Islands|Surinamese|Trinidad(?: and Tobago)?)"
)
AMBIGUOUS_CODES = {"ALL", "BAM", "BOB", "COP", "CUP", "GEL", "MAD", "PEN", "SOS", "TOP", "TRY"}
FOREIGN_CODE = "|".join(code for code in CURRENCY_CODES if code not in AMBIGUOUS_CODES)
FOREIGN_CODE += "|(?-i:" + "|".join(sorted(AMBIGUOUS_CODES)) + ")"
REGION_CODES = r"CA|AU|NZ|HK|SG|NT|MX|CN|JP"
# Single letters qualify a currency only as part of a symbol, such as A$.
REGIONAL_SYMBOL = rf"(?:{REGION_CODES}|[CASR])\$"
FOREIGN_NAME = (
    rf"{LOCAL_DOLLAR}(?: dollars?)?|euros?|(?:British )?pounds?(?: sterling)?|"
    r"(?:Japanese )?yen|(?:Chinese )?yuan|renminbi|(?:Swiss )?francs?|"
    r"(?:Indian )?rupees?|(?:South Korean )?won|pesos?|reais|(?:Russian )?rubl(?:e|es)|"
    r"kron(?:a|or|e|er)|dirhams?|riyals?|lira|rand|baht|ringgit|dong|naira"
)
BEFORE_CURRENCY = re.compile(
    rf"(?:(?<!{ALNUM})(?:{FOREIGN_CODE}|{FOREIGN_NAME}|{REGION_CODES}|{REGIONAL_SYMBOL})"
    rf" *(?:[:(] *)?|[€£¥₹₽₩])$", re.I,
)
AFTER_CURRENCY = re.compile(
    rf"^ *(?P<separator>[-,:] *|\( *|(?:in|denominated in) +)?"
    rf"(?P<label>{REGIONAL_SYMBOL}|{FOREIGN_CODE}|{FOREIGN_NAME}|"
    rf"[€£¥₹₽₩])(?!{ALNUM})", re.I,
)
NEXT_AMOUNT = re.compile(rf"^ *(?:[€£¥₹₽₩$]|{NUMBER}|US\$|USD\b)", re.I)


@lru_cache(maxsize=512)
def words(phrases, flags=re.I):
    alternatives = "|".join(re.escape(item) for item in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<!{ALNUM})(?:{alternatives})(?!{ALNUM})", flags)


@lru_cache(maxsize=512)
def identity(domain):
    return words((domain, domain.split(".")[0].replace("-", " ")))


SUFFIX = words(SUFFIXES, 0)
PERIOD_SUFFIX = words(tuple(item for item in SUFFIXES if item.endswith(".")), 0)


def prose(text):
    lines = text.splitlines()
    if lines and HEADER.match(lines[0]):
        for index, line in enumerate(lines[1:], 1):
            if not line.strip():
                return lines[index + 1:]
        return []
    return lines


def page_headers(text):
    headers = {}
    for line in text.splitlines():
        if not HEADER.match(line):
            break
        name, value = line.split(":", 1)
        headers[name] = value.strip()
    return headers


def parse_timestamp(value):
    if isinstance(value, str) and RFC3339.fullmatch(value):
        try:
            return datetime.fromisoformat(value.upper())
        except ValueError:
            pass
    return None


def sentences(line):
    protected = {match.end() - 1 for match in PERIOD_SUFFIX.finditer(line)}
    start = 0
    for match in SENTENCE_END.finditer(line):
        if match.start() not in protected:
            if sentence := line[start:match.end()].strip():
                yield sentence
            start = match.end()
    if sentence := line[start:].strip():
        yield sentence


def capitalized(word):
    return len(word) >= 2 and word[0].isupper() and all(char.islower() for char in word[1:])


def name_word(word):
    return capitalized(word) or len(word) >= 2 and all(char.isupper() for char in word)


def word_at(sentence, start, accept):
    match = WORD.match(sentence, start)
    if match and (match.end() == len(sentence) or not sentence[match.end()].isalnum()):
        if accept(match[0]):
            return match
    return None


def legal_names(sentence, company):
    for anchor in company.finditer(sentence):
        end = anchor.end()
        while end < len(sentence):
            separator = end + (sentence[end] == ",")
            if separator >= len(sentence) or sentence[separator] != " ":
                break
            if match := SUFFIX.match(sentence, separator + 1):
                # Some multiword suffixes share a prefix with other legal forms.
                yield sentence[anchor.start():match.end()]
                break
            if separator != end or not (word := word_at(sentence, end + 1, name_word)):
                break
            end = word.end()


def cities(sentence, phrases):
    for phrase in phrases.finditer(sentence):
        start = phrase.end() + 1
        if sentence[phrase.end():start] != " ":
            continue
        end = start
        while word := word_at(sentence, end, capitalized):
            end = word.end()
            if sentence[end:end + 1] not in (" ", "-"):
                break
            if not word_at(sentence, end + 1, capitalized):
                break
            end += 1
        if end > start:
            yield sentence[start:end]


def capital_runs(sentence):
    run = []
    last_end = -1
    for word in WORD.finditer(sentence):
        standalone = (
            (word.start() == 0 or not sentence[word.start() - 1].isalnum())
            and (word.end() == len(sentence) or not sentence[word.end()].isalnum())
        )
        if not standalone or not capitalized(word[0]) or sentence[last_end:word.start()] != " ":
            if run:
                yield run
            run = []
        if standalone and capitalized(word[0]):
            run.append(word[0])
        last_end = word.end()
    if run:
        yield run


def persons(sentence, domain, phrases):
    sentence = phrases.sub("|", identity(domain).sub("|", sentence))
    for run in capital_runs(sentence):
        if 2 <= len(run) <= 3:
            yield " ".join(run)


def investor_names(sentence, domain, amounts):
    name_removed = identity(domain).sub("|", sentence)
    names = words(INVESTOR_PHRASES).sub("|", name_removed)
    for run in capital_runs(names):
        if len(run) >= 2 and run[-1] in INVESTOR_ENDINGS:
            yield " ".join(run)
    if not amounts:
        return
    for mark in words(("led by", "backed by")).finditer(name_removed):
        start = mark.end() + 1
        if name_removed[mark.end():start] != " ":
            continue
        end = start
        while word := word_at(name_removed, end, capitalized):
            end = word.end()
            if name_removed[end:end + 1] != " " or not word_at(name_removed, end + 1, capitalized):
                break
            end += 1
        if end > start:
            yield name_removed[start:end]


def foreign_amount(text, match):
    prefix = match["prefix"]
    if (prefix == "$" or match["suffix"] and match["suffix"].lower() == "dollars"):
        if BEFORE_CURRENCY.search(text[:match.start()]):
            return True
    following = text[match.end():]
    label = AFTER_CURRENCY.match(following)
    if not label:
        return False
    # A label introducing a second amount belongs to that amount.
    if NEXT_AMOUNT.match(following[label.end():]) and not (label["separator"] or "").endswith("in "):
        return False
    return True


def usd_amounts(sentence):
    for match in AMOUNT.finditer(sentence):
        if foreign_amount(sentence, match):
            continue
        number = (match["first"] or match["second"]).replace(",", "")
        scale = (match["first_scale"] or match["second_scale"] or "").strip().lower()
        with localcontext() as context:
            context.prec = max(28, len(number) + 10)
            amount = Decimal(number) * SCALES[scale]
            value = int(amount) if amount == amount.to_integral_value() else None
        yield match.span(), value


def number_values(sentence, amounts, field):
    for match in NUMBER_TOKEN.finditer(sentence):
        if any(start <= match.start() < end for start, end in amounts):
            continue
        raw = match[0]
        if field == "founded_year":
            if len(raw) == 4 and raw.isascii() and raw.isdigit() and 1800 <= int(raw) <= 2099:
                yield int(raw)
        elif "." not in raw:
            number = int(raw.replace(",", ""))
            if number > 0:
                yield next((label for limit, label in RANGES if number <= limit), "10001+")


def supported_values(excerpt, domain, *, executives=False, investors=False):
    company = identity(domain)
    if not company.search(excerpt) or words(NEGATIONS).search(excerpt):
        return {}
    result = {}
    amounts = list(usd_amounts(excerpt))
    formats = PHRASES | EXECUTIVE_PHRASES if executives else PHRASES
    for field, phrases in formats.items():
        phrase = words(phrases)
        if not phrase.search(excerpt):
            continue
        if field == "legal_name":
            values = legal_names(excerpt, company)
        elif field == "hq_city":
            values = cities(excerpt, phrase)
        elif field == "ceo" or field in EXECUTIVE_PHRASES:
            values = persons(excerpt, domain, phrase)
        elif field == "funding_total":
            values = (value for _, value in amounts if value is not None)
        else:
            values = number_values(excerpt, [span for span, _ in amounts], field)
        distinct = set(values)
        if len(distinct) == 1:
            result[field] = distinct.pop()
    if investors and words(INVESTOR_PHRASES).search(excerpt):
        names = sorted(set(investor_names(excerpt, domain, amounts)))
        if names:
            result["investors"] = names
    return result


def excerpt_text(text, rendered=False):
    lines = prose(text)
    if rendered:
        lines = visible_text(lines).splitlines()
    for line in lines:
        for sentence in sentences(" ".join(line.split())):
            if len(sentence) <= 500 and REDACTED not in sentence:
                yield sentence


def public_url(value):
    if not isinstance(value, str) or REDACTED in value:
        return False
    try:
        address = urlsplit(value)
        return (address.scheme in ("http", "https") and bool(address.hostname)
                and address.username is None and address.password is None)
    except ValueError:
        return False


def empty_fields():
    return {
        field: {"value": None, "status": "unknown", "citations": [], "candidates": []}
        for field in PHRASES
    }


def candidate_score(domain, page, excerpt, field):
    # Prefer a company-owned or explicitly attributed source when Appendix A
    # also admits a same-name source. Keep all observations in the build record.
    host = urlsplit(page["url"]).hostname or ""
    headers = page.get("headers", {})
    registered = headers.get("Registrant", "").strip().lower()
    on_domain = host == domain or host.endswith("." + domain)
    explicit = bool(words((domain,)).search(excerpt))
    score = 4 * on_domain + 4 * (registered == domain) + 4 * explicit
    label = domain.split(".")[0]
    if any(origin != domain and origin.split(".")[0] == label for origin in (registered, host)):
        score -= 12
    if field == "funding_total":
        cumulative = words(("total", "cumulative", "to date", "across rounds", "overall")).search(excerpt)
        if cumulative:
            score += 8
        if words(("equity",)).search(excerpt):
            score += 4
        if words(("debt", "loan", "credit facility")).search(excerpt):
            score -= 8
        elif not cumulative and words(("round", "series")).search(excerpt):
            score -= 4
    return score


def candidate_rank(candidate):
    published = parse_timestamp(candidate["published_at"])
    recency = 0
    if published is not None:
        seconds = 86400 * published.toordinal() + 3600 * published.hour + 60 * published.minute + published.second
        recency = -(seconds * 1000000 + published.microsecond
                    - published.utcoffset() // datetime.resolution)
    return (
        AUTHORITY[candidate["kind"]], published is None, recency, candidate["url"],
        PROVIDERS.index(candidate["provider"]), candidate["value"],
    )


def field_from_candidates(candidates):
    if not candidates:
        return {"value": None, "status": "unknown", "citations": [], "candidates": []}
    ranked = sorted(candidates, key=candidate_rank)
    value = ranked[0]["value"]
    citations = [
        {key: item[key] for key in ("url", "excerpt", "provider")}
        for item in ranked if item["value"] == value
    ]
    return {
        "value": value, "status": "known" if len(citations) == len(ranked) else "contested",
        "citations": citations, "candidates": [
            item | {"selected": index == 0} for index, item in enumerate(ranked)
        ],
    }


def executive_field(candidates):
    members, citations, ranked = [], [], []
    contested = False
    for title in EXECUTIVE_PHRASES:
        item = field_from_candidates([candidate for candidate in candidates if candidate["title"] == title])
        if item["value"] is not None:
            members.append({"title": title, "name": item["value"]})
            citations.extend(item["citations"])
            ranked.extend(item["candidates"])
            contested |= item["status"] == "contested"
    return {
        "value": members or None, "status": ("contested" if contested else "known") if members else "unknown",
        "citations": citations, "candidates": ranked,
    }


def investor_field(candidates):
    ranked = sorted(candidates, key=candidate_rank)
    by_name = {}
    for item in ranked:
        by_name.setdefault(item["value"], []).append(item)
    members = [
        name for name, entries in sorted(by_name.items())
        if any(entry["kind"] in ("own", "filing") for entry in entries)
        or len({entry["origin"] for entry in entries}) >= 2
    ]
    return {
        "value": members or None, "status": "known" if members else "unknown",
        "citations": [{key: entry[key] for key in ("url", "excerpt", "provider")}
                      for name in members for entry in by_name[name]],
        "candidates": [entry | {"selected": entry["value"] in members} for entry in ranked],
    }


def select_fields(domain, pages, retrieved_at, claims=(), *, imported=False, executives=False, lineage=False):
    fields = empty_fields()
    candidates = {field: {} for field in (*fields, *EXECUTIVE_PHRASES, "investors")}
    rendered = {page["url"]: page for page in pages if page.get("rendered") and public_url(page["url"])}

    def add(page, excerpt, field, value):
        headers = page_headers(page.get("text", ""))
        headers.update(page.get("headers") or {})
        kind = headers.get("Kind")
        if kind not in ("own", "filing", "news", "aggregator"):
            host = urlsplit(page["url"]).hostname.lower().removesuffix(".").removeprefix("www.")
            kind = None if imported else ("own" if host == domain else "aggregator")
        if lineage:
            kind = lineage_metadata(page | {"headers": headers}, domain)["kind"]
        published = headers.get("Published")
        item = {
            "value": value, "url": page["url"], "excerpt": excerpt, "provider": page["provider"],
            "kind": kind, "published_at": published if parse_timestamp(published) else None,
            "retrieved_at": retrieved_at, "selected": False,
        }
        if field in EXECUTIVE_PHRASES:
            item["title"] = field
        if lineage:
            item["origin"] = resolve_origin(page["url"], rendered, domain)
        key = page["url"], value
        existing = candidates[field].get(key)
        if existing is None or candidate_rank(item) < candidate_rank(existing):
            candidates[field][key] = item

    for page in pages:
        if not public_url(page["url"]) or page["provider"] not in PROVIDERS:
            continue
        if not (page.get("complete") if imported else page.get("rendered")):
            continue
        for excerpt in excerpt_text(page["text"], rendered=not imported):
            for field, value in supported_values(excerpt, domain, executives=executives, investors=lineage).items():
                if field == "investors":
                    for name in value:
                        add(page, excerpt, field, name)
                else:
                    add(page, excerpt, field, value)

    # Stage 1 accepted attributable provider excerpts even for unsearched
    # pages. New builds gather those pages and apply the visible-text rule.
    if imported:
        for claim in claims:
            field, url, quote = claim.get("field"), claim.get("url"), claim.get("excerpt")
            if field not in fields or not public_url(url) or not isinstance(quote, str):
                continue
            if claim.get("provider") not in PROVIDERS:
                continue
            excerpt = " ".join(quote.split())
            if tuple(excerpt_text(quote)) != (excerpt,):
                continue
            supported = supported_values(excerpt, domain)
            value = claim.get("value")
            if field not in supported or type(value) is not type(supported[field]) or value != supported[field]:
                continue
            existing = [page for page in pages if page["url"] == url and page.get("complete")]
            if not existing:
                add(claim, excerpt, field, value)
    result = {field: field_from_candidates(candidates[field].values()) for field in fields}
    if executives:
        result["executives"] = executive_field([
            candidate for title in EXECUTIVE_PHRASES for candidate in candidates[title].values()
        ])
    if lineage:
        result["investors"] = investor_field(candidates["investors"].values())
    return result
