"""Check Dossier funding evidence against a fixed synthetic mock corpus."""

import argparse
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4


CASES = (
    ("birch", "CAD $12 million", None, None),
    ("ash", "$12 million Canadian dollars", None, None),
    ("hazel", "$12 million CAD", None, None),
    ("rowan", "AUD $12 million", None, None),
    ("alder", "€12 million", None, None),
    ("maple", "CAD $12 million and US$5 million", 5_000_000, "US$5 million"),
    ("willow", "9 million US dollars and $12 million in Canadian dollars", 9_000_000, "9 million US dollars"),
    ("cedar", "$12M", 12_000_000, "$12M"),
    ("spruce", "USD 12 million", 12_000_000, "USD 12 million"),
    ("elm", "12 million dollars", 12_000_000, "12 million dollars"),
    ("pine", "$12.5m", 12_500_000, "$12.5m"),
    ("yew", "$12.50", None, None),
    ("beech", "CAD $12 million", None, None),
)
BODY_LIMIT = 2_097_152


class ProbeFailure(Exception):
    """A bounded, user-facing check failure."""


def fixtures():
    for species, amount, expected, dollar_form in CASES:
        company = f"Audit {species.title()} Labs"
        domain = f"audit-{species}-labs.test"
        url = f"https://{domain}/announcement"
        funding = f"{company} raised {amount}."
        headquarters = f"{company} is headquartered in Oslo."
        research_only = species == "beech"
        page = {
            "url": url, "kind": "own", "epochs": [0], "searchable": not research_only,
            "title": f"{company} funding announcement", "lineage": {"registrant": domain},
            "text": f"{funding}\n{headquarters}",
        }
        document = {"domain": domain, "names": [company], "pages": [page]}
        if research_only:
            document["research"] = {"nimble": {"0": [
                {"field": "funding_total", "value": 12_000_000, "url": url, "excerpt": funding},
                {"field": "hq_city", "value": "Oslo", "url": url, "excerpt": headquarters},
            ]}}
        case = {"domain": domain, "url": url, "funding": funding, "expected": expected,
                "headquarters": headquarters, "dollar_form": dollar_form, "research_only": research_only}
        yield case, document


def request(origin, method, path, status, *, body=None, headers=None):
    url = urlsplit(origin)
    connection = HTTPConnection(url.hostname, url.port, timeout=5)
    headers = {"Content-Type": "application/json", **(headers or {})}
    try:
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        if response.status != status:
            raise ProbeFailure(f"{method} {path} returned {response.status}, expected {status}")
        payload = response.read(BODY_LIMIT + 1)
    finally:
        connection.close()
    if len(payload) > BODY_LIMIT:
        raise ProbeFailure(f"{method} {path} returned an oversized response")
    return json.loads(payload) if payload else None


def wait_for_health(origin, path):
    expires = time.monotonic() + 60
    while time.monotonic() < expires:
        try:
            if request(origin, "GET", path, 200) == {"status": "ok"}:
                return
        except (OSError, HTTPException, ValueError, ProbeFailure):
            pass
        time.sleep(0.35)
    raise ProbeFailure(f"{path} did not respond with healthy status within 60 seconds")


def dossier_for(origin, auth, domain):
    request(origin, "POST", "/dossiers", 202, body={"domain": domain},
            headers={**auth, "Idempotency-Key": uuid4().hex})
    expires = time.monotonic() + 35
    while time.monotonic() < expires:
        dossier = request(origin, "GET", f"/dossiers/{domain}", 200, headers=auth)
        if dossier["state"] == "ready" and dossier["domain"] == domain:
            return dossier
        if dossier["state"] != "building":
            raise ProbeFailure(f"{domain} returned an unexpected dossier state or domain")
        time.sleep(0.35)
    raise ProbeFailure(f"{domain} did not yield a ready dossier within 35 seconds")


def funding_problem(field, case):
    expected = case["expected"]
    value = field["value"]
    status = field["status"]
    citations = field["citations"]
    candidates = field.get("candidates", [])
    if expected is None:
        if status != "unknown" or value is not None or citations != [] or candidates != []:
            return "Unsupported amount must stay unknown, with no citations or candidates"
        return None
    if status != "known" or type(value) is not int or value != expected:
        return f"Expected a known USD whole-dollar amount of {expected}"
    if not citations or any(
        citation["url"] != case["url"] or not 1 <= len(citation["excerpt"]) <= 500
        or citation["excerpt"] not in case["funding"] or case["dollar_form"] not in citation["excerpt"]
        for citation in citations
    ):
        return "Citation does not reproduce the supported USD amount from the fixture page"
    if any(candidate["value"] != expected for candidate in candidates):
        return "An unsupported alternate candidate survived"
    return None


def page_was_used(field, case):
    return field["value"] == "Oslo" and field["status"] == "known" and any(
        cite["url"] == case["url"] and cite["excerpt"] and cite["excerpt"] in case["headquarters"]
        for cite in field["citations"]
    )


def research_was_used(mock, auth, case):
    if not auth:
        return None
    log = request(mock, "GET", "/_mock/log", 200, headers=auth)["calls"]
    return any(
        call.get("method") == "research" and call.get("provider") == "nimble"
        and 200 <= call["status"] < 300
        and any(item["url"] == case["url"] and item["text"] == case["funding"]
                for item in call["served"])
        for call in log
    )


def verify_cases(base, mock, report):
    token = os.environ.get("MOCK_ADMIN_TOKEN")
    mock_auth = {"X-Mock-Admin": token} if token else {}
    wait_for_health(mock, "/_mock/health")
    wait_for_health(base, "/health")
    if mock_auth:
        request(mock, "POST", "/_mock/reset", 204, body={"epoch": 0}, headers=mock_auth)
    account = request(base, "POST", "/auth/signup", 201, body={
        "email": f"audit-{uuid4().hex}@example.test", "password": uuid4().hex,
        "display_name": "Offline Currency Audit",
    })
    auth = {"Authorization": f"Bearer {account['token']}"}
    for case, _ in fixtures():
        outcome = {"domain": case["domain"], "fixture_amount": case["funding"],
                   "expected_usd": case["expected"], "passed": False}
        if case["research_only"]:
            outcome["research_exercised"] = None
        try:
            fields = dossier_for(base, auth, case["domain"])["fields"]
            problem = funding_problem(fields["funding_total"], case)
            saw_company = page_was_used(fields["hq_city"], case)
            if case["research_only"]:
                reached = research_was_used(mock, mock_auth, case)
                outcome["research_exercised"] = reached and saw_company
            elif not saw_company and problem is None:
                problem = "The independent headquarters citation was missing, so page coverage was not proven"
            if problem:
                outcome["failure"] = problem
            else:
                outcome["passed"] = True
        except ProbeFailure as error:
            outcome["failure"] = str(error)
        except (OSError, HTTPException, KeyError, TypeError, ValueError) as error:
            outcome["failure"] = f"Unable to verify the fixture ({type(error).__name__})"
        report["cases"].append(outcome)


def http_origin(value):
    parts = urlsplit(value)
    if (parts.scheme != "http" or not parts.hostname or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment):
        raise argparse.ArgumentTypeError("Use the isolated service's HTTP origin")
    return f"http://{parts.netloc}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="operation", required=True)
    corpus = modes.add_parser("corpus")
    corpus.add_argument("--output", type=Path, required=True)
    check = modes.add_parser("check")
    check.add_argument("--base-url", type=http_origin, required=True)
    check.add_argument("--mock-url", type=http_origin, required=True)
    check.add_argument("--output", type=Path, required=True)
    check.add_argument("--revision", required=True)
    args = parser.parse_args()
    if args.operation == "corpus":
        args.output.mkdir(parents=True, exist_ok=True)
        for case, document in fixtures():
            (args.output / f"{case['domain']}.json").write_text(json.dumps(document), encoding="utf-8")
        return 0
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("Use a full lowercase Git revision")

    args.output.mkdir(parents=True, exist_ok=True)
    report = {"revision": args.revision, "state": "error", "passed": False, "cases": []}
    try:
        verify_cases(args.base_url, args.mock_url, report)
        report["state"] = "completed"
        report["passed"] = len(report["cases"]) == len(CASES) and all(row["passed"] for row in report["cases"])
    except ProbeFailure as error:
        report["error"] = str(error)
    except (OSError, HTTPException, KeyError, TypeError, ValueError) as error:
        report["error"] = f"The currency fixture could not be prepared ({type(error).__name__})"
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Funding currency checks passed {sum(row['passed'] for row in report['cases'])}/{len(CASES)} fixtures.")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
