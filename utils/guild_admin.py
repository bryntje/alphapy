"""Shared guild admin check logic for use in API and interaction contexts."""

from typing import Optional

import discord

import config


def member_has_admin_in_guild(
    member: discord.Member,
    app_owner_id: Optional[int] = None,
) -> bool:
    """
    Check if a Discord member has admin permissions in their guild.

    Args:
        member: The guild member to check
        app_owner_id: Optional bot application owner ID (from application_info())

    Returns:
        True if member is admin (owner IDs, administrator permission, admin role, or app owner)
    """
    if member.id in config.OWNER_IDS:
        return True
    if member.guild_permissions.administrator:
        return True
    admin_role_ids = config.ADMIN_ROLE_ID
    if isinstance(admin_role_ids, (list, tuple, set)):
        if any(r.id in admin_role_ids for r in member.roles):
            return True
    elif any(r.id == admin_role_ids for r in member.roles):
        return True
    if app_owner_id is not None and member.id == app_owner_id:
        return True
    return False
