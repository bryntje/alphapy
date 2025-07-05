import unittest
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
import discord
from cogs.embed_watcher import parse_embed_for_reminder

class TestReminderMidnight(unittest.TestCase):
    def test_midnight_triggers_previous_day(self):
        tz = ZoneInfo("Europe/Brussels")
        embed = discord.Embed(
            title="Event",
            description="Date: 19/03/2024\nTime: 00:30"
        )
        parsed = parse_embed_for_reminder(embed)
        self.assertIsNotNone(parsed)
        reminder = parsed["reminder_time"].astimezone(tz)
        self.assertEqual(reminder.hour, 23)
        self.assertEqual(reminder.minute, 30)
        self.assertEqual(reminder.day, 18)
        self.assertEqual(reminder.weekday(), 0)  # Monday

    def test_event_0030_has_2330_reminder(self):
        tz = ZoneInfo("Europe/Brussels")
        embed = discord.Embed(
            title="Event",
            description="Date: 19/03/2024\nTime: 00:30"
        )
        parsed = parse_embed_for_reminder(embed)
        self.assertIsNotNone(parsed)
        event_dt = parsed["datetime"].astimezone(tz)
        expected_reminder = event_dt - timedelta(minutes=60)
        self.assertEqual(parsed["reminder_time"], expected_reminder)
        self.assertEqual(parsed["reminder_time"].weekday(), expected_reminder.weekday())
        self.assertEqual(parsed["days"], [str(expected_reminder.weekday())])

if __name__ == "__main__":
    unittest.main()
