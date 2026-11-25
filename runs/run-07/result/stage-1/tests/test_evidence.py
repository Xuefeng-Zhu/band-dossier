import unittest

from evidence import Evidence


class SupportAndRanking(unittest.TestCase):
    def test_sole_supported_value_survives_every_ranking_signal(self):
        cases = [
            ("lilac-anvil.test", "funding_total", 80_000_000,
             "Lilac Anvil has raised lifetime funding of $80 million and is valued at its highest historical level."),
            ("maple-loom.test", "funding_total", 45_000_000,
             "Maple Loom received a cumulative $45 million in funding and is valued at an all-time high."),
            ("prism-lantern.test", "legal_name", "Prism Lantern LLC",
             "The legal entity the customer contracts with is Prism Lantern LLC."),
            ("silver-basalt.test", "legal_name", "Silver Basalt GmbH",
             "The legal entity you know as Silver Basalt is Silver Basalt GmbH."),
            ("amber-lake.test", "legal_name", "Amber Lake Opco LLC",
             "Amber Lake's registered name is Amber Lake Opco LLC."),
            ("east-harbor.test", "headcount_range", "51-200",
             "East Harbor employs 120 people, including its regional staff."),
            ("cedar-spring.test", "hq_city", "Oslo",
             "Cedar Spring acquired its building and is now based in Oslo."),
            ("ruby-mica.test", "ceo", "Dana Ruiz",
             "After the incumbent resigned, Ruby Mica named Dana Ruiz its CEO."),
            ("garnet-willow.test", "founded_year", 2001,
             "The firm at https://garnet-willow.test was founded in 2001."),
        ]
        url = "https://news.example/profile"
        for domain, field, value, sentence in cases:
            for claim in (None, (field, value)):
                with self.subTest(domain=domain, claim=claim):
                    proof = Evidence(domain)
                    proof.observe(url, "nimble", sentence, claim=claim)
                    self.assertEqual(proof.fields()[field], {
                        "status": "known", "value": value,
                        "citations": [{"url": url, "provider": "nimble", "excerpt": sentence}],
                    })

    def test_conflicting_values_still_use_attribution(self):
        proof = Evidence("ruby-mica.test")
        proof.observe("https://ruby-mica.test/news", "nimble",
                      "Ruby Mica met Dana Ruiz, CEO of Horizon.")
        proof.observe("https://news.example/finance", "nimble",
                      "Ruby Mica CEO: Simon Lane.")
        self.assertEqual(proof.fields()["ceo"]["value"], "Simon Lane")

    def test_negated_or_ambiguous_statements_remain_unknown(self):
        proof = Evidence("ruby-mica.test")
        proof.observe("https://ruby-mica.test/about", "nimble",
                      "Ruby Mica might be based in Oslo. Ruby Mica is based in Oslo and headquartered in Paris.")
        self.assertEqual(proof.fields()["hq_city"]["status"], "unknown")
