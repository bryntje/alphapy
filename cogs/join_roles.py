import discord
from discord.ext import commands

from utils.logger import logger, log_with_guild


class JoinRoleCog(commands.Cog):
    """Assign a configurable join role when a new member joins a guild."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        settings = getattr(bot, "settings", None)
        if settings is None or not hasattr(settings, "get"):
            raise RuntimeError("SettingsService not available on bot instance")
        self.settings = settings  # type: ignore

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Assign onboarding.join_role_id to new human members when they join."""
        if member.bot:
            return

        guild = member.guild
        guild_id = guild.id

        try:
            enabled = self.settings.get("onboarding", "enabled", guild_id)
        except Exception:
            enabled = False

        if not enabled:
            return

        try:
            join_role_id = self.settings.get("onboarding", "join_role_id", guild_id)
        except Exception:
            join_role_id = 0

        if not join_role_id or join_role_id == 0:
            return

        role = guild.get_role(int(join_role_id))
        if role is None:
            log_with_guild(
                f"JoinRoleCog: configured join_role_id={join_role_id} not found in guild",
                guild_id,
                "warning",
            )
            return

        if any(r.id == role.id for r in member.roles):
            return

        try:
            await member.add_roles(role, reason="Join role assignment")
            log_with_guild(
                f"JoinRoleCog: assigned join role {role.id} to member {member.id}",
                guild_id,
                "info",
            )
        except Exception as e:
            logger.warning(f"JoinRoleCog: could not assign join role {role.id} to {member.id}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinRoleCog(bot))

