from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

import httpx

import config

logger = logging.getLogger(__name__)

SUPABASE_URL = (config.SUPABASE_URL or "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = config.SUPABASE_SERVICE_ROLE_KEY


class SupabaseConfigurationError(RuntimeError):
    """Raised when Supabase credentials are missing."""


def _require_config() -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise SupabaseConfigurationError(
            "Supabase URL/service role key not configured. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )


def _headers(prefer: Optional[Iterable[str]] = None) -> Dict[str, str]:
    header = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        header["Prefer"] = ", ".join(prefer)
    return header


async def _supabase_post(
    table: str,
    payload: Dict[str, Any] | List[Dict[str, Any]],
    *,
    upsert: bool = False,
) -> List[Dict[str, Any]]:
    """Insert or upsert records using the Supabase REST endpoint."""
    _require_config()
    rows: List[Dict[str, Any]] = (
        payload if isinstance(payload, list) else [payload]
    )

    if not rows:
        return []

    prefer: List[str] = ["return=representation"]
    if upsert:
        prefer.append("resolution=merge-duplicates")

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            url,
            json=rows,
            headers=_headers(prefer),
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:  # pragma: no cover - network path
        logger.error(
            "Supabase POST failed: table=%s status=%s body=%s",
            table,
            exc.response.status_code,
            exc.response.text,
        )
        raise

    if not response.content:
        return []

    data = response.json()
    if isinstance(data, dict):
        # REST can return {"data": [...]} depending on headers
        return data.get("data", [])
    return data


async def upsert_profile(payload: Dict[str, Any]) -> None:
    """Upsert a profile record keyed by user_id."""
    await _supabase_post("profiles", payload, upsert=True)


async def insert_reflection(payload: Dict[str, Any]) -> None:
    await _supabase_post("reflections", payload, upsert=False)


async def insert_trade(payload: Dict[str, Any]) -> None:
    await _supabase_post("trades", payload, upsert=False)


async def insert_insight(payload: Dict[str, Any]) -> None:
    await _supabase_post("insights", payload, upsert=False)


__all__ = [
    "upsert_profile",
    "insert_reflection",
    "insert_trade",
    "insert_insight",
    "SupabaseConfigurationError",
]
