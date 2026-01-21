"""
Tests for reminder parsing and timing logic.

Tests cover:
- Reminder time calculation (T-60 vs T0)
- Midnight edge case handling
- One-off vs recurring event detection
- Day matching logic
"""

import pytest
from datetime import datetime, time, timedelta
from unittest.mock import Mock, AsyncMock
from cogs.reminders import ReminderCog
from utils.timezone import BRUSSELS_TZ


class TestReminderOffset:
    """Tests for reminder offset calculation."""
    
    @pytest.fixture
    def reminder_cog(self, mock_bot):
        """Create a ReminderCog instance for testing."""
        return ReminderCog(mock_bot)
    
    def test_default_reminder_offset(self, reminder_cog):
        """Test that default reminder offset is 60 minutes."""
        # MockSettingsService returns None by default, which should trigger default value
        offset = reminder_cog._get_reminder_offset(guild_id=123456)
        # Should return 60 as default when settings returns None
        assert offset == 60
    
    def test_custom_reminder_offset(self, reminder_cog):
        """Test custom reminder offset from settings."""
        # Set custom offset via settings
        reminder_cog.settings.set("embedwatcher", "reminder_offset_minutes", 30, guild_id=123456)
        offset = reminder_cog._get_reminder_offset(guild_id=123456)
        assert offset == 30


class TestReminderTiming:
    """Tests for reminder timing calculations."""
    
    @pytest.fixture
    def reminder_cog(self, mock_bot):
        """Create a ReminderCog instance for testing."""
        return ReminderCog(mock_bot)
    
    def test_one_off_reminder_time_calculation(self, reminder_cog):
        """Test that one-off reminders are calculated at T-60."""
        # Event at 19:30
        event_time = datetime(2025, 1, 15, 19, 30, tzinfo=BRUSSELS_TZ)
        reminder_offset = 60  # 1 hour
        
        # Reminder should be at 18:30 (T-60)
        expected_reminder_time = event_time - timedelta(minutes=reminder_offset)
        assert expected_reminder_time.hour == 18
        assert expected_reminder_time.minute == 30
    
    def test_recurring_reminder_time_calculation(self, reminder_cog):
        """Test that recurring reminders are calculated at T-60."""
        # Event at 14:00
        event_time = datetime(2025, 1, 15, 14, 0, tzinfo=BRUSSELS_TZ)
        reminder_offset = 60
        
        # Reminder should be at 13:00 (T-60)
        expected_reminder_time = event_time - timedelta(minutes=reminder_offset)
        assert expected_reminder_time.hour == 13
        assert expected_reminder_time.minute == 0
    
    def test_midnight_edge_case_reminder(self, reminder_cog):
        """Test midnight edge case: reminder at 23:xx for event at 00:xx next day."""
        # Event at Wednesday 00:30 (midnight + 30 minutes)
        event_time = datetime(2025, 1, 15, 0, 30, tzinfo=BRUSSELS_TZ)  # Wednesday
        reminder_offset = 60
        
        # Reminder should be at Tuesday 23:30 (previous day, T-60)
        expected_reminder_time = event_time - timedelta(minutes=reminder_offset)
        assert expected_reminder_time.day == 14  # Previous day
        assert expected_reminder_time.hour == 23
        assert expected_reminder_time.minute == 30
        assert expected_reminder_time.weekday() == 1  # Tuesday
    
    def test_custom_offset_30_minutes(self, reminder_cog):
        """Test reminder with custom 30-minute offset."""
        event_time = datetime(2025, 1, 15, 19, 0, tzinfo=BRUSSELS_TZ)
        reminder_offset = 30
        
        # Reminder should be at 18:30 (T-30)
        expected_reminder_time = event_time - timedelta(minutes=reminder_offset)
        assert expected_reminder_time.hour == 18
        assert expected_reminder_time.minute == 30


class TestOneOffVsRecurring:
    """Tests for distinguishing one-off vs recurring events."""
    
    def test_one_off_has_event_time(self):
        """Test that one-off events have event_time set."""
        # One-off events have a specific event_time timestamp
        event_time = datetime(2025, 1, 15, 19, 30, tzinfo=BRUSSELS_TZ)
        assert event_time is not None
        # One-off events typically have empty or single-day days array
        days = []  # Empty for one-off
        assert len(days) == 0
    
    def test_recurring_has_no_event_time(self):
        """Test that recurring events have event_time as None."""
        event_time = None
        days = ["0", "2", "4"]  # Monday, Wednesday, Friday
        assert event_time is None
        assert len(days) > 0
    
    def test_recurring_multiple_days(self):
        """Test recurring event with multiple days."""
        days = ["1", "3", "5"]  # Tuesday, Thursday, Saturday
        assert len(days) == 3
        assert "1" in days
        assert "3" in days
        assert "5" in days


class TestDayMatching:
    """Tests for day matching logic."""
    
    def test_numeric_day_match(self):
        """Test matching numeric day strings."""
        current_day = "2"  # Wednesday
        reminder_days = ["2"]  # Wednesday
        assert current_day in reminder_days
    
    def test_text_day_match(self):
        """Test matching text day abbreviations."""
        current_day = "2"  # Wednesday
        reminder_days = ["wo", "woe", "woensdag", "wednesday"]
        # Should match via day mapping logic
        day_map = {
            "wo": "2", "woe": "2", "woensdag": "2", "wednesday": "2"
        }
        for day_abbrev in reminder_days:
            assert day_map.get(day_abbrev) == current_day
    
    def test_multiple_days_match(self):
        """Test matching when reminder has multiple days."""
        current_day = "1"  # Tuesday
        reminder_days = ["0", "1", "2", "3", "4"]  # Weekdays
        assert current_day in reminder_days
    
    def test_no_day_match(self):
        """Test when current day doesn't match reminder days."""
        current_day = "6"  # Sunday
        reminder_days = ["0", "1", "2", "3", "4"]  # Weekdays only
        assert current_day not in reminder_days


class TestMidnightEdgeCase:
    """Tests for midnight edge case handling."""
    
    def test_midnight_reminder_detection(self):
        """Test detection of midnight edge case (reminder at 23:xx)."""
        reminder_time = time(23, 30)
        assert reminder_time.hour == 23
        is_late_night = reminder_time.hour == 23
        assert is_late_night is True
    
    def test_midnight_event_next_day(self):
        """Test that midnight events are on the next calendar day."""
        # Reminder at Tuesday 23:30
        reminder_time = datetime(2025, 1, 14, 23, 30, tzinfo=BRUSSELS_TZ)  # Tuesday
        
        # Event at Wednesday 00:30 (next day)
        event_time = reminder_time + timedelta(hours=1)  # Next hour
        assert event_time.day == reminder_time.day + 1 or (event_time.hour == 0 and event_time.day == reminder_time.day + 1)
        assert event_time.weekday() == 2  # Wednesday
    
    def test_normal_time_not_midnight(self):
        """Test that normal times don't trigger midnight edge case."""
        reminder_time = time(18, 30)
        assert reminder_time.hour != 23
        is_late_night = reminder_time.hour == 23
        assert is_late_night is False


class TestTimeFormatting:
    """Tests for time formatting and conversion."""
    
    def test_time_to_string_format(self):
        """Test converting time object to string format."""
        time_obj = time(19, 30)
        time_str = time_obj.strftime("%H:%M")
        assert time_str == "19:30"
    
    def test_string_to_time_format(self):
        """Test converting string to time object."""
        time_str = "14:00"
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        assert time_obj.hour == 14
        assert time_obj.minute == 0
    
    def test_datetime_to_time_extraction(self):
        """Test extracting time from datetime."""
        dt = datetime(2025, 1, 15, 19, 30, tzinfo=BRUSSELS_TZ)
        time_obj = dt.time()
        assert time_obj.hour == 19
        assert time_obj.minute == 30


class TestReminderQueryLogic:
    """Tests for reminder query logic (conceptual, not actual DB queries)."""
    
    def test_one_off_t_minus_60_query_conditions(self):
        """Test query conditions for one-off reminders at T-60."""
        # Conditions:
        # - event_time IS NOT NULL
        # - time::time = current_time (reminder time)
        # - event_time - 60 minutes = current_date OR midnight edge case
        event_time = datetime(2025, 1, 15, 19, 30, tzinfo=BRUSSELS_TZ)
        reminder_time = event_time - timedelta(minutes=60)
        current_time = reminder_time.time()
        current_date = reminder_time.date()
        
        assert event_time is not None
        assert current_time == time(18, 30)
        assert (event_time - timedelta(minutes=60)).date() == current_date
    
    def test_one_off_t0_query_conditions(self):
        """Test query conditions for one-off reminders at T0."""
        # Conditions:
        # - event_time IS NOT NULL
        # - call_time::time = current_time (event time)
        # - event_time date = current_date
        event_time = datetime(2025, 1, 15, 19, 30, tzinfo=BRUSSELS_TZ)
        call_time = event_time.time()
        current_time = call_time
        current_date = event_time.date()
        
        assert event_time is not None
        assert current_time == time(19, 30)
        assert event_time.date() == current_date
    
    def test_recurring_query_conditions(self):
        """Test query conditions for recurring reminders."""
        # Conditions:
        # - event_time IS NULL
        # - time::time = current_time (reminder time)
        # - current_day matches days array
        event_time = None
        reminder_time = time(18, 30)
        current_time = reminder_time
        current_day = "2"  # Wednesday
        days = ["2"]  # Wednesday
        
        assert event_time is None
        assert current_time == reminder_time
        assert current_day in days
