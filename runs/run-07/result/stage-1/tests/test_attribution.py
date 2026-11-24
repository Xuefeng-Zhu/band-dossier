import unittest

from evidence import Evidence


class Attribution(unittest.TestCase):
    def test_direct_executive_names_outrank_people_or_titles_elsewhere(self):
        cases = [
            ("cloudflare.com", "Cloudflare CEO explains his emotional decision to punt The Daily Stormer.",
             "Cloudflare CEO Matthew Prince addressed shareholders.", "Matthew Prince"),
            ("forest-river.test", "Forest River CEO shares her advice for working with Hal Morse.",
             "Kira Rowan has led Forest River as chief executive since 2021.", "Kira Rowan"),
        ]
        for domain, weak, direct, expected in cases:
            with self.subTest(domain=domain):
                proof = Evidence(domain)
                proof.observe("https://" + domain + "/commentary", "nimble", weak, "2026-04-15")
                proof.observe("https://finance.example/leadership", "nimble", direct)
                self.assertEqual(proof.fields()["ceo"]["value"], expected)

    def test_dated_annual_headcount_beats_undated_estimates(self):
        for headcount, expected in [(5156, "5001-10000"), (600, "501-1000")]:
            proof = Evidence("violet-works.test", 2026)
            proof.observe("https://directory.example/profile", "nimble", "Violet Works has about 400 employees.")
            self.assertIn("headcount_range", proof.missing())
            proof.observe("https://reports.example/filings", "nimble",
                          f"Violet Works reports {headcount} employees worldwide.", "2026-02-01")
            self.assertEqual(proof.fields()["headcount_range"]["value"], expected)

    def test_funding_round_components_do_not_outrank_a_lifetime_total(self):
        proof = Evidence("forest-river.test")
        proof.observe("https://forest-river.test/finance", "nimble",
                      "Forest River has closed on new funding of $11 billion, the initial part of a round.", "2026-09-04")
        proof.observe("https://finance.example/forest", "nimble",
                      "Forest River has raised a total of $52 billion across all rounds.", "2026-09-01")
        self.assertEqual(proof.fields()["funding_total"]["value"], 52_000_000_000)

    def test_confirmed_company_total_outranks_counts_from_when_someone_joined(self):
        for domain, company, n in [("cloudflare.com", "Cloudflare", "5,483"),
                                    ("cedar-lake.test", "Cedar Lake", "8,000")]:
            with self.subTest(domain=domain):
                proof = Evidence(domain, 2026)
                proof.observe("https://" + domain + "/history", "nimble",
                              f"The founder joined {company} when the company had fewer than 30 people.")
                proof.observe("https://markets.example/annual", "nimble",
                              f"{company} had {n} employees as of March 31, 2026.")
                proof.observe("https://industry.example/profile", "nimble",
                              f"{company} has {n} total employees.")
                self.assertEqual(proof.fields()["headcount_range"]["value"], "5001-10000")
