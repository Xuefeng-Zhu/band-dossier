import unittest

from research import Build


class LinkEvidenceTests(unittest.TestCase):
    def test_link_destination_cannot_supply_headcount_phrase(self):
        build = Build("river-clay.example")
        quote = "River Clay was founded in 2001 by [Jordan Ramos](https://archive.example/people/jordan)."
        build.page("nimble", "https://archive.example/company", quote)
        self.assertIsNone(build.fields()["headcount_range"]["value"])
        self.assertEqual(build.fields()["founded_year"]["value"], 2001)

    def test_link_destination_cannot_supply_a_workforce_number(self):
        build = Build("river-clay.example")
        quote = "River Clay employees prefer the [new policy](https://office.example/docs/80000)."
        build.page("nimble", "https://office.example/company", quote)
        self.assertIsNone(build.fields()["headcount_range"]["value"])

    def test_visible_number_in_link_label_retains_verbatim_citation(self):
        build = Build("river-clay.example")
        quote = "River Clay employs [143 people](https://archive.example/page_(staff)/73001)."
        build.page("nimble", "https://archive.example/company", quote)
        field = build.fields()["headcount_range"]
        self.assertEqual(field["value"], "51-200")
        self.assertEqual(field["citations"][0]["excerpt"], quote)

    def test_link_title_punctuation_does_not_create_source_sentences(self):
        build = Build("river-clay.example")
        link = '[award](https://archive.example/record "75130. Read the announcement!")'
        quote = f"River Clay thanks its employees for the {link}."
        build.page("nimble", "https://archive.example/company", quote)
        self.assertIsNone(build.fields()["headcount_range"]["value"])

        quote = f"River Clay employs 31 people and won the {link}."
        build.page("nimble", "https://archive.example/profile", quote)
        field = build.fields()["headcount_range"]
        self.assertEqual(field["value"], "11-50")
        self.assertEqual(field["citations"][0]["excerpt"], quote)
