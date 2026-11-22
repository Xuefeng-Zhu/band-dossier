"""History, dated page versions, and migration of durable dossier state."""

from datetime import date
import re

from candidates import candidates_from_pages, page_headers, publication_time, select
from evidence import EXECUTIVE_TITLES, FIELDS


ALL_FIELDS = (*FIELDS, "executives")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def valid_date(value):
    if not isinstance(value, str) or DATE.fullmatch(value) is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def effective_date(text):
    headers = page_headers(text)
    if explicit := valid_date(headers.get("Effective")):
        return explicit
    if instant := publication_time(headers.get("Published")):
        ordinal = instant[0] // 86400
        if 1 <= ordinal <= date.max.toordinal():
            return date.fromordinal(ordinal).isoformat()
    return None


def page_versions(pages, legacy):
    eligible = ("search", "citation") if legacy else ("rendered",)
    versions = {}
    for page in sorted(pages, key=lambda page: page["call_id"]):
        if page["scope"] in eligible:
            versions.setdefault(page["url"], effective_date(page["text"]))
    return versions


def executive_selection(candidates):
    names, ordered, citations, dates = [], [], [], []
    contested = False
    for title in EXECUTIVE_TITLES:
        chosen = select([candidate for candidate in candidates if candidate["title"] == title])
        if chosen["value"] is not None:
            names.append({"title": title, "name": chosen["value"]})
            ordered.extend(chosen["candidates"])
            citations.extend(chosen["citations"])
            dates.append(chosen["candidates"][0]["true_from"])
            contested |= chosen["status"] == "contested"
    return {
        "value": names or None,
        "status": ("contested" if contested else "known") if names else "unknown",
        "citations": citations,
        "candidates": ordered,
        "true_from": max(dates) if dates and all(dates) else None,
    }


def choose(field, candidates):
    if field == "executives":
        return executive_selection(candidates)
    chosen = select(candidates)
    chosen["true_from"] = chosen["candidates"][0]["true_from"] if chosen["candidates"] else None
    return chosen


def empty_fields():
    return {field: {**choose(field, ()), "learned_at": None} for field in ALL_FIELDS}


def empty_history():
    return {field: [] for field in ALL_FIELDS}


def candidate_id(field, candidate):
    return (field, candidate.get("title"), candidate["value"], candidate["url"], candidate["provider"])


def timed_fields(raw, versions, started, timeline):
    first_seen = {}
    previous = empty_fields()
    for build in timeline:
        if build["outcome"] != "ready":
            continue
        previous = build["fields"]
        for field, current in previous.items():
            for item in current["candidates"]:
                first_seen.setdefault(candidate_id(field, item), item["learned_at"])
    timed = {}
    for field in ALL_FIELDS:
        if field == "executives":
            candidates = [{**item, "title": title} for title in EXECUTIVE_TITLES
                          for item in raw.get(title, {}).get("candidates", ())]
        else:
            candidates = raw[field]["candidates"]
        enriched = [
            {**item, "true_from": versions.get(item["url"]),
             "learned_at": first_seen.get(candidate_id(field, item), started)}
            for item in candidates
        ]
        selected = choose(field, enriched)
        if selected["value"] is None:
            learned = None
        elif selected["value"] == previous[field]["value"]:
            learned = previous[field]["learned_at"]
        else:
            learned = started
        timed[field] = {**selected, "learned_at": learned}
    return timed


def member_dates(entry):
    return {item["title"]: (item["value"], item["true_from"])
            for item in entry["candidates"] if item["selected"]}


def correction(field, old, new):
    if field != "executives":
        earlier, current = old["true_from"], new["true_from"]
        return bool(old["value"] is not None and new["value"] is not None
                    and earlier and current and current <= earlier)
    earlier, current = member_dates(old), member_dates(new)
    for title in EXECUTIVE_TITLES:
        old_name, old_date = earlier.get(title, (None, None))
        new_name, new_date = current.get(title, (None, None))
        if old_name != new_name and not (old_date and new_date and new_date <= old_date):
            return False
    return True


def record_changes(domain, dossier, fields, started, feed):
    initial = dossier["researched_at"] is None
    for field in ALL_FIELDS:
        old, new = dossier["fields"][field], fields[field]
        if old["value"] == new["value"]:
            continue
        kind = "initial" if initial else ("correction" if correction(field, old, new) else "change")
        item = {"type": kind, "value": new["value"], "citations": new["citations"],
                "true_from": new["true_from"], "learned_at": started}
        dossier["history"][field].append(item)
        if kind != "initial":
            feed.append({"seq": (feed[-1]["seq"] + 1 if feed else 1),
                         "domain": domain, "field": field, "type": kind,
                         "from": old["value"], "to": new["value"], "true_from": new["true_from"],
                         "learned_at": started})


def chronological_row(build, fields=None, versions=None):
    return {key: build[key] for key in ("id", "started_at", "spent_units", "outcome")} | {
        "fields": fields, "versions": versions,
    }


def imported_stage_one(build):
    for call in build["audit"]["calls"]:
        request = call.get("request")
        if call.get("kind") == "search" and isinstance(request, dict) and request.get("depth") == "deep":
            return True
    return False


def migrate_dossier(domain, dossier, stage):
    timeline = []
    builds = dossier["builds"]
    if stage == 1:
        prefix = builds
    else:
        legacy_count = next((i for i, build in enumerate(builds) if not imported_stage_one(build)), len(builds))
        prefix = builds[:legacy_count]
    if prefix:
        ready = next((build for build in reversed(prefix) if build["outcome"] == "ready"), None)
        aggregate = {**(ready or prefix[-1]), "spent_units": sum(build["spent_units"] for build in prefix)}
        if ready:
            audit = ready["audit"]
            raw = candidates_from_pages(
                domain, audit["pages"], ready["started_at"], answers=audit["research_answers"],
                imported=True, previous=dossier["fields"] if stage == 1 else None,
            )
            versions = page_versions(audit["pages"], legacy=True)
            fields = timed_fields(raw, versions, ready["started_at"], timeline)
            timeline.append(chronological_row(aggregate, fields, versions))
        else:
            timeline.append(chronological_row(aggregate))

    for build in builds[len(prefix):]:
        if build["outcome"] == "failed":
            timeline.append(chronological_row(build))
            continue
        audit = build["audit"]
        raw = candidates_from_pages(domain, audit["pages"], build["started_at"],
                                    answers=audit["research_answers"])
        versions = page_versions(audit["pages"], legacy=False)
        fields = timed_fields(raw, versions, build["started_at"], timeline)
        timeline.append(chronological_row(build, fields, versions))

    latest = next((row for row in reversed(timeline) if row["outcome"] == "ready"), None)
    dossier["timeline"] = timeline
    dossier["history"] = empty_history()
    if latest is None:
        dossier["fields"] = empty_fields()
        return

    # Imported history begins with the state at export. Earlier build
    # snapshots still retain the dates learned from that build sequence.
    started = dossier["researched_at"]
    for field, entry in latest["fields"].items():
        if entry["value"] is not None:
            entry["learned_at"] = started
            dossier["history"][field].append({
                "type": "initial", "value": entry["value"], "true_from": entry["true_from"],
                "learned_at": started, "citations": entry["citations"],
            })
    dossier["fields"] = latest["fields"]


def at_or_before(timeline, as_of):
    instant = publication_time(as_of)
    return [build for build in timeline if publication_time(build["started_at"]) <= instant]


def values_at(timeline, true_at):
    by_url = {}
    for build in timeline:
        if build["outcome"] != "ready":
            continue
        for url, effective in build["versions"].items():
            prior = by_url.get(url, ())
            by_url[url] = ([(start, saved) for start, saved in prior if start < effective]
                           + [(effective, build["fields"])]) if effective else []

    at_date = {field: [] for field in ALL_FIELDS}
    for url, versions in by_url.items():
        active = next((fields for start, fields in reversed(versions) if start <= true_at), None)
        if active is None:
            continue
        for field, entry in active.items():
            at_date[field].extend(item for item in entry["candidates"] if item["url"] == url)
    result = {}
    for field, candidates in at_date.items():
        chosen = choose(field, candidates)
        result[field] = {key: chosen[key] for key in ("value", "true_from", "citations")}
    return result
