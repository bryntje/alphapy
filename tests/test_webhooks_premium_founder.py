"""
Tests for premium-invalidate and founder webhooks.

Uses a minimal FastAPI app mounting only these routers to avoid loading full api.py.
"""

from concurrent.futures import Future
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.premium_guard import _get_cached, _set_cache
from webhooks.premium_invalidate import router as premium_invalidate_router
from webhooks.founder import router as founder_router

app = FastAPI()
app.include_router(premium_invalidate_router)
app.include_router(founder_router)
client = TestClient(app)


class TestPremiumInvalidateWebhook:
    """Tests for POST /webhooks/premium-invalidate."""

    @patch("webhooks.premium_invalidate.get_premium_invalidate_secret", return_value=None)
    def test_invalidates_cache_for_user_and_guild(self, _mock_secret):
        _set_cache(111, 222, True)
        assert _get_cached(111, 222) is True
        response = client.post(
            "/webhooks/premium-invalidate",
            content='{"user_id": 111, "guild_id": 222}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "acknowledged", "user_id": "111"}
        assert _get_cached(111, 222) is None

    @patch("webhooks.premium_invalidate.get_premium_invalidate_secret", return_value=None)
    def test_invalidates_all_guilds_for_user_when_guild_id_omitted(self, _mock_secret):
        _set_cache(333, 1, True)
        _set_cache(333, 2, False)
        response = client.post(
            "/webhooks/premium-invalidate",
            content='{"user_id": 333}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert _get_cached(333, 1) is None
        assert _get_cached(333, 2) is None

    @patch("webhooks.premium_invalidate.get_premium_invalidate_secret", return_value=None)
    def test_missing_user_id_returns_400(self, _mock_secret):
        response = client.post(
            "/webhooks/premium-invalidate",
            content='{"guild_id": 456}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "user_id" in response.json().get("detail", "").lower()

    @patch("webhooks.premium_invalidate.get_premium_invalidate_secret", return_value=None)
    def test_invalid_user_id_returns_400(self, _mock_secret):
        response = client.post(
            "/webhooks/premium-invalidate",
            content='{"user_id": "not_an_int"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @patch("webhooks.premium_invalidate.get_premium_invalidate_secret", return_value=None)
    def test_invalid_guild_id_returns_400(self, _mock_secret):
        response = client.post(
            "/webhooks/premium-invalidate",
            content='{"user_id": 123, "guild_id": "bad"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @patch("webhooks.premium_invalidate.get_premium_invalidate_secret", return_value=None)
    def test_invalid_json_returns_400(self, _mock_secret):
        response = client.post(
            "/webhooks/premium-invalidate",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


class TestFounderWebhook:
    """Tests for POST /webhooks/founder."""

    @patch("webhooks.founder.get_founder_webhook_secret", return_value=None)
    def test_missing_user_id_returns_400(self, _mock_secret):
        response = client.post(
            "/webhooks/founder",
            content='{"message": "Hi"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "user_id" in response.json().get("detail", "").lower()

    @patch("webhooks.founder.get_founder_webhook_secret", return_value=None)
    def test_invalid_user_id_returns_400(self, _mock_secret):
        response = client.post(
            "/webhooks/founder",
            content='{"user_id": "nope"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @patch("webhooks.founder.get_founder_webhook_secret", return_value=None)
    @patch("gpt.helpers.bot_instance", None)
    def test_returns_503_when_bot_not_available(self, _mock_secret):
        response = client.post(
            "/webhooks/founder",
            content='{"user_id": 12345}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 503
        assert "bot" in response.json().get("detail", "").lower() or "available" in response.json().get("detail", "").lower()

    @patch("webhooks.founder.get_founder_webhook_secret", return_value=None)
    @patch("webhooks.founder.asyncio.run_coroutine_threadsafe")
    def test_returns_200_when_dm_sent(self, mock_threadsafe, _mock_secret):
        future = Future()
        future.set_result(True)
        mock_threadsafe.return_value = future
        mock_bot = MagicMock()
        mock_bot.loop = MagicMock()
        with patch("gpt.helpers.bot_instance", mock_bot):
            response = client.post(
                "/webhooks/founder",
                content='{"user_id": 98765}',
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 200
        assert response.json() == {"status": "acknowledged", "user_id": "98765"}
        mock_threadsafe.assert_called_once()

    @patch("webhooks.founder.get_founder_webhook_secret", return_value=None)
    @patch("webhooks.founder.asyncio.run_coroutine_threadsafe")
    def test_accepts_optional_custom_message(self, mock_threadsafe, _mock_secret):
        future = Future()
        future.set_result(True)
        mock_threadsafe.return_value = future
        mock_bot = MagicMock()
        mock_bot.loop = MagicMock()
        with patch("gpt.helpers.bot_instance", mock_bot):
            response = client.post(
                "/webhooks/founder",
                content='{"user_id": 1, "message": "Custom welcome!"}',
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 200
        assert response.json()["user_id"] == "1"
        mock_threadsafe.assert_called_once()
