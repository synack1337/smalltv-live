import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from smalltv_live import usage


class UsageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cache = Path(self.dir.name) / "sub" / "rate_limits.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_round_trip_keeps_only_limits(self):
        usage.write(self.cache, {"five_hour": {"used_percentage": 12.5, "resets_at": 1000, "extra": "x"},
                                 "seven_day": {"used_percentage": 40, "resets_at": 2000}}, now=100)
        u = usage.read(self.cache, now=160)
        self.assertEqual(u.five_hour.used_percentage, 12.5)
        self.assertEqual(u.seven_day.resets_at, 2000)
        self.assertEqual(u.age_seconds, 60)
        self.assertNotIn("extra", self.cache.read_text())
        self.assertEqual(stat.S_IMODE(os.stat(self.cache).st_mode), 0o600)

    def test_missing_or_malformed_is_no_data(self):
        self.assertIsNone(usage.read(self.cache).age_seconds)
        self.cache.parent.mkdir(parents=True)
        for text in ("", "[]", "{", '{"rate_limits": 5}', '{"captured_at": "x", "rate_limits": {}}'):
            self.cache.write_text(text)
            u = usage.read(self.cache)
            self.assertIsNone(u.five_hour.used_percentage, text)

    def test_percentages_are_clamped_and_typed(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text(json.dumps({"captured_at": 1, "rate_limits": {
            "five_hour": {"used_percentage": 250}, "seven_day": {"used_percentage": True}}}))
        u = usage.read(self.cache, now=2)
        self.assertEqual(u.five_hour.used_percentage, 100)
        self.assertIsNone(u.seven_day.used_percentage)

    def test_stale(self):
        self.assertTrue(usage.EMPTY.is_stale(60))
        self.assertFalse(usage.Usage(usage.Limit(1, 1), usage.Limit(1, 1), 10).is_stale(60))

    def test_statusline_caches_and_chains(self):
        payload = json.dumps({"rate_limits": {"five_hour": {"used_percentage": 3, "resets_at": 5}}})
        with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                mock.patch.object(sys, "stdout", new_callable=io.StringIO) as out:
            self.assertEqual(usage.statusline(self.cache, f"{sys.executable} -c \"print('next')\""), 0)
        self.assertEqual(out.getvalue().strip(), "next")
        self.assertEqual(usage.read(self.cache).five_hour.used_percentage, 3)

    def test_statusline_survives_garbage(self):
        with mock.patch.object(sys, "stdin", io.StringIO("not json")):
            self.assertEqual(usage.statusline(self.cache, None), 0)
        self.assertFalse(self.cache.exists())


if __name__ == "__main__":
    unittest.main()
