"""
Context loader for GPT personalization using App reflections.

Loads recent reflections from reflections_shared table for users who have
opted in to share their reflections with the Discord bot.
"""

from __future__ import annotations

import logging
from typing import Optional

from utils.supabase_client import _supabase_get, get_user_id_for_discord

logger = logging.getLogger(__name__)


async def load_user_reflections(
    discord_id: int | str,
    limit: int = 5,
) -> str:
    """
    Load recent reflections for a Discord user to use as GPT context.
    
    Args:
        discord_id: Discord user ID
        limit: Maximum number of reflections to load (default: 5)
    
    Returns:
        Formatted context string with reflections, or empty string if:
        - User hasn't opted in (bot_sharing_enabled = false)
        - No reflections found
        - Error occurred (logged but not raised)
    """
    try:
        # First, get Supabase user_id from Discord ID
        user_id = await get_user_id_for_discord(discord_id)
        if not user_id:
            logger.debug(
                f"No Supabase profile linked to discord_id={discord_id} - skipping reflection context"
            )
            return ""
        
        # Check if user has opted in to sharing
        profile_rows = await _supabase_get(
            "profiles",
            {
                "select": "bot_sharing_enabled",
                "user_id": f"eq.{user_id}",
                "limit": 1,
            },
        )
        
        if not profile_rows:
            logger.debug(f"No profile found for user_id={user_id}")
            return ""
        
        bot_sharing_enabled = profile_rows[0].get("bot_sharing_enabled", False)
        if not bot_sharing_enabled:
            logger.debug(
                f"User {user_id} (discord_id={discord_id}) has not opted in to reflection sharing"
            )
            return ""
        
        # Fetch recent reflections from reflections_shared table
        reflection_rows = await _supabase_get(
            "reflections_shared",
            {
                "select": "reflection_text,mantra,thoughts,future_message,date",
                "user_id": f"eq.{user_id}",
                "order": "date.desc",
                "limit": limit,
            },
        )
        
        if not reflection_rows:
            logger.debug(f"No shared reflections found for user_id={user_id}")
            return ""
        
        # Format reflections as context string
        context_parts = [
            "Recent reflections from the user:",
            "",
        ]
        
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
            f"Loaded {len(reflection_rows)} reflections for user_id={user_id} (discord_id={discord_id})"
        )
        return context_str
        
    except Exception as e:
        logger.warning(
            f"Failed to load reflection context for discord_id={discord_id}: {e}",
            exc_info=True,
        )
        # Return empty string on error - don't break GPT calls
        return ""


__all__ = ["load_user_reflections"]
