import unittest

from state import Store, domain, fresh_dossier


class SnapshotTests(unittest.TestCase):
    def test_restores_hostname_after_exactly_one_prefix_was_removed(self):
        original = Store()
        name = domain(" WWW.www.rotor.TEST. ")
        self.assertEqual(name, "www.rotor.test")
        original.dossiers[name] = fresh_dossier(name)

        restored = Store.restore(original.export())

        self.assertEqual(restored.detail(name), original.detail(name))


class ClockTests(unittest.TestCase):
    def test_submicrosecond_clock_order_and_serialization(self):
        from state import timestamp

        first = timestamp("2026-05-05T10:10:10.123456789012345678901+02:00")
        earlier = timestamp("2026-05-05T08:10:10.123456789012345678900+00:00")
        same = timestamp("2026-05-05T08:10:10.1234567890123456789010Z")

        self.assertLess(earlier, first)
        self.assertEqual(same, first)
        self.assertEqual(timestamp(first.isoformat()), first)
        self.assertIn(".123456789012345678901", first.isoformat())
