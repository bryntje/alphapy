# utils/checks_interaction.py
import discord
import config

async def is_owner_or_admin_interaction(interaction: discord.Interaction) -> bool:
    user = interaction.user

    if user.id in config.OWNER_IDS:
        return True

    permissions = getattr(user, "guild_permissions", None)
    if permissions and permissions.administrator:
        return True

    admin_role_ids = config.ADMIN_ROLE_ID
    if isinstance(admin_role_ids, int):
        admin_role_ids = [admin_role_ids]
    elif not isinstance(admin_role_ids, (list, tuple, set)):
        admin_role_ids = [admin_role_ids]

    user_roles = getattr(user, "roles", [])
    return any(role.id in admin_role_ids for role in user_roles)
