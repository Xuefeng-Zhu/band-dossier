"""Build order is the knowledge axis. Each page's effective date is the validity axis."""
from candidates import current_origins, investor_dates, legacy_book, member_origins, select_field
from lineage import host_of
from evidence import ALL_FIELDS, TITLES, unknown_fields
from timestamps import parse_stamp


def empty_history():
    return {field: [] for field in ALL_FIELDS}


def candidate_key(field, candidate):
    return (field, candidate.get("title"), candidate["value"], candidate["url"], candidate["provider"])


def set_learned(fields, previous, seen, when):
    for field, item in fields.items():
        for candidate in item["candidates"]:
            key = candidate_key(field, candidate)
            candidate["learned_at"] = seen.setdefault(key, candidate["retrieved_at"])
        if item["value"] is not None:
            old = previous[field]
            item["learned_at"] = old["learned_at"] if old["value"] == item["value"] else when


def standing_origins(fields, standing, when):
    for name, item in fields.items():
        old = standing.get(name, {})
        episodes = {}
        for key, sources in member_origins(name, item).items():
            earlier, attained = old.get(key, (set(), None))
            sources = earlier | sources
            if attained is None and len(sources) >= 2:
                attained = when
            episodes[key] = (sources, attained)
        standing[name] = episodes
        dates = [attained for _, attained in episodes.values()]
        item["corroborated_since"] = max(dates, key=parse_stamp) if dates and all(dates) else None


def import_lineage(dossier, records, stage):
    """Old candidate identity, ranking, learning times and citations remain authoritative."""
    blank = unknown_fields()["investors"]
    ready = [r for r in records if "fields" in r]
    for r in ready:
        r["fields"].setdefault("investors", blank.copy())
        for name, item in r["fields"].items():
            for c in item["candidates"]:
                c.setdefault("origin", host_of(c["url"]))
            current_origins(name, item)
        # Pre-Stage 3 imports begin their standing episodes at the imported
        # baseline. Stage 3 retains the episodes of its ready-build stream.
        if stage < 3 and r is not ready[-1]:
            r["before_origin_baseline"] = True
    dossier["fields"] = ready[-1]["fields"] if ready else unknown_fields()


def members(item):
    return {c["title"]: (c["value"], c["true_from"]) for c in item["candidates"] if c["selected"]}


def corrected(old, new):
    return old is not None and new is not None and new <= old


def entry_type(field, old, new, first):
    if first:
        return "initial"
    if field == "investors":
        before, after = set(old["value"] or ()), set(new["value"] or ())
        added = investor_dates(new["candidates"])
        if before <= after and all(corrected(old["true_from"], added[name]) for name in after - before):
            return "correction"
        return "change"
    if field != "executives":
        return "correction" if corrected(old["true_from"], new["true_from"]) else "change"
    before, after = members(old), members(new)
    for title in TITLES:
        if (title in before) != (title in after):
            return "change"
        if title in before and before[title][0] != after[title][0]:
            if not corrected(before[title][1], after[title][1]):
                return "change"
    return "correction"


def add_entries(domain, previous, fields, when, first, history, feed):
    for field in ALL_FIELDS:
        old, new = previous[field], fields[field]
        if old["value"] == new["value"]:
            continue
        kind = entry_type(field, old, new, first)
        history[field].append({"type": kind, "value": new["value"], "learned_at": when,
                               "true_from": new["true_from"], "citations": new["citations"]})
        if kind != "initial":
            feed.append({"seq": len(feed) + 1, "domain": domain, "field": field, "type": kind,
                         "from": old["value"], "to": new["value"], "true_from": new["true_from"], "learned_at": when})


def page_dates(book, fields):
    dates = {url: values[2] for url, values in book.meta.items()}
    for item in fields.values():
        for c in item["candidates"]:
            dates.setdefault(c["url"], c["true_from"])
    return dates


def state_at(builds, cutoff):
    snapshot = None
    last_time = None
    units = 0
    for build in builds:
        when = parse_stamp(build["time"])
        if when <= cutoff:
            units += build["units"]
            if "fields" in build and (last_time is None or when >= last_time):
                snapshot, last_time = build, when
    return snapshot, units


def values_at(builds, cutoff, date):
    # Evaluating at one date avoids materializing full validity intervals. A
    # gathered empty version ends the old one just as a populated version does.
    active = {}
    for build in builds:
        if "fields" not in build or parse_stamp(build["time"]) > cutoff:
            continue
        for url, effective in build["dates"].items():
            if effective is None:
                active.pop(url, None)
            elif effective <= date:
                active[url] = build
    grouped = {field: [] for field in ALL_FIELDS}
    for build in {id(b): b for b in active.values()}.values():
        for field, item in build["fields"].items():
            grouped[field].extend(c for c in item["candidates"] if active.get(c["url"]) is build)
    result = {}
    for field, candidates in grouped.items():
        selected = select_field(field, candidates)
        result[field] = {k: selected[k] for k in ("value", "true_from", "citations")}
    return result


def legacy_success(build):
    return any(call["outcome"] in ("answered", "no_page") for call in build["calls"])


def cost(build):
    return sum(call["units"] for call in build["calls"])


def upgrade(domain, dossier, raw, stage):
    """Collapse legacy Stage 1 history; preserve each native Stage 2 build."""
    builds, seen = [], {}
    previous = unknown_fields()
    prefix = len(raw) if stage == 1 else next((i for i, b in enumerate(raw) if "candidates" not in b), len(raw))
    baseline = next((b for b in reversed(raw[:prefix]) if legacy_success(b)), None)
    if prefix:
        baseline_units = sum(cost(b) for b in raw[:prefix])
        if baseline is None:
            builds.append({"time": raw[prefix-1]["time"], "units": baseline_units})
        else:
            book = legacy_book(domain, baseline, True)
            if stage == 1:
                for field, item in dossier["fields"].items():
                    for c in item["citations"]:
                        book.add(field, item["value"], c["url"], c["provider"], c["excerpt"])
            fields = book.fields()
            set_learned(fields, previous, seen, baseline["time"])
            # Stage 1 imports start with the URLs supporting its imported candidates.
            dates = {c["url"]: c["true_from"] for f in fields.values() for c in f["candidates"]}
            builds.append({"time": baseline["time"], "units": baseline_units, "fields": fields, "dates": dates,
                           "legacy_builds": raw[:prefix]})
            previous = fields
    for old in raw[prefix:]:
        record = {**old, "units": cost(old)}
        if legacy_success(old):
            book = legacy_book(domain, old, False)
            fields = book.fields()
            set_learned(fields, previous, seen, old["time"])
            record.update(fields=fields, dates=page_dates(book, fields))
            previous = fields
        builds.append(record)
    history = empty_history()
    when = dossier["researched_at"]
    if when is not None:
        for item in previous.values():
            if item["value"] is not None:
                item["learned_at"] = when
        add_entries(domain, unknown_fields(), previous, when, True, history, [])
    dossier["fields"] = previous
    return builds, seen, history
