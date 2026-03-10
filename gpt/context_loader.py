"""
Context loader for Grok personalization using App reflections.

Loads recent reflections from:
- Supabase reflections_shared (for users who opted in via bot_sharing_enabled)
- app_reflections (plaintext from App via Core webhook, last 30 days)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from utils.db_helpers import PoolT
from utils.supabase_client import _supabase_get, get_user_id_for_discord
from utils.sanitizer import safe_prompt

logger = logging.getLogger(__name__)

# Pool for app_reflections (PostgreSQL); created on first use
_app_reflections_pool: Optional[PoolT] = None
_app_reflections_pool_lock = asyncio.Lock()
_REFLECTION_TEXT_MAX_CHARS = 2048
_REFLECTION_DATE_MAX_CHARS = 128


def _sanitize_reflection_field(value: object, max_chars: int = _REFLECTION_TEXT_MAX_CHARS) -> str:
    """Normalize reflection content before injecting into LLM context."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return safe_prompt(text[:max_chars])


async def _get_app_reflections_pool() -> Optional[PoolT]:
    """Get the shared pool from api.py instead of creating a new one."""
    try:
        from api import app
        return app.state.db_pool
    except (ImportError, AttributeError) as e:
        logger.debug("Could not access shared db_pool from api: %s", e)
        return None


async def _load_app_reflections(discord_id: int | str, limit: int = 5) -> str:
    """
    Load recent reflections from app_reflections (plaintext from App via Core webhook).
    Returns formatted context string or empty string.
    """
    try:
        pool = await _get_app_reflections_pool()
        if not pool:
            return ""
        discord_id_int = int(discord_id)
        from utils.db_helpers import acquire_safe

        async with acquire_safe(pool) as conn:
            rows = await conn.fetch(
                """
                SELECT plaintext_content, created_at
                FROM app_reflections
                WHERE user_id = $1
                  AND created_at >= NOW() - interval '30 days'
                ORDER BY created_at DESC
                LIMIT $2
                """,
                discord_id_int,
                limit,
            )
        if not rows:
            return ""
        blocks: list[str] = []
        display_idx = 0
        for row in rows:
            content = row["plaintext_content"]
            created = row["created_at"]
            date_str = created.strftime("%Y-%m-%d") if created else ""
            # JSONB may be returned as str by asyncpg when no custom codec is used
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (ValueError, TypeError):
                    continue
            if not isinstance(content, dict):
                continue
            display_idx += 1
            blocks.append(f"Reflection {display_idx} ({date_str}):")
            for key in ("reflection_text", "reflection", "mantra", "thoughts", "future_message"):
                val = content.get(key)
                safe_val = _sanitize_reflection_field(val)
                if safe_val:
                    label = key.replace("_", " ").title()
                    blocks.append(f"  {label}: {safe_val}")
            date_val = content.get("date")
            safe_date = _sanitize_reflection_field(date_val, max_chars=_REFLECTION_DATE_MAX_CHARS)
            if safe_date:
                blocks.append(f"  Date: {safe_date}")
            blocks.append("")
        if not blocks:
            return ""
        return "Recent reflections from the App (shared via webhook):\n\n" + "\n".join(blocks).strip()
    except Exception as e:
        logger.debug("Failed to load app_reflections for discord_id=%s: %s", discord_id, e)
        return ""


async def load_user_reflections(
    discord_id: int | str,
    limit: int = 5,
) -> str:
    """
    Load recent reflections for a Discord user to use as Grok context.
    
    Args:
        discord_id: Discord user ID
        limit: Maximum total number of reflections to load across all sources
               (default: 5)
    
    Returns:
        Formatted context string with reflections, or empty string if:
        - User hasn't opted in (bot_sharing_enabled = false)
        - No reflections found
        - Error occurred (logged but not raised)
    """
    context_str = ""
    loaded_count = 0
    if limit <= 0:
        return ""
    try:
        # Supabase: get user_id and check bot_sharing_enabled
        user_id = await get_user_id_for_discord(discord_id)
        if not user_id:
            logger.debug(
                "No Supabase profile linked to discord_id=%s - skipping Supabase reflection context",
                discord_id,
            )
        else:
            profile_rows = await _supabase_get(
                "profiles",
                {
                    "select": "bot_sharing_enabled",
                    "user_id": f"eq.{user_id}",
                    "limit": 1,
                },
            )
            if not profile_rows:
                logger.debug("No profile found for user_id=%s", user_id)
            else:
                bot_sharing_enabled = profile_rows[0].get("bot_sharing_enabled", False)
                if not bot_sharing_enabled:
                    logger.debug(
                        "User %s (discord_id=%s) has not opted in to reflection sharing",
                        user_id,
                        discord_id,
                    )
                else:
                    reflection_rows = await _supabase_get(
                        "reflections_shared",
                        {
                            "select": "reflection_text,mantra,thoughts,future_message,date",
                            "user_id": f"eq.{user_id}",
                            "order": "date.desc",
                            "limit": limit,
                        },
                    )
                    if reflection_rows:
                        context_parts = ["Recent reflections from the user:", ""]
                        for idx, reflection in enumerate(reflection_rows, 1):
                            date_str = _sanitize_reflection_field(
                                reflection.get("date", ""),
                                max_chars=_REFLECTION_DATE_MAX_CHARS,
                            )
                            reflection_text = _sanitize_reflection_field(reflection.get("reflection_text", ""))
                            mantra = _sanitize_reflection_field(reflection.get("mantra"))
                            thoughts = _sanitize_reflection_field(reflection.get("thoughts"))
                            future_message = _sanitize_reflection_field(reflection.get("future_message"))
                            context_parts.append(f"Reflection {idx} ({date_str}):")
                            if reflection_text:
                                context_parts.append(f"  Reflection: {reflection_text}")
                            if mantra:
                                context_parts.append(f"  Mantra: {mantra}")
                            if thoughts:
                                context_parts.append(f"  Thoughts: {thoughts}")
                            if future_message:
                                context_parts.append(f"  Future message: {future_message}")
                            context_parts.append("")
                        context_str = "\n".join(context_parts)
                        loaded_count = len(reflection_rows)
                        logger.debug(
                            "Loaded %s Supabase reflections for user_id=%s (discord_id=%s)",
                            len(reflection_rows),
                            user_id,
                            discord_id,
                        )
                    else:
                        logger.debug("No shared reflections found for user_id=%s", user_id)
    except Exception as e:
        logger.warning(
            "Failed to load Supabase reflection context for discord_id=%s: %s",
            discord_id,
            e,
            exc_info=True,
        )

    # Always try app_reflections (plaintext from App via Core webhook), but
    # enforce the global limit across both sources.
    remaining_limit = max(limit - loaded_count, 0)
    if remaining_limit > 0:
        app_context = await _load_app_reflections(discord_id, limit=remaining_limit)
        if app_context:
            context_str = f"{context_str}\n\n{app_context}".strip() if context_str else app_context
    else:
        logger.debug(
            "Skipping app_reflections for discord_id=%s because limit=%s is already reached",
            discord_id,
            limit,
        )

    return context_str or ""


__all__ = ["load_user_reflections"]
