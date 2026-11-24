import asyncio
import copy
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import server
from evidence import Evidence
from research import Build

DOMAIN = "cedar-trace.test"
URL = "https://cedar-trace.test/profile"
YEAR = "Cedar Trace was founded in 2011."
CITY = "Cedar Trace is headquartered in Lyon."


class ResearchClaimTests(unittest.TestCase):
    def test_confirm_direct_company_wide_statements_over_incidental_numbers(self):
        cases = (
            ("headcount_range", "Cedar Trace employs 980 people.", "Cedar Trace employees use the entrance at 42 Arbor Street.", "501-1000"),
            ("headcount_range", "Cedar Trace has 980 employees worldwide.", "Shop for Cedar Trace employees at https://cedar-trace.test/shop/86262.", "501-1000"),
            ("founded_year", "Cedar Trace was founded in 1983.", "Cedar Trace was incorporated in 1986.", 1983),
            ("funding_total", "Cedar Trace has raised $30 million in total equity funding.", "Cedar Trace raised a total of $5 million for charity.", 30000000),
        )
        for field, direct, incidental, expected in cases:
            with self.subTest(field=field, incidental=incidental):
                evidence = Evidence(DOMAIN)
                evidence.add("nimble", URL, direct, date="2025-01-01")
                evidence.add("nimble", URL, incidental, date="2026-01-01")
                self.assertEqual(evidence.fields[field]["value"], expected)

    def test_initial_labels_in_prose_are_preserved(self):
        for field, value, text in (
            ("ceo", "Etta Navarro", "CEO: Etta Navarro is chief executive of Cedar Trace."),
            ("hq_city", "Basel", "HQ: Cedar Trace is headquartered in Basel."),
        ):
            for claim in (None, (field, value)):
                with self.subTest(field=field, claim=claim):
                    evidence = Evidence(DOMAIN)
                    evidence.add("nimble", URL, text, claim=claim)
                    result = evidence.fields[field]
                    self.assertEqual(result["value"], value)
                    self.assertEqual(result["citations"][0]["excerpt"], text)

    def test_whole_research_citation_must_support_claim(self):
        for excerpt, field, value in (
            (YEAR + " More details follow.", "founded_year", 2011),
            ("Announcement! " + CITY, "hq_city", "Lyon"),
            ('"What changed?" ' + YEAR, "founded_year", 2011),
        ):
            with self.subTest(excerpt=excerpt):
                evidence = Evidence(DOMAIN)
                evidence.add("nimble", URL, excerpt, claim=(field, value))
                self.assertIsNone(evidence.fields[field]["value"])
                evidence.add("nimble", URL, excerpt)
                self.assertEqual(evidence.fields[field]["value"], value)


class SnapshotEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", server.api)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        await self.client.post("/_test/reset", json={"now": "2026-01-02T00:00:00Z"})
        session = await self.client.post("/auth/signup", json={"email": "a@b", "password": "password", "display_name": "A"})
        headers = {"Authorization": "Bearer " + (await session.json())["token"], "Idempotency-Key": "create"}

        async def gather(build):
            build.succeeded = True
            build.ingest("nimble", URL, YEAR + " Cedar Trace employs 120 people.")

        with patch.object(Build, "gather", gather):
            await self.client.post("/dossiers", headers=headers, json={"domain": DOMAIN})
            await asyncio.sleep(0)
        self.snapshot = await (await self.client.get("/_test/export")).json()

    async def test_reject_modified_fields_and_preserve_destination(self):
        for field, value in (("headcount_range", "unrecognized-tier"), ("founded_year", 123),
                             ("headcount_range", "1-10"), ("founded_year", 1999)):
            with self.subTest(field=field, value=value):
                broken = copy.deepcopy(self.snapshot)
                broken["state"]["dossiers"][DOMAIN]["fields"][field]["value"] = value
                response = await self.client.post("/_test/import", json=broken)
                self.assertEqual(response.status, 422)
                self.assertEqual((await response.json())["error"]["code"], "validation_failed")
                self.assertEqual(await (await self.client.get("/_test/export")).json(), self.snapshot)

    async def test_reject_citation_from_another_page(self):
        broken = copy.deepcopy(self.snapshot)
        broken["state"]["dossiers"][DOMAIN]["fields"]["founded_year"]["citations"][0]["url"] += "/other"
        response = await self.client.post("/_test/import", json=broken)
        self.assertEqual(response.status, 422)
