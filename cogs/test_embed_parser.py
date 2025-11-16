# test_embed_parser.py
import unittest
from datetime import datetime
from cogs.embed_watcher import EmbedReminderWatcher
from utils.settings_service import SettingsService
import discord

class MockSettingsService:
    def get(self, scope, key, guild_id):
        # Return default values for tests
        if scope == "embedwatcher" and (key == "reminder_offset" or key == "reminder_offset_minutes"):
            return 60  # default 60 minutes
        return None

    def set(self, scope, key, value, guild_id):
        pass

    def is_overridden(self, scope, key, guild_id):
        return False

    def list_scope(self, scope, guild_id):
        return {}

    def clear(self, scope, key, guild_id):
        pass

class DummyBot:
    def __init__(self):
        self.settings = MockSettingsService()

    def get_channel(self, *_):
        return None

class TestEmbedParser(unittest.TestCase):
    def setUp(self):
        self.w = EmbedReminderWatcher(DummyBot())

    def test_parse_datetime_with_full_date(self):
        dt, tz = self.w.parse_datetime("12 March 2025", "Time: 14:30")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 12)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)

    def test_parse_datetime_without_date(self):
        dt, tz = self.w.parse_datetime(None, "Time: 09:15")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 9)
        self.assertEqual(dt.minute, 15)

    def test_parse_days_daily(self):
        now = datetime.now()
        days = self.w.parse_days("daily", now)
        self.assertEqual(days, "0,1,2,3,4,5,6")

    def test_parse_days_specific(self):
        now = datetime.now()
        days = self.w.parse_days("Monday, Wednesday, Friday", now)
        self.assertEqual(days, "0,2,4")

if __name__ == "__main__":
    unittest.main()