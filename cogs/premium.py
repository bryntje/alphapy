"""Premium tier: /premium command and admin /premium_check."""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
import httpx
import asyncpg
from datetime import datetime
from typing import Optional

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

# Founder guild ID from environment (for founder role assignment)
FOUNDER_GUILD_ID = int(getattr(config, 'FOUNDER_GUILD_ID', 0))


class TermsAcceptanceView(discord.ui.View):
    """View with Accept/Decline buttons for Terms acceptance."""

    def __init__(self, user_id: int):
        super().__init__(timeout=300)  # 5 minutes
        self.user_id = user_id

    @discord.ui.button(label="✅ Accept Terms", style=discord.ButtonStyle.success, emoji="📋")
    async def accept_terms(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not for you!", ephemeral=True)
            return

        # Save acceptance to database
        cog = interaction.client.get_cog('PremiumCog')  # type: ignore
        if not cog:
            logger.error("PremiumCog not found for terms acceptance")
            await interaction.response.send_message(
                "❌ There was an error processing your acceptance. Please contact support@innersync.tech for assistance.",
                ephemeral=True
            )
            return

        try:
            await _save_terms_acceptance(cog, interaction.user.id, interaction.user.id)
            embed = discord.Embed(
                title="✅ Terms Accepted!",
                description="Thank you for accepting our Terms and Privacy Policy!\n\nYou can now access premium features.",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            logger.error(f"Failed to save terms acceptance for user {interaction.user.id}: {e}")
            await interaction.response.send_message(
                "❌ There was an error processing your acceptance. Please contact support@innersync.tech for assistance.",
                ephemeral=True
            )

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger, emoji="🚫")
    async def decline_terms(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not for you!", ephemeral=True)
            return

        embed = discord.Embed(
            title="❌ Terms Declined",
            description="You must accept our Terms and Privacy Policy to use premium features.\n\nYou can try again later with `/premium`.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)


async def _save_terms_acceptance(cog: 'PremiumCog', user_id: int, accepted_by: int) -> None:
    """Save terms acceptance to database for GDPR compliance."""
    from utils.database_helpers import DatabaseManager
    db_manager = DatabaseManager("premium", {"DATABASE_URL": config.DATABASE_URL})

    try:
        async with db_manager.connection() as conn:
            await conn.execute(
                "INSERT INTO terms_acceptance (user_id, accepted_at, version) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO NOTHING",
                user_id, datetime.utcnow(), "2025-02-27"
            )
        logger.info(f"Terms accepted by user {user_id}")
    except Exception as e:
        logger.error(f"Failed to save terms acceptance for user {user_id}: {e}")
        raise


async def _has_accepted_terms(cog: 'PremiumCog', user_id: int) -> bool:
    """Check if user has accepted current terms version."""
    from utils.database_helpers import DatabaseManager
    db_manager = DatabaseManager("premium", {"DATABASE_URL": config.DATABASE_URL})

    try:
        async with db_manager.connection() as conn:
            result = await conn.fetchval(
                "SELECT 1 FROM terms_acceptance WHERE user_id = $1 AND version = $2",
                user_id, "2025-02-27"
            )
        return result is not None
    except Exception as e:
        logger.error(f"Failed to check terms acceptance for user {user_id}: {e}")
        return False


async def _assign_founder_role_if_eligible(cog: 'PremiumCog', user_id: int, guild_id: int, tier: str) -> None:
    """Assign founder role to early bird lifetime members in founder guild."""
    # Only assign founder role in configured founder guild
    if guild_id != FOUNDER_GUILD_ID or FOUNDER_GUILD_ID == 0:
        return

    # Only lifetime tier gets founder role (early bird pricing)
    if tier != "lifetime":
        return

    # Get the guild and member efficiently
    guild = cog.bot.get_guild(FOUNDER_GUILD_ID)
    if not guild:
        logger.warning(f"Founder role: Could not find founder guild {FOUNDER_GUILD_ID}")
        return

    # Check bot permissions before attempting role assignment
    bot_member = guild.get_member(cog.bot.user.id)
    if not bot_member or not bot_member.guild_permissions.manage_roles:
        logger.warning(f"Founder role: Bot lacks manage_roles permission in founder guild {FOUNDER_GUILD_ID}")
        return

    member = guild.get_member(user_id)
    if not member:
        logger.warning(f"Founder role: Could not find member {user_id} in founder guild")
        return

    # Check if member already has founder role (avoid duplicate assignments)
    founder_role_name = getattr(config, 'FOUNDER_ROLE_NAME', 'Founder')
    founder_role = discord.utils.get(guild.roles, name=founder_role_name)
    if not founder_role:
        logger.warning(f"Founder role: '{founder_role_name}' role not found in founder guild {guild_id}")
        return

    # Check if bot can assign this role (role hierarchy)
    if founder_role.position >= bot_member.top_role.position:
        logger.warning(f"Founder role: Bot cannot assign '{founder_role_name}' role due to role hierarchy")
        return

    if founder_role in member.roles:
        logger.debug(f"Founder role: User {user_id} already has founder role")
        return

    # Assign the founder role with rate limiting consideration
    try:
        await member.add_roles(founder_role, reason="Early bird lifetime member - founder recognition")
        logger.info(f"Founder role: Assigned '{founder_role_name}' role to user {user_id} in founder guild")
    except discord.Forbidden:
        logger.error(f"Founder role: Forbidden - Bot lacks permission to assign role to user {user_id}")
    except discord.HTTPException as e:
        logger.error(f"Founder role: HTTP error assigning role to user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Founder role: Unexpected error assigning role to user {user_id}: {e}")


async def _create_checkout_url(tier: str, guild_id: int, user_id: int) -> str | None:
    """Create a Lemon Squeezy checkout URL via Core API."""
    core_url = getattr(config, "CORE_API_URL", "") or ""
    api_key = getattr(config, "ALPHAPY_SERVICE_KEY", None)
    if not core_url or not api_key:
        logger.warning(f"Premium checkout: CORE_API_URL or ALPHAPY_SERVICE_KEY not configured (core_url: {bool(core_url)}, api_key: {bool(api_key)})")
        return None
    endpoint = f"{core_url}/api/premium/checkout"
    params = {"tier": tier, "guild_id": guild_id, "user_id": user_id}
    headers = {"X-API-Key": api_key}
    try:
        logger.debug(f"Premium checkout: Calling {endpoint} with tier={tier}, guild_id={guild_id}")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(endpoint, params=params, headers=headers)
            if response.is_success:
                data = response.json()
                checkout_url = data.get("checkout_url")
                logger.debug(f"Premium checkout: Got URL for {tier}: {bool(checkout_url)}")
                return checkout_url
            else:
                logger.warning(f"Premium checkout: Core-API returned {response.status_code}: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Premium checkout: Exception calling Core-API: {e}")
        return None


class PremiumCog(commands.Cog):
    """Premium tier UX: pricing embed and checkout."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None
        from utils.database_helpers import DatabaseManager
        self._db_manager = DatabaseManager("premium", {"DATABASE_URL": config.DATABASE_URL or ""})
        self.bot.loop.create_task(self._connect_database())

    async def _connect_database(self) -> None:
        """Initialize database connection pool for premium features."""
        try:
            self.db = await self._db_manager.ensure_pool()
            logger.info("Premium cog: Database pool created")
        except Exception as e:
            logger.error(f"Premium cog: Failed to create database pool: {e}")
            return

    @app_commands.command(
        name="premium",
        description="See Premium pricing and features. Powerful enough?",
    )
    async def premium(self, interaction: discord.Interaction) -> None:
        # Check if user has accepted terms
        if not await _has_accepted_terms(self, interaction.user.id):
            # Show terms acceptance embed with buttons
            embed = discord.Embed(
                title="📋 Terms & Privacy Policy",
                description=(
                    "To access premium features, you must accept our Terms of Service and Privacy Policy.\n\n"
                    "📄 [Terms of Service](https://docs.alphapy.innersync.tech/terms-of-service/)\n"
                    "🔒 [Privacy Policy](https://docs.alphapy.innersync.tech/privacy-policy/)\n\n"
                    "Please review these documents and click Accept below."
                ),
                color=discord.Color.blue()
            )
            view = TermsAcceptanceView(interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        embed = discord.Embed(
            title="⚡ Premium — real power",
            description="Powerful enough? Get the full stack.",
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
        guild_id = interaction.guild.id if interaction.guild else 0
        how_it_works = (
            "Premium applies to **one server**.\n"
            "Pay once → choose where you want full Mockingbird power, vision verification, and image reminders.\n"
            "Want to switch servers later? Use `/premium_transfer` in the server you want, or ask us (dashboard coming later)."
        )
        if guild_id != 0:
            how_it_works += f"\n\n**This purchase will apply Premium to **this server** ({interaction.guild.name}).**"
        else:
            how_it_works += "\n\n**You'll choose your server after payment via `/premium_transfer`.**"
        embed.add_field(
            name="📍 How it works",
            value=how_it_works,
            inline=False,
        )
        embed.set_footer(text=f"v{__version__} — {CODENAME}")

        # Premium is now live with Core-API integration!
        embed.add_field(
            name="🎉 Premium is Live!",
            value="Choose your plan below. Early bird pricing available for the first 50 lifetime members!",
            inline=False,
        )

        # Premium is now live with Core-API integration!
        # Create real checkout URLs for each tier
        guild_id = interaction.guild.id if interaction.guild else 0
        user_id = interaction.user.id
        checkout_urls = {}
        tiers = ["monthly", "yearly", "lifetime"]

        for tier in tiers:
            checkout_urls[tier] = await _create_checkout_url(tier, guild_id, user_id)

        view = discord.ui.View()
        tier_info = [
            ("monthly", "Monthly", "€4.99"),
            ("yearly", "Yearly", "€29"),
            ("lifetime", "Lifetime", "€49"),
        ]
        for tier, label, price in tier_info:
            url = checkout_urls.get(tier)
            if url:
                view.add_item(
                    discord.ui.Button(
                        label=f"Get {label} ({price})",
                        url=url,
                        style=discord.ButtonStyle.link,
                    )
                )
            else:
                # Fallback if Core-API fails
                view.add_item(
                    discord.ui.Button(
                        label=f"Get {label} ({price})",
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
            active_guild = await get_active_premium_guild(interaction.user.id)
            if active_guild == 0:
                # Unassigned premium: user has paid but hasn't chosen a guild yet
                msg = f"You have **Premium** ({tier}) but haven't chosen a server yet. Use `/premium_transfer` in the server you want."
            else:
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
            current_guild = await get_active_premium_guild(interaction.user.id)
            if current_guild == 0:
                msg = "You have Premium but haven't chosen a server yet. Use `/premium_transfer` in the server you want."
            elif current_guild is not None and current_guild != interaction.guild.id:
                msg = "Your Premium is active in another server. Use `/premium_transfer` here to move it."
            else:
                msg = "You don't have Premium in this server. Get power with /premium."

        # Add support contact info
        msg += "\n\n❓ Questions or issues? Contact support@innersync.tech"
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
            # Check for founder role assignment if transferring to founder guild
            try:
                premium_status = await get_premium_status(user_id, guild_id)
                if premium_status.get("premium") and premium_status.get("tier") == "lifetime":
                    await _assign_founder_role_if_eligible(self, user_id, guild_id, "lifetime")
            except Exception as e:
                logger.debug(f"Founder role check failed during transfer: {e}")

            await interaction.followup.send(
                "Premium is now active in this server.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Transfer failed: {reason}. Try again or contact support@innersync.tech",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PremiumCog(bot))
