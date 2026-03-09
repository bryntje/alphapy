"""
Context loader for Grok personalization using App reflections.

Loads recent reflections from:
- Supabase reflections_shared (for users who opted in via bot_sharing_enabled)
- app_reflections (plaintext from App via Core webhook, last 30 days)
"""

from __future__ import annotations

import logging
from typing import Optional

from utils.supabase_client import _supabase_get, get_user_id_for_discord

logger = logging.getLogger(__name__)

# Pool for app_reflections (PostgreSQL); created on first use
_app_reflections_pool = None


async def _get_app_reflections_pool():
    """Lazy-create pool for app_reflections queries (bot context)."""
    global _app_reflections_pool
    if _app_reflections_pool is not None and not _app_reflections_pool.is_closing():
        return _app_reflections_pool
    try:
        from utils.db_helpers import create_db_pool

        try:
            import config_local as config  # type: ignore
        except ImportError:
            import config  # type: ignore

        dsn = getattr(config, "DATABASE_URL", None) or ""
        if not dsn:
            return None
        _app_reflections_pool = await create_db_pool(
            dsn,
            name="context_loader_app_reflections",
            min_size=1,
            max_size=5,
            command_timeout=10.0,
        )
        return _app_reflections_pool
    except Exception as e:
        logger.debug("Could not create app_reflections pool for context: %s", e)
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
        parts = ["Recent reflections from the App (shared via webhook):", ""]
        for idx, row in enumerate(rows, 1):
            content = row["plaintext_content"]
            created = row["created_at"]
            date_str = created.strftime("%Y-%m-%d") if created else ""
            if not isinstance(content, dict):
                continue
            parts.append(f"Reflection {idx} ({date_str}):")
            for key in ("reflection_text", "reflection", "mantra", "thoughts", "future_message"):
                val = content.get(key)
                if val:
                    label = key.replace("_", " ").title()
                    parts.append(f"  {label}: {val}")
            if content.get("date"):
                parts.append(f"  Date: {content['date']}")
            parts.append("")
        return "\n".join(parts).strip() or ""
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
        limit: Maximum number of reflections to load (default: 5)
    
    Returns:
        Formatted context string with reflections, or empty string if:
        - User hasn't opted in (bot_sharing_enabled = false)
        - No reflections found
        - Error occurred (logged but not raised)
    """
    context_str = ""
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
                            date_str = reflection.get("date", "")
                            reflection_text = reflection.get("reflection_text", "")
                            mantra = reflection.get("mantra")
                            thoughts = reflection.get("thoughts")
                            future_message = reflection.get("future_message")
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

    # Always try app_reflections (plaintext from App via Core webhook)
    app_context = await _load_app_reflections(discord_id, limit=limit)
    if app_context:
        context_str = f"{context_str}\n\n{app_context}".strip() if context_str else app_context

    return context_str or ""


__all__ = ["load_user_reflections"]
