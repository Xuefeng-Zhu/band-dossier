"""Append-only selections, page versions, and temporal reads."""

import re
from bisect import bisect_right
from datetime import date, timezone

from evidence import (
    FIELDS, empty_fields, executive_field, field_from_candidates, page_headers, parse_timestamp,
    public_url, select_fields,
)


def date_text(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return None


def effective_date(page):
    headers = page_headers(page["text"]) | page.get("headers", {})
    effective = date_text(headers.get("Effective"))
    if effective is not None:
        return effective
    published = parse_timestamp(headers.get("Published"))
    if published is not None:
        try:
            return published.astimezone(timezone.utc).date().isoformat()
        except (ValueError, OverflowError):
            pass
    return None


def blank_fields():
    fields = empty_fields() | {"executives": executive_field([])}
    return {name: item | {"true_from": None, "learned_at": None} for name, item in fields.items()}


def chosen_by_title(item):
    return {candidate["title"]: candidate for candidate in item["candidates"] if candidate["selected"]}


def display_field(field, candidates):
    result = executive_field(candidates) if field == "executives" else field_from_candidates(candidates)
    dates = [candidate["true_from"] for candidate in result["candidates"] if candidate["selected"]]
    result["true_from"] = max(dates) if dates and all(value is not None for value in dates) else None
    return result


def key_of(field, candidate):
    return field, candidate.get("title"), candidate["value"], candidate["url"], candidate["provider"]


def first_seen(timeline):
    seen = {}
    for build in timeline:
        for field, item in (build["fields"] or {}).items():
            for candidate in item["candidates"]:
                seen.setdefault(key_of(field, candidate), candidate["learned_at"])
    return seen


def annotate(fields, previous, seen, dates, when):
    result = {}
    for field in FIELDS:
        plain = fields.get(field, {"candidates": []})
        candidates = [
            candidate | {
                "learned_at": seen.setdefault(key_of(field, candidate), when),
                "true_from": dates.get(candidate["url"]),
            }
            for candidate in plain["candidates"]
        ]
        item = display_field(field, candidates)
        if item["value"] is None:
            learned = None
        elif previous[field]["value"] == item["value"]:
            learned = previous[field]["learned_at"]
        else:
            learned = when
        result[field] = item | {"learned_at": learned}
    return result


def build_snapshot(build, fields=None, *, previous=None, seen=None, stage_one=False):
    snapshot = {key: build[key] for key in ("id", "started_at", "outcome", "spent_units")}
    snapshot.update(fields=None, versions={})
    if fields is None:
        return snapshot
    candidates = {item["url"] for field in fields.values() for item in field["candidates"]}
    dates = {}
    for page in build["pages"]:
        if not public_url(page["url"]):
            continue
        if (stage_one and page.get("complete") and page["url"] in candidates) or page.get("rendered"):
            dates[page["url"]] = effective_date(page)
    for url in candidates:
        dates.setdefault(url, None)
    snapshot["fields"] = annotate(fields, previous, seen, dates, build["started_at"])
    snapshot["versions"] = dates
    return snapshot


def snapshot_for_build(dossier, build, fields):
    return build_snapshot(build, fields, previous=dossier["fields"], seen=first_seen(dossier["timeline"]))


def history_entry(kind, item, when=None):
    return {
        "type": kind, "value": item["value"], "true_from": item["true_from"],
        "learned_at": item["learned_at"] if when is None else when, "citations": item["citations"],
    }


def date_corrects(old, new):
    return old is not None and new is not None and new <= old


def change_type(field, old, new):
    if field == "executives":
        before, after = chosen_by_title(old), chosen_by_title(new)
        changed = {title for title in before.keys() | after.keys()
                   if before.get(title, {}).get("value") != after.get(title, {}).get("value")}
        if all(title in before and title in after and
               date_corrects(before[title]["true_from"], after[title]["true_from"]) for title in changed):
            return "correction"
    elif old["value"] is not None and new["value"] is not None:
        if date_corrects(old["true_from"], new["true_from"]):
            return "correction"
    return "change"


def updates(dossier, snapshot, sequence):
    history = dossier["history"].copy()
    changes = []
    initial = dossier["researched_at"] is None
    for field in FIELDS:
        previous, now = dossier["fields"][field], snapshot["fields"][field]
        if previous["value"] == now["value"]:
            continue
        kind = "initial" if initial else change_type(field, previous, now)
        entry = history_entry(kind, now, snapshot["started_at"])
        history[field] = history[field] + [entry]
        if not initial:
            changes.append({
                "seq": sequence + len(changes), "domain": dossier["domain"], "field": field,
                "type": kind, "from": previous["value"], "to": now["value"],
                "true_from": entry["true_from"], "learned_at": entry["learned_at"],
            })
    return history, changes


def qualifying_builds(timeline, as_of):
    return [build for build in timeline if parse_timestamp(build["started_at"]) <= as_of]


def selected_snapshot(builds):
    return next((build for build in reversed(builds) if build["outcome"] == "ready"), None)


def effective_fields(builds, true_at):
    versions = {}
    for build in builds:
        if build["fields"] is None:
            continue
        for url, date_from in build["versions"].items():
            if date_from is None:
                versions.pop(url, None)
                continue
            current = versions.setdefault(url, [])
            while current and current[-1][0] >= date_from:
                current.pop()
            current.append((date_from, build))

    eligible = {}
    for url, intervals in versions.items():
        index = bisect_right(intervals, true_at, key=lambda item: item[0])
        if index:
            eligible[url] = intervals[index - 1][1]
    candidates = {field: [] for field in FIELDS}
    # Each page can contribute only the candidates its selected version gathered.
    for build in builds:
        if build["fields"] is None:
            continue
        for field, item in build["fields"].items():
            candidates[field].extend(entry for entry in item["candidates"] if eligible.get(entry["url"]) is build)
    fields = {field: display_field(field, items) for field, items in candidates.items()}
    return {field: {key: fields[field][key] for key in ("value", "true_from", "citations")}
            for field in FIELDS}


def is_stage_one(build):
    if any("rendered" in page for page in build["pages"]):
        return False
    return any(call["operation"] == "search" and call["argument"].get("depth") == "deep" or
               call["operation"] == "extract" and not call["argument"].get("render")
               for call in build["calls"]) or bool(build["pages"])


def collapsed_stage_one(builds):
    if not builds:
        return []
    ready = next((build for build in reversed(builds) if build["outcome"] == "ready"), None)
    chosen = ready or builds[-1]
    return [chosen | {"spent_units": sum(build["spent_units"] for build in builds)}]


def migrate_dossier(dossier, *, stage_one):
    raw = dossier["builds"]
    if stage_one:
        legacy, modern = raw, []
    else:
        boundary = next((index for index, build in enumerate(raw) if not is_stage_one(build)), len(raw))
        legacy, modern = raw[:boundary], raw[boundary:]
    timeline = []
    fields = blank_fields()
    seen = {}
    grouped = [(build, True) for build in collapsed_stage_one(legacy)]
    grouped.extend((build, False) for build in modern)
    for build, legacy_build in grouped:
        plain = None
        if build["outcome"] == "ready":
            plain = select_fields(dossier["domain"], build["pages"], build["started_at"], build["claims"],
                                  imported=legacy_build)
        snap = build_snapshot(build, plain, previous=fields, seen=seen, stage_one=legacy_build)
        if plain is not None:
            fields = snap["fields"]
        timeline.append(snap)
    when = dossier["researched_at"]
    if when is not None:
        # An upgrade seeds one public history entry for the value it imported.
        fields = {key: item | {"learned_at": when if item["value"] is not None else None}
                  for key, item in fields.items()}
        latest = selected_snapshot(timeline)
        latest["fields"] = fields
    history = {field: [history_entry("initial", item)] if item["value"] is not None else []
               for field, item in fields.items()}
    return dossier | {"timeline": timeline, "history": history, "fields": fields}
