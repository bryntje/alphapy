"""Tests for Core Discord link-session URL extraction."""

import pytest

from utils.core_discord_integration import extract_link_url


def test_extract_link_url_prefers_link_url() -> None:
    assert extract_link_url({"link_url": "https://app.example/link"}) == "https://app.example/link"


def test_extract_link_url_falls_back_to_url() -> None:
    assert extract_link_url({"url": "https://core.example/session"}) == "https://core.example/session"


def test_extract_link_url_none_when_missing() -> None:
    assert extract_link_url({}) is None
    assert extract_link_url(None) is None


def test_extract_link_url_authorize_url() -> None:
    assert extract_link_url({"authorize_url": "https://a.example/z"}) == "https://a.example/z"


@pytest.mark.asyncio
async def test_request_discord_link_session_none_without_core_url(monkeypatch) -> None:
    import utils.core_discord_integration as cdi

    monkeypatch.setattr(cdi.config, "CORE_API_URL", "")
    monkeypatch.setattr(cdi.config, "ALPHAPY_SERVICE_KEY", "k")
    out = await cdi.request_discord_link_session(123)
    assert out is None


@pytest.mark.asyncio
async def test_request_discord_link_session_none_without_service_key(monkeypatch) -> None:
    import utils.core_discord_integration as cdi

    monkeypatch.setattr(cdi.config, "CORE_API_URL", "https://core.example")
    monkeypatch.setattr(cdi.config, "ALPHAPY_SERVICE_KEY", "")
    out = await cdi.request_discord_link_session(123)
    assert out is None


@pytest.mark.asyncio
async def test_request_discord_link_session_parses_json(monkeypatch) -> None:
    import utils.core_discord_integration as cdi

    monkeypatch.setattr(cdi.config, "CORE_API_URL", "https://core.example")
    monkeypatch.setattr(cdi.config, "ALPHAPY_SERVICE_KEY", "secret")

    class _Resp:
        is_success = True
        status_code = 200
        text = ""

        def json(self):
            return {"link_url": "https://app.example/complete"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(cdi.httpx, "AsyncClient", _Client)
    out = await cdi.request_discord_link_session(42)
    assert out == {"link_url": "https://app.example/complete"}


@pytest.mark.asyncio
async def test_fetch_innersync_profile_for_discord(monkeypatch) -> None:
    import utils.core_discord_integration as cdi

    monkeypatch.setattr(cdi.config, "CORE_API_URL", "https://core.example")
    monkeypatch.setattr(cdi.config, "ALPHAPY_SERVICE_KEY", "secret")

    class _Resp:
        is_success = True
        status_code = 200
        text = ""

        def json(self):
            return {"display_name": "Pat", "avatar_url": "https://cdn.example/a.png"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(cdi.httpx, "AsyncClient", _Client)
    out = await cdi.fetch_innersync_profile_for_discord(9)
    assert out is not None
    assert out.get("display_name") == "Pat"
