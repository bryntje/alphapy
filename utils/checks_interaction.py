# utils/checks_interaction.py
import discord
import config

async def is_owner_or_admin_interaction(interaction: discord.Interaction) -> bool:
    user = interaction.user
    if user.id in config.OWNER_IDS:
        return True
    if user.guild_permissions.administrator:
        return True
    admin_role = discord.utils.get(user.roles, id=config.ADMIN_ROLE_ID)
    return admin_role is not None
