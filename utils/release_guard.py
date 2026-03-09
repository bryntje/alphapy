"""
Optional sanity check: feature allowed only after 3.0.0 is published on GitHub.

Used as a mental reminder for the maintainer to rest; not core to feature logic.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = "https://api.github.com/repos/bryntje/alphapy/releases"
CACHE_TTL_SECONDS = 60 * 30  # 30 minutes
_ALLOWED_CACHE: Optional[tuple[bool, float]] = None  # (allowed, expires_at)


def _normalize_tag(tag: str) -> str:
    """Strip leading 'v' for comparison."""
    return tag.lstrip("v")


async def is_reflection_share_allowed() -> bool:
    """
    Return True if reflection sharing is allowed (3.0.0 release exists on GitHub).

    Caches the result for CACHE_TTL_SECONDS. On any failure (timeout, non-2xx,
    parse error), returns False (fail closed). Optional sanity check for maintainer.
    """
    global _ALLOWED_CACHE
    now = time.monotonic()
    if _ALLOWED_CACHE is not None:
        allowed, expires_at = _ALLOWED_CACHE
        if now < expires_at:
            return allowed
    try:
        token = getattr(config, "GITHUB_TOKEN", None) or None
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(GITHUB_RELEASES_URL, headers=headers)
        if response.status_code != 200:
            logger.debug(
                "Release guard: GitHub API returned status=%s",
                response.status_code,
            )
            _ALLOWED_CACHE = (False, now + CACHE_TTL_SECONDS)
            return False
        data = response.json()
        if not isinstance(data, list):
            _ALLOWED_CACHE = (False, now + CACHE_TTL_SECONDS)
            return False
        for release in data:
            tag = release.get("tag_name")
            if isinstance(tag, str) and _normalize_tag(tag) == "3.0.0":
                _ALLOWED_CACHE = (True, now + CACHE_TTL_SECONDS)
                return True
        _ALLOWED_CACHE = (False, now + CACHE_TTL_SECONDS)
        return False
    except Exception as e:
        logger.debug("Release guard: check failed (%s), treating as not allowed", e)
        _ALLOWED_CACHE = (False, now + CACHE_TTL_SECONDS)
        return False


__all__ = ["is_reflection_share_allowed"]
