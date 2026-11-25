import unittest
from types import SimpleNamespace

from gather import Build


class TransientSearch:
    """One connection loss. Only a repeated exact search discovers the full text."""
    def __init__(self, domain, statement):
        self.domain = domain
        self.url = f"https://records.example/archive/{domain}"
        self.statement = statement
        self.exact_attempts = 0

    async def search(self, query, **kwargs):
        if query != self.domain:
            return SimpleNamespace(results=[])
        self.exact_attempts += 1
        if self.exact_attempts == 1:
            raise ConnectionError()
        page = SimpleNamespace(title="Annual review", url=self.url, published_date=None,
                               content="Annual report introduction.", description="")
        return SimpleNamespace(results=[page])

    async def extract(self, url, **kwargs):
        docs = [SimpleNamespace(url=url, content=self.statement)] if url == self.url else []
        return SimpleNamespace(documents=docs)

    async def submit_research(self, *args, **kwargs):
        async def result(**kwargs):
            return SimpleNamespace(structured={}, citations=[])
        return SimpleNamespace(aresult=result)


class RecoveryCoverage(unittest.IsolatedAsyncioTestCase):
    async def test_exact_search_recovers_and_fetches_sources_for_missing_fields(self):
        for domain, field, sentence, value in (
            ("ivory-sled.test", "headcount_range", "Ivory Sled employs 187 people.", "51-200"),
            ("amber-river.test", "hq_city", "Amber River is headquartered in Upper Hutt.", "Upper Hutt"),
            ("green-oar.test", "legal_name", "Green Oar is registered as Green Oar GmbH.", "Green Oar GmbH"),
        ):
            with self.subTest(field=field):
                router = TransientSearch(domain, sentence)
                build = Build(domain, SimpleNamespace(order=["nimble"], router=router))
                await build.gather()
                self.assertEqual(router.exact_attempts, 2)
                self.assertEqual(build.fields()[field]["value"], value)
                self.assertEqual([c["target"] for c in build.calls if c["method"] == "extract"].count(router.url), 1)
                self.assertLessEqual(build.spent, 80)
