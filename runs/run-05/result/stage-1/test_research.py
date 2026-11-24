import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from web_router import ExtractResponse, ExtractedDocument, ProviderError, SearchResponse, SearchResult

from research import Build


class SearchEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.domain = "river-clay.example"
        self.url = "https://river-clay.example/company"
        self.api = SimpleNamespace(search=AsyncMock(), extract=AsyncMock(), submit_research=AsyncMock())
        self.api.submit_research.side_effect = ProviderError("nimble", "unavailable")
        self.enterContext(patch("research.router", return_value=self.api))
        self.enterContext(patch("research.available", return_value=["nimble"]))

    def page_hit(self, query, snippet):
        return SearchResponse(provider="nimble", query=query, results=[
            SearchResult(url=self.url, title="Company", description=snippet, content=snippet)
        ])

    async def test_uses_served_snippet_when_page_is_unavailable(self):
        quote = "River Clay was established in 1998."

        async def search(query, **options):
            if query == self.domain:
                return self.page_hit(query, quote)
            raise ProviderError("nimble", "unavailable")

        self.api.search.side_effect = search
        self.api.extract.return_value = ExtractResponse(provider="nimble")
        build = Build(self.domain)
        await build.run()

        field = build.fields()["founded_year"]
        self.assertEqual(field["value"], 1998)
        self.assertEqual(field["citations"], [{"url": self.url, "excerpt": quote, "provider": "nimble"}])

    async def test_reads_new_url_from_successful_exact_retry(self):
        exact_attempts = 0
        quote = "River Clay employs 80 employees."

        async def search(query, **options):
            nonlocal exact_attempts
            if query == self.domain:
                exact_attempts += 1
                if exact_attempts == 1:
                    raise ProviderError("nimble", "temporarily unavailable")
                return self.page_hit(query, "About our company.")
            return SearchResponse(provider="nimble", query=query, results=[])

        self.api.search.side_effect = search
        self.api.extract.return_value = ExtractResponse(provider="nimble", documents=[
            ExtractedDocument(url=self.url, content=quote, format="markdown")
        ])
        build = Build(self.domain)
        await build.run()

        self.assertEqual(exact_attempts, 2)
        self.assertEqual(build.fields()["headcount_range"]["value"], "51-200")
        self.assertEqual(self.api.extract.await_count, 1)

    async def test_exact_retry_precedes_discretionary_extracts(self):
        exact_attempts, exact_answers = 0, 0

        async def search(query, **options):
            nonlocal exact_attempts, exact_answers
            if query == self.domain:
                exact_attempts += 1
                if exact_attempts == 1:
                    raise ProviderError("nimble", "temporarily unavailable")
                exact_answers += 1
                return SearchResponse(provider="nimble", query=query, results=[])
            topic = query.split()[1]
            hits = [SearchResult(url=f"{self.url}/{topic}/{i}", title="Background") for i in range(10)]
            return SearchResponse(provider="nimble", query=query, results=hits)

        self.api.search.side_effect = search
        self.api.extract.return_value = ExtractResponse(provider="nimble")
        self.api.submit_research.side_effect = None
        self.api.submit_research.return_value = SimpleNamespace(
            aresult=AsyncMock(return_value=SimpleNamespace(structured={}, answer=None, citations=[]))
        )

        build = Build(self.domain)
        await build.run()

        self.assertEqual(exact_answers, 1)
        self.assertLessEqual(build.spent, 80)

    async def test_webrouter_deadlines_consume_units_and_enforce_cap(self):
        from web_router import DeadlineExceededError

        build = Build(self.domain)
        # Five extracts remain affordable after three research runs.
        succeeded = AsyncMock(return_value=object())
        for _ in range(3):
            await build.call("nimble", "research", self.domain, 25, succeeded)
        timeout = AsyncMock(side_effect=DeadlineExceededError("nimble", 55))
        for i in range(7):
            await build.call("nimble", "extract", f"{self.url}/{i}", 1, timeout)

        self.assertEqual(build.spent, 80)
        self.assertEqual(timeout.await_count, 5)
        self.assertEqual(sum(c["units"] for c in build.calls), build.spent)

    async def test_repeated_transient_exact_refusals_end_at_first_success(self):
        exact_attempts = 0

        async def search(query, **options):
            nonlocal exact_attempts
            if query == self.domain:
                exact_attempts += 1
                if exact_attempts <= 3:
                    error = ProviderError("nimble", "service temporarily unavailable")
                    error.status_code = 503
                    raise error
            return SearchResponse(provider="nimble", query=query, results=[])

        self.api.search.side_effect = search
        build = Build(self.domain)
        await build.run()

        self.assertEqual(exact_attempts, 4)
        exact = [c for c in build.calls if c["argument"] == self.domain]
        self.assertEqual([c["outcome"] for c in exact], ["refused"] * 3 + ["answered"])
        self.assertLessEqual(build.spent, 80)
