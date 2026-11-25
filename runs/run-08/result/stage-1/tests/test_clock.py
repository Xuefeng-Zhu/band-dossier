import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import server


class ClockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", server.api)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def test_fractional_order_and_equal_offsets(self):
        cases = [
            ("2026-03-01T09:30:00.123456789123Z", "2026-03-01T09:30:00.123456789122Z",
             "2026-03-01T09:30:00.12345678912300+00:00"),
            ("2026-01-01T00:10:00.00000000000041+01:00", "2025-12-31T18:10:00.0000000000004-05:00",
             "2025-12-31T23:10:00.000000000000410Z"),
        ]
        for initial, earlier, equal in cases:
            with self.subTest(initial=initial):
                reset = await self.client.post("/_test/reset", json={"now": initial})
                self.assertEqual(reset.status, 204)
                move = await self.client.post("/_test/clock", json={"now": earlier})
                self.assertEqual(move.status, 422)
                self.assertEqual((await move.json())["error"]["code"], "validation_failed")
                same = await self.client.post("/_test/clock", json={"now": equal})
                self.assertEqual(same.status, 204)

    async def test_leap_second_order_and_wire_precision(self):
        for before, leap, equal, after in (
            ("1990-12-31T23:59:59.99999999Z", "1990-12-31T23:59:60.1Z",
             "1990-12-31T15:59:60.10-08:00", "1991-01-01T00:00:00Z"),
            ("2017-01-01T05:29:59.999+05:30", "2017-01-01T05:29:60.00000001+05:30",
             "2016-12-31T23:59:60.000000010Z", "2017-01-01T00:00:00Z"),
        ):
            with self.subTest(leap=leap):
                self.assertEqual((await self.client.post("/_test/reset", json={"now": before})).status, 204)
                for stamp, status in ((leap, 204), (before, 422), (equal, 204), (after, 204), (leap, 422)):
                    result = await self.client.post("/_test/clock", json={"now": stamp})
                    self.assertEqual(result.status, status, stamp)

    async def test_unannounced_leap_and_wrong_utc_minute_rejected(self):
        for stamp in ("2024-12-31T23:59:60Z", "2016-12-31T23:58:60Z", "1990-12-31T23:59:60-08:00"):
            with self.subTest(stamp=stamp):
                result = await self.client.post("/_test/reset", json={"now": stamp})
                self.assertEqual(result.status, 422)
