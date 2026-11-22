"""Build snapshots, effective source versions and ordered change events (R42–R56)."""

import json

from candidates import CITATION_KEYS, effective_date, page_metadata, publication_key, ranked, upgrade_fields
from evidence import EXECUTIVE_PHRASES, FIELDS


TITLES = tuple(EXECUTIVE_PHRASES)
GROUPS = (*FIELDS, *TITLES)
ALL_FIELDS = (*FIELDS, "executives")
VALUE_KEYS = ("value", "true_from", "citations")


def empty_fields():
    return {key: {"value": None, "status": "unknown", "citations": [], "candidates": [],
                  "true_from": None, "learned_at": None} for key in ALL_FIELDS}


def new_timeline():
    return {"builds": [], "history": {key: [] for key in ALL_FIELDS}, "first_seen": {}}


def selected(group, items, retrieved_at):
    candidates = [
        {**item, "selected": index == 0, **({"title": group} if group in TITLES else {})}
        for index, item in enumerate(ranked(items))
    ]
    first = candidates[0]
    same = [item for item in candidates if item["value"] == first["value"]]
    return {"value": first["value"], "true_from": first["true_from"], "learned_at": retrieved_at,
            "status": "known" if len(candidates) == len(same) else "contested",
            "citations": [{key: item[key] for key in CITATION_KEYS} for item in same],
            "candidates": candidates}


def resolve(groups, retrieved_at, previous=None):
    fields = empty_fields()
    executives = fields["executives"]
    people, dates = [], []
    for group in GROUPS:
        if not groups.get(group):
            continue
        value = selected(group, groups[group], retrieved_at)
        if group in TITLES:
            people.append({"title": group, "name": value["value"]})
            dates.append(value["true_from"])
            executives["candidates"].extend(value["candidates"])
            executives["citations"].extend(value["citations"])
            if value["status"] == "contested":
                executives["status"] = "contested"
        else:
            fields[group] = value
    if people:
        executives["value"] = people
        executives["true_from"] = max(dates) if all(dates) else None
        executives["learned_at"] = retrieved_at
        if executives["status"] != "contested":
            executives["status"] = "known"
    if previous:
        for field, value in fields.items():
            if value["value"] == previous[field]["value"]:
                value["learned_at"] = previous[field]["learned_at"]
    return fields


def member_choices(field):
    return {candidate["title"]: (candidate["value"], candidate["true_from"])
            for candidate in field["candidates"] if candidate["selected"]}


def is_correction(field, old, new):
    if field == "executives":
        before, after = member_choices(old), member_choices(new)
        differing = [title for title in TITLES
                     if before.get(title, (None,))[0] != after.get(title, (None,))[0]]
        return bool(differing) and all(
            title in before and title in after and before[title][1] and after[title][1]
            and after[title][1] <= before[title][1] for title in differing
        )
    return (old["value"] is not None and new["value"] is not None
            and old["true_from"] and new["true_from"] and new["true_from"] <= old["true_from"])


def record_changes(state, dossier, fields, started_at, first_ready):
    for key in ALL_FIELDS:
        old, new = dossier["fields"][key], fields[key]
        if old["value"] == new["value"]:
            continue
        kind = "initial" if first_ready else "correction" if is_correction(key, old, new) else "change"
        entry = {**{name: new[name] for name in VALUE_KEYS}, "type": kind, "learned_at": started_at}
        dossier["timeline"]["history"][key].append(entry)
        if kind != "initial":
            state["changes"].append({
                "seq": state["next_seq"], "domain": dossier["domain"], "field": key,
                "type": kind, "from": old["value"], "to": new["value"],
                "true_from": new["true_from"], "learned_at": started_at,
            })
            state["next_seq"] += 1


def build_view(timeline, record, groups, dates, previous):
    started_at = record["started_at"]
    stored = {"started_at": started_at, "outcome": record["outcome"], "spent_units": record["spent_units"]}
    if record["outcome"] == "ready":
        versions = {url: {"true_from": day, "groups": {}} for url, day in dates.items()}
        candidates = {}
        for key, entries in groups.items():
            for item in entries:
                url = item["url"]
                version = versions.setdefault(url, {"true_from": effective_date("", item["published_at"]), "groups": {}})
                identity = json.dumps([key, item["value"], url, item["provider"]], ensure_ascii=True, separators=(",", ":"))
                first_seen = timeline["first_seen"].setdefault(identity, started_at)
                candidate = {**{name: item[name] for name in ("value", *CITATION_KEYS, "kind", "published_at")},
                             "retrieved_at": started_at, "learned_at": first_seen, "true_from": version["true_from"]}
                candidates.setdefault(key, []).append(candidate)
                version["groups"].setdefault(key, []).append(candidate)
        stored["fields"] = resolve(candidates, started_at, previous)
        stored["versions"] = versions
    timeline["builds"].append(stored)
    return stored


def finish(state, dossier, record, raw_candidates, dates):
    timeline = dossier["timeline"]
    first_ready = dossier["researched_at"] is None
    snapshot = build_view(timeline, record, raw_candidates, dates, dossier["fields"])
    if snapshot["outcome"] == "ready":
        fields = snapshot["fields"]
        record_changes(state, dossier, fields, record["started_at"], first_ready)
        dossier["fields"] = fields
        dossier["researched_at"] = record["started_at"]


def through(dossier, as_of):
    return [record for record in dossier["timeline"]["builds"] if publication_key(record["started_at"]) <= as_of]


def valid_values(records, day):
    by_url = {}
    for record in records:
        for url, version in record.get("versions", {}).items():
            start = version["true_from"]
            if start is None:
                by_url.pop(url, None)
                continue
            timeline = by_url.setdefault(url, [])
            while timeline and timeline[-1]["true_from"] >= start:
                timeline.pop()
            timeline.append(version)
    groups = {}
    for versions in by_url.values():
        active = next((version for version in reversed(versions) if version["true_from"] <= day), None)
        if active:
            for key, candidates in active["groups"].items():
                groups.setdefault(key, []).extend(candidates)
    return {key: {name: field[name] for name in VALUE_KEYS}
            for key, field in resolve(groups, None).items()}


def legacy_versions(dossier, record, candidates, *, from_stage_one):
    candidate_urls = {item["url"] for group in candidates.values() for item in group}
    dates = {}
    calls = record["calls"]
    if from_stage_one:
        # Extracted bodies usually carry more metadata than their discovery snippets.
        calls = sorted(calls, key=lambda call: call["operation"] != "extract")
    for call in calls:
        if not from_stage_one and not call.get("rendered"):
            continue
        for page in call.get("pages", ()):
            url = page["url"]
            if not url or (from_stage_one and url not in candidate_urls):
                continue
            _, published = page_metadata(dossier["domain"], page, legacy=from_stage_one)
            dated = effective_date(page["text"], published)
            if url not in dates or (from_stage_one and dates[url] is None and dated is not None):
                dates[url] = dated
    return dates


def upgrade(dossier, stage):
    records = dossier["builds"]
    timeline = new_timeline()
    dossier["timeline"] = timeline
    previous = empty_fields()
    stage_one = [record for record in records if stage == 1 or record.get("schema_stage") != 2]
    stage_two = [record for record in records if stage == 2 and record.get("schema_stage") == 2]
    last_old_ready = next((record for record in reversed(stage_one) if record["outcome"] == "ready"), None)
    if last_old_ready:
        synthetic = {**last_old_ready, "spent_units": sum(record["spent_units"] for record in stage_one)}
        imported = upgrade_fields(dossier, last_old_ready)
        groups = {field: data["candidates"] for field, data in imported.items()}
        dates = legacy_versions(dossier, last_old_ready, groups, from_stage_one=True)
        previous = build_view(timeline, synthetic, groups, dates, previous)["fields"]
    else:
        for record in stage_one:
            build_view(timeline, record, {}, {}, previous)
    for record in stage_two:
        groups = record["candidates"] if record["outcome"] == "ready" else {}
        dates = legacy_versions(dossier, record, groups, from_stage_one=False)
        snapshot = build_view(timeline, record, groups, dates, previous)
        previous = snapshot.get("fields", previous)
    dossier["fields"] = previous
    if dossier["researched_at"] is not None:
        for key, value in previous.items():
            if value["value"] is not None:
                # Imported history starts with the last visible selection, even
                # though earlier dated builds remain independently queryable.
                value["learned_at"] = dossier["researched_at"]
                timeline["history"][key].append({
                    **{name: value[name] for name in VALUE_KEYS},
                    "type": "initial", "learned_at": value["learned_at"],
                })
