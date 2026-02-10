"""
Pytest configuration and shared fixtures for alphapy tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime
import discord
from discord.ext import commands
from typing import Optional
from utils.timezone import BRUSSELS_TZ


class MockSettingsService:
    """Mock settings service for testing."""
    
    def __init__(self):
        self._settings = {}
    
    def get(self, scope: str, key: str, guild_id: int = 0, fallback: Optional[any] = None) -> Optional[any]:
        """Get a setting value. Matches SettingsService signature for CachedSettingsHelper."""
        return self._settings.get((scope, key, guild_id), fallback)
    
    def set(self, scope: str, key: str, value: any, guild_id: int = 0, updated_by: Optional[int] = None):
        """Set a setting value."""
        self._settings[(scope, key, guild_id)] = value
    
    def clear(self, scope: str, key: str, guild_id: int = 0):
        """Clear a setting."""
        self._settings.pop((scope, key, guild_id), None)


class MockBot:
    """Mock Discord bot for testing."""
    
    def __init__(self):
        self.settings = MockSettingsService()
        self.guilds = []
        self.user = Mock(id=123456789)
        # Mock event loop for ReminderCog initialization
        import asyncio
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
    
    def get_channel(self, channel_id: int):
        """Mock channel getter."""
        return None


@pytest.fixture
def mock_bot():
    """Fixture providing a mock Discord bot."""
    return MockBot()


@pytest.fixture
def mock_settings():
    """Fixture providing a mock settings service."""
    return MockSettingsService()


@pytest.fixture
def sample_embed():
    """Fixture providing a sample Discord embed for testing."""
    embed = discord.Embed(
        title="Test Event",
        description="This is a test event description",
        color=0x00ff00
    )
    embed.add_field(name="Time", value="19:30", inline=False)
    embed.add_field(name="Location", value="Test Location", inline=False)
    return embed


@pytest.fixture
def sample_embed_with_date():
    """Fixture providing a sample Discord embed with date."""
    embed = discord.Embed(
        title="Weekly Meeting",
        description="Our weekly team meeting",
        color=0x0000ff
    )
    embed.add_field(name="Date", value="15/01/2025", inline=False)
    embed.add_field(name="Time", value="14:00 CET", inline=False)
    embed.add_field(name="Days", value="Monday, Wednesday", inline=False)
    embed.add_field(name="Location", value="Conference Room", inline=False)
    return embed


@pytest.fixture
def sample_embed_recurring():
    """Fixture providing a sample recurring event embed."""
    embed = discord.Embed(
        title="Daily Standup",
        description="Daily team standup meeting",
        color=0xff0000
    )
    embed.add_field(name="Time", value="09:00", inline=False)
    embed.add_field(name="Days", value="Daily", inline=False)
    return embed


@pytest.fixture
def sample_embed_one_off():
    """Fixture providing a sample one-off event embed."""
    embed = discord.Embed(
        title="Special Event",
        description="One-time special event",
        color=0xffff00
    )
    embed.add_field(name="Date", value="25/12/2025", inline=False)
    embed.add_field(name="Time", value="20:00", inline=False)
    embed.add_field(name="Location", value="Main Hall", inline=False)
    return embed


@pytest.fixture
def mock_database_pool():
    """Fixture providing a mock asyncpg connection pool."""
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool, conn


@pytest.fixture
def brussels_now():
    """Fixture providing current time in Brussels timezone."""
    return datetime.now(BRUSSELS_TZ)
