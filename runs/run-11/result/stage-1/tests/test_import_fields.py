import copy
import unittest

from app import Error, fresh, validate_data
from evidence import empty_fields


class ImportFieldTests(unittest.TestCase):
    def setUp(self):
        self.record = {"status": "known", "value": "North Shore LLC", "citations": [{
            "provider": "nimble", "url": "https://north-shore.example/legal",
            "excerpt": "North Shore is registered as North Shore LLC."}]}

    def validate(self, record):
        domain = "north-shore.example"
        when = "2026-01-01T01:02:03Z"
        fields = empty_fields()
        fields["legal_name"] = record
        state = fresh()
        state["dossiers"][domain] = dict(domain=domain, dossier_id="d1", state="ready", fields=fields,
                                          spent_units=1, researched_at=when)
        state["history"][domain] = [dict(at=when, calls=[dict(method="search", argument=domain, units=1, cost=1)],
                                        pages=[dict(provider="nimble", url="https://north-shore.example/legal",
                                                    text="North Shore is registered as North Shore LLC.")])]
        validate_data(state)

    def test_complete_supported_field(self):
        self.validate(self.record)

    def test_invalid_type_and_incomplete_citations(self):
        for key in ("value", "provider", "url", "excerpt"):
            with self.subTest(key=key):
                record = copy.deepcopy(self.record)
                if key == "value":
                    record[key] = 123
                else:
                    del record["citations"][0][key]
                with self.assertRaises(Error):
                    self.validate(record)

    def test_valid_shape_with_contradictory_excerpt(self):
        self.record["value"] = "North Shore AG"
        with self.assertRaises(Error):
            self.validate(self.record)


if __name__ == "__main__":
    unittest.main()
