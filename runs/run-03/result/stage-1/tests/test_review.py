import http.client
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import research
import service
from evidence import values


class ReviewRegressions(unittest.TestCase):
    def test_clock_fraction_and_offset_order(self):
        source = "2026-04-01T00:00:00.000000000000000001+02:00"
        same = "2026-03-31T22:00:00.0000000000000000010Z"
        earlier = "2026-03-31T22:00:00.0000000000000000009Z"
        self.assertEqual(service.instant(source), service.instant(same))
        self.assertLess(service.instant(earlier), service.instant(source))

    def test_unsupported_method_returns_json(self):
        with service.Server(("127.0.0.1", 0), service.Handler) as server:
            worker = threading.Thread(target=server.handle_request)
            worker.start()
            connection = http.client.HTTPConnection(*server.server_address, timeout=3)
            try:
                connection.request("EXAMPLE", "/health")
                response = connection.getresponse()
                self.assertTrue(400 <= response.status < 500)
                self.assertEqual(json.loads(response.read())["error"]["code"], "not_found")
            finally:
                connection.close()
                worker.join(3)

    def test_retry_transport_and_stop_after_first_answer(self):
        build = research.Build("sample.test", lambda: True, lambda cost: None)
        answer = SimpleNamespace(results=[])
        outcomes = [ConnectionError("disconnected"), answer]
        with patch.object(research.ROUTER, "search", side_effect=outcomes) as search, patch.object(build, "missing", return_value=[]):
            build.run()
        self.assertEqual([call.args for call in search.call_args_list], [("sample.test",)] * 2)
        self.assertEqual(build.used, 2)

    def test_exact_whole_dollar_arithmetic(self):
        digits = "123456789012345678901234567893"
        for text, expected in [(f"${digits}", int(digits)), (f"${digits}.123456 million", int(digits+"123456")),
                               (f"${digits}.0000001 million", None)]:
            with self.subTest(text=text):
                self.assertEqual(values("maple.test", f"Maple raised {text}.").get("funding_total"), expected)

    def test_founding_and_incorporation_conflict(self):
        build = research.Build("silver-maple.test", lambda: True, lambda cost: None)
        registration = "Silver Maple was incorporated in this region in 2018."
        founding = "Silver Maple was founded in 1997."
        for i in range(3):
            build.add_page(f"https://directory.test/{i}", registration, "full")
        self.assertEqual(build.fields["founded_year"]["value"], 2018)
        build.add_page("https://news.test/history", founding, "full")
        build.add_page("https://silver-maple.test/about", founding, "full")
        year = build.fields["founded_year"]
        self.assertEqual(year["value"], 1997)
        self.assertEqual(len(year["citations"]), 2)
        self.assertTrue(all(c["excerpt"] == founding for c in year["citations"]))
