import unittest

from state import parse_time


class PreciseClock(unittest.TestCase):
    def test_monotonic_order_and_preserved_precision(self):
        for prefix, earlier, later, zone in [
            ("2026-03-01T12:00:00.", "1234568", "1234569", "+00:00"),
            ("2026-03-01T12:00:00.", "345678008", "345678009", "+02:30"),
            ("2026-03-01T12:00:00.", "12345678901234567891", "12345678901234567892", "-07:00"),
        ]:
            with self.subTest(zone=zone):
                stamp = parse_time(prefix + later + zone)
                self.assertGreater(stamp, parse_time(prefix + earlier + zone))
                self.assertEqual(stamp.isoformat(), prefix + later + zone)

    def test_instant_equality_across_offsets_and_fraction_lengths(self):
        self.assertEqual(parse_time("2026-03-02T00:45:00.123456900+02:30"),
                         parse_time("2026-03-01T22:15:00.1234569Z"))
        self.assertGreater(parse_time("2026-03-01T22:15:00.1234569001Z"),
                           parse_time("2026-03-02T00:45:00.1234569+02:30"))
