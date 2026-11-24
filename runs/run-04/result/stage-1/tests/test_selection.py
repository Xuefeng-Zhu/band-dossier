import unittest

from research import Build


class FieldSelectionTests(unittest.TestCase):
    def test_foundation_evidence_survives_later_local_incorporation(self):
        build = Build("cobalt-systems.test", None)
        build.page("https://registry.example/entry", "nimble",
                   "Cobalt Systems LLC was incorporated in the state in 2021.", True)
        build.page("https://industry.example/cobalt", "nimble",
                   "Cobalt Systems was founded in 2001 and is based in Stuttgart.", True)
        build.page("https://news.example/history", "nimble",
                   "Cobalt Systems was established in 2001.", True)
        self.assertEqual(build.fields["founded_year"]["value"], 2001)

    def test_direct_workforce_count_wins_over_incidental_year(self):
        build = Build("cobalt-systems.test", None)
        build.page("https://cobalt-systems.test/news", "nimble",
                   "In 2010 Cobalt Systems launched a tool to help people with reporting.", True)
        self.assertIn("headcount_range", build.missing)
        build.page("https://industry.example/report", "nimble",
                   "Cobalt Systems employs 530 engineers worldwide.", True)
        entry = build.fields["headcount_range"]
        self.assertEqual(entry["value"], "501-1000")
        self.assertEqual([c["url"] for c in entry["citations"]], ["https://industry.example/report"])

    def test_incidental_quote_is_removed_even_for_same_bin(self):
        build = Build("cobalt-systems.test", None)
        build.page("https://cobalt-systems.test/blog", "nimble",
                   "In 2011 Cobalt Systems shared a guide for people working remotely.", True)
        build.page("https://business.example/cobalt", "nimble",
                   "Cobalt Systems has 2,400 employees.", True)
        self.assertEqual([c["excerpt"] for c in build.fields["headcount_range"]["citations"]],
                         ["Cobalt Systems has 2,400 employees."])

    def test_evidence_linked_to_the_subject_beats_a_namesake(self):
        build = Build("cobalt.test", None)
        build.page("https://wrong.example/leadership", "nimble",
                   "Jane Wood is the CEO of Cobalt.", True)
        build.page("https://news.example/profile", "nimble",
                   "Website: https://cobalt.test\n\nCobalt CEO Dana Ruiz leads the company.", True)
        self.assertEqual(build.fields["ceo"]["value"], "Dana Ruiz")

    def test_an_unrelated_subjects_city_remains_open_for_research(self):
        build = Build("cobalt.test", None)
        build.page("https://holdings.example/history", "nimble",
                   "Based in Denver, United Insurance operated until its acquisition by Cobalt.", True)
        self.assertIn("hq_city", build.missing)
        build.page("https://cobalt.test/contact", "nimble", "Cobalt is headquartered in Lisbon.", True)
        self.assertEqual(build.fields["hq_city"]["value"], "Lisbon")

    def test_percentage_does_not_settle_employee_count(self):
        build = Build("cobalt.test", None)
        build.page("https://cobalt.test/survey", "nimble",
                   "95% of employees at Cobalt say they are satisfied with their tools.", True)
        self.assertIn("headcount_range", build.missing)
        build.page("https://cobalt.test/team", "nimble", "Cobalt has 1,500 full-time employees.", True)
        self.assertEqual(build.fields["headcount_range"]["value"], "1001-5000")

    def test_cumulative_amount_beats_a_single_round(self):
        build = Build("cobalt.test", None)
        build.page("https://cobalt.test/press", "nimble",
                   "Cobalt's largest funding round brought in $15M.", True)
        build.page("https://industry.example/history", "nimble",
                   "Cobalt has raised total funding of $45M.", True)
        self.assertEqual(build.fields["funding_total"]["value"], 45_000_000)

    def test_expanded_entity_name_disambiguates_a_foreign_source(self):
        build = Build("cobalt.test", None)
        build.hints["legal_name"] = "Cobalt Payments LLC"
        build.page("https://trade.example/leadership", "nimble",
                   "Cobalt Aviation Corporation announced its results. Cobalt CEO Dana Reed commented.", True)
        build.page("https://finance.example/people", "nimble",
                   "Cobalt Payments LLC operates across Europe. Cobalt CEO Sara Ortiz commented.", True)
        self.assertEqual(build.fields["ceo"]["value"], "Sara Ortiz")
