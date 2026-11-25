import unittest

from research import Build


class PageHeaderTests(unittest.TestCase):
    def test_unicode_header_claims_are_excluded_from_evidence(self):
        domain = "cobalt-systems.test"
        for header in ("Résumé", "Équipe-Métadonnées", "Источник"):
            with self.subTest(header=header):
                build = Build(domain, None)
                page = (f"{header}: Cobalt Systems was founded in 1900.\n"
                        "Facts: Cobalt Systems is based in Paris.\n\n"
                        "Cobalt Systems is based in Zürich.")
                build.page("https://" + domain, "nimble", page, True)
                self.assertIsNone(build.fields["founded_year"]["value"])
                self.assertEqual(build.fields["hq_city"]["value"], "Zürich")

    def test_initials_do_not_turn_prose_into_a_header(self):
        build = Build("cobalt-systems.test", None)
        build.page("https://cobalt-systems.test", "nimble",
                   "Q: Cobalt Systems was founded in 2014.", True)
        self.assertEqual(build.fields["founded_year"]["value"], 2014)
