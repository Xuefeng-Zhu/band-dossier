import unittest

from gather import Build


class SourceLabels(unittest.TestCase):
    def check_source(self, domain, field, expected, text, kind):
        build = Build(domain, None)
        claim = [field, expected] if kind == "research" else None
        build.source("nimble", "https://" + domain + "/profile", text, kind, claim=claim)
        self.assertEqual(build.fields()[field]["value"], expected)

    def test_uppercase_prose_labels(self):
        for domain, field, expected, excerpt in (
            ("inlet-crane.test", "ceo", "Isla Braun", "CEO: Isla Braun leads Inlet Crane."),
            ("signal-briar.test", "hq_city", "Brno", "HQ: Signal Briar is based in Brno."),
            ("blue-pond.test", "funding_total", 26000000, "FINANCE: Blue Pond has raised $26M."),
        ):
            for kind in ("page", "snippet", "research"):
                with self.subTest(kind=kind, excerpt=excerpt):
                    self.check_source(domain, field, expected, excerpt, kind)

    def test_page_metadata_and_excerpts_have_different_boundaries(self):
        sentence = "History: Blue Pond was founded in 1987."
        for kind in ("research", "snippet"):
            with self.subTest(kind=kind):
                self.check_source("blue-pond.test", "founded_year", 1987, sentence, kind)
        text = "Kind: filing\nTitle: Blue Pond was founded in 1902.\n\n" + sentence
        self.check_source("blue-pond.test", "founded_year", 1987, text, "page")
        self.check_source("blue-pond.test", "founded_year", None,
                          "Title: Blue Pond was founded in 1902.\n\nNo further information.", "page")


if __name__ == "__main__":
    unittest.main()
