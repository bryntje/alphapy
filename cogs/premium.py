"""Premium tier: /premium command and admin /premium_check."""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.premium_guard import (
    is_premium,
    get_premium_status,
    get_active_premium_guild,
    transfer_premium_to_guild,
)
from utils.timezone import BRUSSELS_TZ
from utils.validators import validate_admin
from version import __version__, CODENAME

logger = logging.getLogger(__name__)


class PremiumCog(commands.Cog):
    """Premium tier UX: pricing embed and checkout."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # This cog does not use guild settings (SettingsService); premium state is from premium_guard/DB.

    @app_commands.command(
        name="premium",
        description="See Premium pricing and features. Mature enough?",
    )
    async def premium(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        embed = discord.Embed(
            title="⚡ Premium — real power",
            description="Mature enough? Get the full stack.",
            color=discord.Color.blue(),
            timestamp=datetime.now(BRUSSELS_TZ),
        )
        embed.add_field(
            name="✨ Features",
            value=(
                "• Reminders with images and banners\n"
                "• Live session presets (with image support)\n"
                "• Mockingbird spicy mode in growth check-ins"
            ),
            inline=False,
        )
        embed.add_field(
            name="📍 How it works",
            value=(
                "Premium applies to **one server**.\n"
                "Pay once → choose where you want full Mockingbird power, vision verification, and image reminders.\n"
                "Want to switch servers later? Use `/premium_transfer` in the server you want, or ask us (dashboard coming later)."
            ),
            inline=False,
        )
        embed.add_field(
            name="💰 Pricing",
            value=(
                "• **€4.99** / month\n"
                "• **€29** / year (early bird)\n"
                "• **€49** lifetime (first 50 members only)"
            ),
            inline=False,
        )
        embed.set_footer(text=f"v{__version__} — {CODENAME}")

        view = None
        checkout_url = getattr(config, "PREMIUM_CHECKOUT_URL", "") or ""
        if checkout_url:
            view = discord.ui.View()
            view.add_item(
                discord.ui.Button(
                    label="Get Premium",
                    url=checkout_url,
                    style=discord.ButtonStyle.link,
                )
            )
        else:
            view = discord.ui.View()
            view.add_item(
                discord.ui.Button(
                    label="Coming soon",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                )
            )

        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(
        name="premium_check",
        description="(Admin) Check if a user has premium in this guild.",
    )
    @app_commands.describe(user="User to check (default: yourself)")
    async def premium_check(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        await validate_admin(interaction, raise_on_fail=True)
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return
        target = user or interaction.user
        premium = await is_premium(target.id, interaction.guild.id)
        await interaction.response.send_message(
            f"**Premium:** `{str(premium).lower()}` for {target.mention} in this guild.",
            ephemeral=True,
        )

    @app_commands.command(
        name="my_premium",
        description="Check your Premium status and expiry in this server.",
    )
    async def my_premium(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        status = await get_premium_status(interaction.user.id, interaction.guild.id)
        if status["premium"]:
            tier = status.get("tier") or "premium"
            expires = status.get("expires_at")
            if expires:
                try:
                    exp_str = expires.astimezone(BRUSSELS_TZ).strftime("%d %B %Y at %H:%M")
                except Exception:
                    exp_str = str(expires)
                msg = f"You have **Premium** ({tier}) in this server until **{exp_str}**."
            else:
                msg = f"You have **Premium** ({tier}) in this server (no expiry)."
        else:
            msg = "You don't have Premium in this server. Get power with /premium."
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(
        name="premium_transfer",
        description="Move your Premium to this server (one subscription per account).",
    )
    async def premium_transfer(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        current_guild = await get_active_premium_guild(user_id)
        if current_guild is None:
            await interaction.followup.send(
                "You don't have an active Premium subscription to transfer. Get power with /premium.",
                ephemeral=True,
            )
            return
        if current_guild == guild_id:
            await interaction.followup.send(
                "Your Premium is already active in this server.",
                ephemeral=True,
            )
            return
        ok, reason = await transfer_premium_to_guild(user_id, guild_id)
        if ok:
            await interaction.followup.send(
                "Premium is now active in this server.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Transfer failed: {reason}. Try again or contact support.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PremiumCog(bot))
