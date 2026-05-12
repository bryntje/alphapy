"""Tests for Core Discord link-session URL extraction."""

from utils.core_discord_integration import extract_link_url


def test_extract_link_url_prefers_link_url() -> None:
    assert extract_link_url({"link_url": "https://app.example/link"}) == "https://app.example/link"


def test_extract_link_url_falls_back_to_url() -> None:
    assert extract_link_url({"url": "https://core.example/session"}) == "https://core.example/session"


def test_extract_link_url_none_when_missing() -> None:
    assert extract_link_url({}) is None
    assert extract_link_url(None) is None
