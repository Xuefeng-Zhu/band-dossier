import unittest

from evidence import Evidence, values


class ResearchEvidenceTests(unittest.TestCase):
    def test_year_group_separator(self):
        for text, expected in (("1,800", 1800), ("2,099", 2099), ("2,000", 2000),
                               ("1,700", None), ("20,00", None), ("USD 2,000", None)):
            with self.subTest(text=text):
                self.assertEqual(values("elm-lake.test", f"Elm Lake was established in {text}.").get("founded_year"), expected)

    def test_citations_only_in_header(self):
        for label, claim, sentence in (("Facts", ("ceo", "Ada Ruiz"), "Elm Lake CEO: Ada Ruiz."),
                                      ("Description", ("legal_name", "Elm Lake LLC"), "Elm Lake is registered as Elm Lake LLC.")):
            url = "https://elm-lake.test/about"
            header = f'{label}: {{"claim":"{sentence}"}}'
            for excerpt in (header, sentence):
                with self.subTest(excerpt=excerpt):
                    evidence = Evidence("elm-lake.test")
                    evidence.full_text = {url: header + "\n\nHistory and operations."}
                    evidence.add("nimble", url, excerpt, claim=claim)
                    self.assertIsNone(evidence.fields()[claim[0]]["value"])
                    evidence.full_text[url] += "\n" + sentence
                    evidence.add("nimble", url, sentence, claim=claim)
                    self.assertEqual(evidence.fields()[claim[0]]["value"], claim[1])


if __name__ == "__main__":
    unittest.main()
