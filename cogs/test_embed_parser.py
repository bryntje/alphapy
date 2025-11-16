# test_embed_parser.py
import unittest  # type: ignore
from datetime import datetime
from typing import Optional, Tuple, Any
from cogs.embed_watcher import EmbedReminderWatcher
import discord  # type: ignore

class DummyBot:
    def get_channel(self, *_) -> Optional[Any]:
        return None

class TestEmbedParser(unittest.TestCase):
    def setUp(self) -> None:
        self.w = EmbedReminderWatcher(DummyBot())

    def test_parse_datetime_with_full_date(self) -> None:
        dt, tz = self.w.parse_datetime("12 March 2025", "Time: 14:30")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 12)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)

    def test_parse_datetime_without_date(self) -> None:
        dt, tz = self.w.parse_datetime(None, "Time: 09:15")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 9)
        self.assertEqual(dt.minute, 15)

    def test_parse_days_daily(self) -> None:
        now: datetime = datetime.now()
        days: str = self.w.parse_days("daily", now)
        self.assertEqual(days, "0,1,2,3,4,5,6")

    def test_parse_days_specific(self) -> None:
        now: datetime = datetime.now()
        days: str = self.w.parse_days("Monday, Wednesday, Friday", now)
        self.assertEqual(days, "0,2,4")

if __name__ == "__main__":
    unittest.main()