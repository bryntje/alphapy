"""
Tests for Premium guard: message helper and is_premium behaviour.
"""

import pytest
from unittest.mock import AsyncMock, patch

from utils.premium_guard import (
    premium_required_message,
    is_premium,
    get_active_premium_guild,
    _get_cached,
    _set_cache,
)


class TestPremiumRequiredMessage:
    """Tests for premium_required_message helper."""

    def test_returns_string_with_premium_command(self):
        msg = premium_required_message("Reminders with images")
        assert isinstance(msg, str)
        assert "/premium" in msg
        assert "premium" in msg.lower()
        assert "Reminders with images" in msg

    def test_contains_mockingbird_tone(self):
        msg = premium_required_message("Feature")
        assert "mature" in msg.lower() or "power" in msg.lower() or "premium" in msg.lower()


class TestIsPremium:
    """Tests for is_premium with mocked Core-API and DB."""

    @pytest.mark.asyncio
    async def test_returns_false_when_core_and_db_both_fail(self):
        with patch("utils.premium_guard._check_core_api", new_callable=AsyncMock, return_value=None), \
             patch("utils.premium_guard._check_local_db", new_callable=AsyncMock, return_value=False):
            result = await is_premium(999, 888)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_core_returns_true(self):
        with patch("utils.premium_guard._check_core_api", new_callable=AsyncMock, return_value=True), \
             patch("utils.premium_guard._check_local_db", new_callable=AsyncMock):
            result = await is_premium(111, 222)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_local_db_returns_true_and_core_unconfigured(self):
        with patch("utils.premium_guard._check_core_api", new_callable=AsyncMock, return_value=None), \
             patch("utils.premium_guard._check_local_db", new_callable=AsyncMock, return_value=True):
            result = await is_premium(333, 444)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_core_returns_false(self):
        with patch("utils.premium_guard._check_core_api", new_callable=AsyncMock, return_value=False), \
             patch("utils.premium_guard._check_local_db", new_callable=AsyncMock):
            result = await is_premium(555, 666)
        assert result is False


class TestPremiumCache:
    """Tests for cache get/set (no TTL expiry in test)."""

    def test_set_and_get_cached(self):
        _set_cache(1, 2, True)
        assert _get_cached(1, 2) is True
        _set_cache(1, 2, False)
        assert _get_cached(1, 2) is False

    def test_get_cached_miss_returns_none(self):
        assert _get_cached(99999, 88888) is None


class TestGetActivePremiumGuild:
    """get_active_premium_guild returns the guild_id (int) or None, never 0."""

    @pytest.mark.asyncio
    async def test_returns_none_when_pool_unavailable(self):
        with patch("utils.premium_guard._ensure_pool", new_callable=AsyncMock, return_value=None):
            result = await get_active_premium_guild(12345)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        mock_cm.__aexit__.return_value = None
        with patch("utils.premium_guard._ensure_pool", new_callable=AsyncMock, return_value=AsyncMock()), \
             patch("utils.premium_guard.acquire_safe", return_value=mock_cm):
            result = await get_active_premium_guild(111)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_guild_id_int_when_row_exists(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"guild_id": 98765})
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        mock_cm.__aexit__.return_value = None
        with patch("utils.premium_guard._ensure_pool", new_callable=AsyncMock, return_value=AsyncMock()), \
             patch("utils.premium_guard.acquire_safe", return_value=mock_cm):
            result = await get_active_premium_guild(111)
        assert result == 98765
        assert isinstance(result, int)
