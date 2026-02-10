from __future__ import annotations

import logging
from datetime import datetime, timezone
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


def _headers(prefer: Optional[Iterable[str]] = None, schema: Optional[str] = None, method: str = "GET") -> Dict[str, str]:
    header = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        header["Prefer"] = ", ".join(prefer)
    # For custom schemas with PostgREST:
    # - GET requests use Accept-Profile header
    # - POST/PUT/PATCH requests use Content-Profile header
    # - Some implementations require both headers for POST requests
    if schema:
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            header["Content-Profile"] = schema
            # Also set Accept-Profile for POST to ensure schema is recognized
            header["Accept-Profile"] = schema
        else:
            header["Accept-Profile"] = schema
    return header


async def _supabase_get(
    table: str, params: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Fetch rows from a Supabase table using the service role."""
    _require_config()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=_headers(), params=params)

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:  # pragma: no cover - network path
        logger.error(
            "Supabase GET failed: table=%s status=%s body=%s",
            table,
            exc.response.status_code,
            exc.response.text,
        )
        raise

    data = response.json()
    if isinstance(data, dict):
        return data.get("data", [])
    if isinstance(data, list):
        return data
    return []


async def _supabase_post(
    table: str,
    payload: Dict[str, Any] | List[Dict[str, Any]],
    *,
    upsert: bool = False,
    schema: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Insert or upsert records using the Supabase REST endpoint.
    
    Args:
        table: Table name (without schema prefix if using schema parameter)
        payload: Data to insert/upsert
        upsert: Whether to upsert on conflict
        schema: Optional schema name (e.g., 'telemetry'). If provided, uses Accept-Profile header
               and table name should NOT include schema prefix.
    """
    _require_config()
    rows: List[Dict[str, Any]] = (
        payload if isinstance(payload, list) else [payload]
    )

    if not rows:
        return []

    prefer: List[str] = ["return=representation"]
    if upsert:
        prefer.append("resolution=merge-duplicates")

    # For PostgREST with custom schemas, use ONLY the header approach
    # Do NOT include schema in URL when using Content-Profile/Accept-Profile headers
    # Format: /rest/v1/table_name (no schema prefix)
    # Headers: Content-Profile: schema (for POST/PUT/PATCH)
    table_name = table
    if schema and "." in table:
        # Remove schema prefix if present (e.g., "telemetry.subsystem_snapshots" -> "subsystem_snapshots")
        table_name = table.split(".", 1)[1]
    elif not schema and "." in table:
        # If no schema specified but table has dot, assume it's schema.table format
        # Extract schema and table name
        parts = table.split(".", 1)
        schema = parts[0]
        table_name = parts[1]
    
    # Use ONLY table name in URL (no schema prefix) when using Content-Profile header
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            url,
            json=rows,
            headers=_headers(prefer, schema=schema, method="POST"),
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


async def get_user_id_for_discord(discord_id: str | int) -> Optional[str]:
    """Resolve a Supabase user_id via the profiles table using a Discord id."""
    try:
        rows = await _supabase_get(
            "profiles",
            {
                "select": "user_id,discord_id",
                "discord_id": f"eq.{discord_id}",
                "limit": 1,
            },
        )
    except httpx.HTTPStatusError:
        return None

    if not rows:
        return None

    user_id = rows[0].get("user_id")
    return str(user_id) if user_id else None


async def get_discord_id_for_user(user_id: str) -> Optional[str]:
    """Resolve a Discord id via the profiles table using a Supabase user_id."""
    try:
        rows = await _supabase_get(
            "profiles",
            {
                "select": "discord_id",
                "user_id": f"eq.{user_id}",
                "limit": 1,
            },
        )
    except httpx.HTTPStatusError:
        return None

    if not rows:
        return None

    discord_id = rows[0].get("discord_id")
    return str(discord_id) if discord_id else None


async def insert_reflection_for_discord(
    discord_id: int | str,
    *,
    reflection: str,
    mantra: Optional[str] = None,
    villain: Optional[str] = None,
    future_message: Optional[str] = None,
    date: Optional[datetime] = None,
) -> bool:
    """Insert a reflection entry for the Supabase user linked to the Discord id."""
    user_id = await get_user_id_for_discord(discord_id)
    if not user_id:
        logger.debug(
            "No Supabase profile linked to discord_id=%s – skipping reflection insert.",
            discord_id,
        )
        return False

    timestamp = date or datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "date": timestamp.isoformat(),
        "reflection": reflection,
    }
    if mantra:
        payload["mantra"] = mantra
    if villain:
        payload["villain"] = villain
    if future_message:
        payload["future_message"] = future_message

    await insert_reflection(payload)
    return True


async def insert_insight_for_discord(
    discord_id: int | str,
    *,
    summary: str,
    source: str = "system",
    tags: Optional[List[str]] = None,
) -> bool:
    """Insert an insight entry linked to the Supabase user for the Discord id."""

    user_id = await get_user_id_for_discord(discord_id)
    if not user_id:
        logger.debug(
            "No Supabase profile linked to discord_id=%s – skipping insight insert.",
            discord_id,
        )
        return False

    payload = {
        "user_id": user_id,
        "summary": summary,
        "source": source,
    }
    if tags:
        payload["tags"] = tags

    await insert_insight(payload)
    return True


__all__ = [
    "upsert_profile",
    "insert_reflection",
    "insert_trade",
    "insert_insight",
    "get_user_id_for_discord",
    "get_discord_id_for_user",
    "insert_reflection_for_discord",
    "insert_insight_for_discord",
    "SupabaseConfigurationError",
]
