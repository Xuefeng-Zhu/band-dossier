import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from research import Build, CALL


class ScriptedSearch:
    """Simulate SDK replies, including a server-enforced retry interval."""
    def __init__(self, domain, refusals):
        self.domain = domain
        self.remaining = refusals
        self.time = 0
        self.last_refusal = None
        self.trace = []

    async def sleep(self, seconds):
        self.time += seconds

    async def search(self, query, **options):
        call = CALL.get()
        status = 200
        if query == self.domain:
            early = self.last_refusal is not None and self.time - self.last_refusal < 1
            if self.remaining or early:
                status = 429
                self.remaining = max(0, self.remaining - 1)
                self.last_refusal = self.time
            self.trace.append(status)
        call.update(status=status, sent=True, accepted=status == 200, cost=int(status == 200))
        if status == 429:
            raise RuntimeError("rate limited")
        return SimpleNamespace(results=[])


class ExactSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_refusals_recover_without_duplicate_accepted_search(self):
        for refusals in (0, 1, 2, 3):
            with self.subTest(refusals=refusals):
                domain = "red-oak.example"
                source = ScriptedSearch(domain, refusals)
                build = Build(domain, source, lambda: True, lambda units: None)
                with patch("research.asyncio.sleep", side_effect=source.sleep), patch.object(build, "research", AsyncMock()):
                    await build.run()
                self.assertEqual(source.trace, [429] * refusals + [200])
                self.assertEqual(sum(c["cost"] for c in build.calls if c["argument"] == domain), 1)


if __name__ == "__main__":
    unittest.main()
