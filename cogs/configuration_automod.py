"""
Automod config helper functions for the Configuration cog.

These are pure helper functions (no command registration) extracted from
the Configuration class to keep configuration.py focused on command wiring.
"""

from typing import Any

import discord

from utils.automod_rules import ActionType, RuleType
from utils.premium_guard import guild_has_premium


def normalize_automod_action_type(action_type: str) -> str | None:
    """Return the canonical action type string, or None if not recognized."""
    normalized = action_type.lower().strip()
    if normalized in {
        ActionType.DELETE.value,
        ActionType.WARN.value,
        ActionType.MUTE.value,
        ActionType.TIMEOUT.value,
        ActionType.BAN.value,
    }:
        return normalized
    return None


def is_advanced_action(action_type: str) -> bool:
    """Return True for actions that require guild premium (timeout, ban)."""
    return action_type in {ActionType.TIMEOUT.value, ActionType.BAN.value}


async def check_advanced_action_premium(
    interaction: discord.Interaction,
    action_type: str,
) -> bool:
    """
    Gate advanced actions (timeout/ban) behind guild premium.
    Sends an ephemeral error and returns False if the guild lacks premium.
    """
    if not interaction.guild:
        return False
    if not is_advanced_action(action_type):
        return True
    has_premium = await guild_has_premium(interaction.guild.id)
    if has_premium:
        return True
    await interaction.response.send_message(
        "❌ Timeout and ban actions require an active premium subscription for this guild.",
        ephemeral=True,
    )
    return False


def validate_rule_update_fields(
    rule_type: str,
    config: dict[str, Any],
    requested_fields: dict[str, bool],
) -> str | None:
    """
    Return an error string if any of the requested update fields are not valid
    for the given rule type/config combination, or None if all fields are valid.
    """
    if rule_type == RuleType.SPAM.value:
        spam_type = str(config.get("spam_type", "frequency"))
        if spam_type == "frequency":
            allowed = {"max_messages", "time_window_seconds"}
        elif spam_type == "duplicate":
            allowed = {"max_duplicates"}
        elif spam_type == "caps":
            allowed = {"min_length", "max_caps_ratio"}
        else:
            allowed = set()
    elif rule_type == RuleType.CONTENT.value:
        content_type = str(config.get("content_type", "bad_words"))
        if content_type == "bad_words":
            allowed = {"words"}
        elif content_type == "links":
            allowed = {"allow_links", "whitelist", "blacklist"}
        elif content_type == "mentions":
            allowed = {"max_mentions"}
        else:
            allowed = set()
    elif rule_type == RuleType.REGEX.value:
        allowed = {"patterns"}
    else:
        allowed = set()

    invalid = sorted([name for name, present in requested_fields.items() if present and name not in allowed])
    if invalid:
        return f"❌ These fields are not valid for this rule type/config: {', '.join(invalid)}."
    return None
