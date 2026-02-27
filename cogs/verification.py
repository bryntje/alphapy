import json
from datetime import datetime
from typing import Optional, Dict, Any, cast

import asyncpg
import discord
from asyncpg import exceptions as pg_exceptions
from discord import app_commands
from discord.ext import commands

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from gpt.helpers import ask_gpt_vision
from utils.db_helpers import acquire_safe, create_db_pool, is_pool_healthy
from utils.embed_builder import EmbedBuilder
from utils.logger import logger, log_database_event, log_with_guild, log_guild_action
from utils.sanitizer import safe_embed_text
from utils.settings_helpers import CachedSettingsHelper
from utils.settings_service import SettingsService
from utils.timezone import BRUSSELS_TZ


class VerificationCog(commands.Cog):
    """AI-based payment verification via private ticket channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None

        settings = getattr(bot, "settings", None)
        if not isinstance(settings, SettingsService):
            raise RuntimeError("SettingsService not available on bot instance")

        self.settings: SettingsService = settings
        self.settings_helper = CachedSettingsHelper(settings)

        # Start async setup without blocking the event loop
        self.bot.loop.create_task(self.setup_db())
        # Register persistent panel view so the button keeps working after restarts
        try:
            self.bot.add_view(VerificationPanelView(self, timeout=None))
        except Exception as e:
            logger.warning(f"⚠️ VerificationCog: could not register VerificationPanelView: {e}")

    async def setup_db(self) -> None:
        """Initialize database pool and ensure verification_tickets table exists."""
        try:
            dsn = getattr(config, "DATABASE_URL", None) or ""
            if not dsn:
                logger.warning("VerificationCog: DATABASE_URL not set, skipping pool creation")
                return

            pool = await create_db_pool(
                dsn,
                name="verification",
                min_size=1,
                max_size=10,
                command_timeout=10.0,
            )
            self.db = pool
            log_database_event("DB_CONNECTED", details="Verification database pool created")

            async with acquire_safe(pool) as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS verification_tickets (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        channel_id BIGINT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        ai_can_verify BOOLEAN,
                        ai_needs_manual_review BOOLEAN,
                        ai_reason TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        resolved_at TIMESTAMPTZ
                    );
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_verification_tickets_guild_status ON verification_tickets(guild_id, status);"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_verification_tickets_channel_id ON verification_tickets(channel_id);"
                )

            logger.info("✅ VerificationCog: DB ready (verification_tickets)")
            log_database_event("DB_READY", details="VerificationCog database fully initialized")
        except Exception as e:
            log_database_event("DB_INIT_ERROR", details=f"VerificationCog setup failed: {e}")
            logger.error(f"❌ VerificationCog: DB init error: {e}")
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None

    async def cog_unload(self) -> None:
        if self.db:
            try:
                await self.db.close()
            except Exception:
                pass
            self.db = None

    # ----- Settings helpers -----

    def _get_verified_role_id(self, guild_id: int) -> Optional[int]:
        value = self.settings_helper.get_int("verification", "verified_role_id", guild_id, fallback=0)
        return int(value) if value else None

    def _get_panel_channel_id(self, guild_id: int) -> Optional[int]:
        value = self.settings_helper.get_int("verification", "channel_id", guild_id, fallback=0)
        return int(value) if value else None

    def _get_category_id(self, guild_id: int) -> Optional[int]:
        value = self.settings_helper.get_int("verification", "category_id", guild_id, fallback=0)
        return int(value) if value else None

    def _get_vision_model(self, guild_id: int) -> Optional[str]:
        try:
            raw = self.settings.get("verification", "vision_model", guild_id)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        except Exception:
            pass
        return None

    def _get_log_channel_id(self, guild_id: int) -> int:
        value = self.settings_helper.get_int("system", "log_channel_id", guild_id, fallback=0)
        return int(value) if value else 0

    async def send_log_embed(self, title: str, description: str, level: str, guild_id: int) -> None:
        """Send log embed to the guild's log channel using EmbedBuilder."""
        if guild_id == 0:
            logger.warning("⚠️ VerificationCog send_log_embed called without guild_id")
            return

        from utils.logger import should_log_to_discord

        if not should_log_to_discord(level, guild_id):
            return

        try:
            embed = EmbedBuilder.log(title, description, level, guild_id)
            embed.set_footer(text=f"verification | Guild: {guild_id}")

            channel_id = self._get_log_channel_id(guild_id)
            if channel_id == 0:
                log_with_guild("No log channel configured for verification logging", guild_id, "debug")
                return

            channel = self.bot.get_channel(channel_id)
            if channel and hasattr(channel, "send"):
                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(embed=embed)
                log_guild_action(guild_id, "LOG_SENT", details=f"verification: {title}")
            else:
                log_with_guild(f"Verification log channel {channel_id} not found or not accessible", guild_id, "warning")
        except Exception as e:
            log_with_guild(f"Could not send verification log embed: {e}", guild_id, "error")

    # ----- Commands -----

    @app_commands.command(
        name="verification_panel_post",
        description="Post a verification panel with a Start verification button.",
    )
    @app_commands.guild_only()
    @app_commands.describe(channel="Channel where the panel should be posted (defaults to current channel)")
    async def verification_panel_post(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        from utils.validators import validate_admin

        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return

        target = channel or cast(discord.TextChannel, interaction.channel)
        if target is None:
            await interaction.response.send_message("❌ No channel specified.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        category_id = self._get_category_id(guild_id)
        verified_role_id = self._get_verified_role_id(guild_id)

        if not category_id or not verified_role_id:
            await interaction.response.send_message(
                "⚠️ Verification is not fully configured yet. "
                "Please set `verification.category_id` and `verification.verified_role_id` via the config system.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="✅ Verify your access",
            description=(
                "To unlock full access, start a private verification.\n\n"
                "1. Click **Start verification**.\n"
                "2. Upload a clear screenshot of your payment or subscription confirmation.\n"
                "3. Our AI will review it and either auto-verify you or forward it to the team."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(BRUSSELS_TZ),
        )
        from version import __version__, CODENAME
        embed.set_footer(text=f"Innersync • Alphapy v{__version__} — {CODENAME}")

        view = VerificationPanelView(self, timeout=None)
        await target.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Verification panel posted.", ephemeral=True)

    @app_commands.command(
        name="verification_close",
        description="Close a verification channel after manual review.",
    )
    @app_commands.guild_only()
    async def verification_close(self, interaction: discord.Interaction) -> None:
        from utils.validators import validate_admin

        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command only works in a server.",
                ephemeral=True,
            )
            return

        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ This command can only be used in a text channel.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        category_id = self._get_category_id(guild_id)
        if not category_id or not channel.category or channel.category.id != category_id:
            await interaction.response.send_message(
                "❌ This command can only be used inside a verification channel.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Update ticket status in database (best-effort)
        if is_pool_healthy(self.db):
            try:
                async with acquire_safe(self.db) as conn:
                    await conn.execute(
                        """
                        UPDATE verification_tickets
                        SET status = 'closed_manual', resolved_at = NOW()
                        WHERE guild_id = $1 AND channel_id = $2
                        """,
                        guild_id,
                        int(channel.id),
                    )
            except Exception as e:
                logger.warning(f"VerificationCog: failed to mark ticket closed manually: {e}")

        # Lock and optionally rename the channel
        try:
            overwrites = channel.overwrites
            guild = interaction.guild
            member = guild.get_member(interaction.user.id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                )
            overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            await channel.edit(overwrites=overwrites, reason="Verification closed manually")

            try:
                if not channel.name.endswith("-closed"):
                    await channel.edit(name=f"{channel.name}-closed")
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"VerificationCog: could not lock/rename verification channel: {e}")

        # Notify in channel and to the invoker
        closed_embed = EmbedBuilder.warning(
            title="🔒 Verification closed",
            description=(
                "This verification has been closed manually by a team member.\n\n"
                "If you believe this is a mistake, please contact the team."
            ),
        )
        try:
            await channel.send(embed=closed_embed)
        except Exception:
            pass

        await interaction.followup.send("✅ Verification channel closed.", ephemeral=True)

        await self.send_log_embed(
            title="🔒 Verification closed manually",
            description=(
                f"Channel: {channel.mention}\n"
                f"Closed by: {interaction.user} ({interaction.user.id})"
            ),
            level="info",
            guild_id=guild_id,
        )

    # ----- Ticket helpers -----

    async def _create_verification_channel(self, interaction: discord.Interaction) -> Optional[discord.TextChannel]:
        if not interaction.guild:
            return None

        guild = interaction.guild
        guild_id = guild.id
        user = interaction.user

        category_id = self._get_category_id(guild_id)
        if not category_id:
            await interaction.followup.send(
                "❌ Verification category is not configured. Please ask an admin to configure verification.",
                ephemeral=True,
            )
            return None

        try:
            fetched_channel = guild.get_channel(category_id) or await self.bot.fetch_channel(category_id)
            if not isinstance(fetched_channel, discord.CategoryChannel):
                raise RuntimeError("Configured verification category is not a category channel")
            category = fetched_channel
        except Exception as e:
            logger.warning(f"VerificationCog: could not fetch category {category_id}: {e}")
            await interaction.followup.send(
                "❌ Verification category could not be found. Please ask an admin to fix the configuration.",
                ephemeral=True,
            )
            return None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }

        channel = await guild.create_text_channel(
            name=f"verify-{user.name}".lower().replace(" ", "-"),
            category=category,
            overwrites=overwrites,
            reason=f"Verification ticket for {user}",
        )

        await self._store_verification_ticket(guild_id=guild_id, user_id=int(user.id), channel_id=int(channel.id))

        intro = EmbedBuilder.info(
            title="📸 Verification started",
            description=(
                "Please upload **one clear screenshot** of your payment or subscription confirmation.\n\n"
                "- Make sure the **amount** and **date** are visible.\n"
                "- You may blur sensitive details like card numbers.\n\n"
                "Once you upload the screenshot, our AI will review it."
            ),
        )
        await channel.send(content=user.mention, embed=intro)
        return channel

    async def _store_verification_ticket(self, guild_id: int, user_id: int, channel_id: int) -> None:
        if not is_pool_healthy(self.db):
            return
        try:
            async with acquire_safe(self.db) as conn:
                await conn.execute(
                    """
                    INSERT INTO verification_tickets (guild_id, user_id, channel_id, status)
                    VALUES ($1, $2, $3, 'pending')
                    """,
                    guild_id,
                    user_id,
                    channel_id,
                )
        except RuntimeError:
            logger.debug("VerificationCog: database pool not available when storing ticket")
        except Exception as e:
            logger.warning(f"VerificationCog: failed to store verification ticket: {e}")

    async def _update_verification_ticket(
        self,
        channel_id: int,
        *,
        status: str,
        ai_can_verify: Optional[bool],
        ai_needs_manual_review: Optional[bool],
        ai_reason: Optional[str],
    ) -> None:
        if not is_pool_healthy(self.db):
            return
        try:
            async with acquire_safe(self.db) as conn:
                await conn.execute(
                    """
                    UPDATE verification_tickets
                    SET status = $1,
                        ai_can_verify = $2,
                        ai_needs_manual_review = $3,
                        ai_reason = $4,
                        resolved_at = CASE WHEN $1 <> 'pending' THEN NOW() ELSE resolved_at END
                    WHERE channel_id = $5 AND status = 'pending'
                    """,
                    status,
                    ai_can_verify,
                    ai_needs_manual_review,
                    ai_reason,
                    channel_id,
                )
        except RuntimeError:
            logger.debug("VerificationCog: database pool not available when updating ticket")
        except Exception as e:
            logger.warning(f"VerificationCog: failed to update verification ticket: {e}")

    # ----- Listener -----

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle screenshots uploaded in verification channels."""
        if message.author.bot:
            return
        if not message.guild:
            return
        if not message.attachments:
            return

        guild = message.guild
        guild_id = guild.id
        category_id = self._get_category_id(guild_id)
        if not category_id:
            return

        if not isinstance(message.channel, discord.TextChannel):
            return
        if not message.channel.category or message.channel.category.id != category_id:
            return

        # Only process the first image attachment
        attachment = None
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                attachment = att
                break
        if not attachment:
            return

        # Defer basic acknowledgement in-channel
        processing_embed = EmbedBuilder.status(
            title="🔍 Verifying your screenshot",
            description="Please wait a moment while we review your payment confirmation.",
        )
        await message.channel.send(embed=processing_embed)

        # Build verification prompt
        verified_role_id = self._get_verified_role_id(guild_id)
        vision_model = self._get_vision_model(guild_id)

        prompt = (
            "You are verifying whether an uploaded image is a valid proof of payment or subscription confirmation.\n\n"
            "Strictly answer in **JSON only** with the following keys:\n"
            '{\n  "can_verify": boolean,\n  "needs_manual_review": boolean,\n  "reason": string\n}\n\n'
            "- `can_verify`: true if the screenshot clearly shows a valid payment or active subscription for this product.\n"
            "- `needs_manual_review`: true if the screenshot is unclear, incomplete, or ambiguous.\n"
            "- `reason`: short explanation in English without including any card numbers, IBAN, email addresses, or other PII.\n\n"
            "Never include raw payment details in your answer. Just describe the situation at a high level.\n"
            "Now analyze the screenshot and respond with JSON only."
        )

        image_url = attachment.url

        try:
            result_text = await ask_gpt_vision(
                prompt,
                image_url,
                user_id=int(message.author.id),
                model=vision_model,
                guild_id=guild_id,
            )
        except Exception as e:
            logger.exception(f"VerificationCog: vision call failed: {e}")
            await message.channel.send(
                embed=EmbedBuilder.error(
                    title="❌ Verification failed",
                    description="Something went wrong while contacting the AI service. Please try again later or contact support.",
                )
            )
            await self._update_verification_ticket(
                channel_id=int(message.channel.id),
                status="error",
                ai_can_verify=None,
                ai_needs_manual_review=None,
                ai_reason=str(e),
            )
            return

        can_verify = False
        needs_manual_review = True
        reason = "Unclear AI result."

        try:
            parsed = json.loads(result_text or "{}")
            if isinstance(parsed, dict):
                can_verify = bool(parsed.get("can_verify", False))
                needs_manual_review = bool(parsed.get("needs_manual_review", not can_verify))
                reason_val = parsed.get("reason")
                if isinstance(reason_val, str) and reason_val.strip():
                    reason = reason_val.strip()
        except Exception as e:
            # Avoid logging the full AI response to reduce risk of PII in logs
            logger.warning(
                "VerificationCog: could not parse vision JSON: %s (response length=%s)",
                e,
                len(result_text or ""),
            )

        # Update DB
        await self._update_verification_ticket(
            channel_id=int(message.channel.id),
            status="verified" if can_verify and not needs_manual_review else "manual_review",
            ai_can_verify=can_verify,
            ai_needs_manual_review=needs_manual_review,
            ai_reason=reason,
        )

        # Act on result
        member = guild.get_member(message.author.id)

        if can_verify and not needs_manual_review and member and verified_role_id:
            role = guild.get_role(verified_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="AI verification succeeded")
                except Exception as e:
                    logger.warning(f"VerificationCog: could not assign verified role: {e}")

            success_embed = EmbedBuilder.success(
                title="✅ You are verified",
                description=(
                    "Your payment screenshot has been verified successfully.\n\n"
                    f"Reason: {safe_embed_text(reason, 1024)}"
                ),
            )
            await message.channel.send(embed=success_embed)

            # Optionally lock the channel
            try:
                overwrites = message.channel.overwrites
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                )
                overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                await message.channel.edit(overwrites=overwrites, reason="Verification completed")
            except Exception as e:
                logger.debug(f"VerificationCog: could not lock verification channel: {e}")

            await self.send_log_embed(
                title="✅ Verification succeeded",
                description=(
                    f"User: {member} ({member.id})\n"
                    f"Channel: {message.channel.mention}\n"
                    f"Reason: {safe_embed_text(reason, 1024)}"
                ),
                level="success",
                guild_id=guild_id,
            )
        else:
            warn_embed = EmbedBuilder.warning(
                title="👀 Manual review required",
                description=(
                    "The AI could not confidently verify this screenshot.\n"
                    "A member of the team will review your verification manually.\n\n"
                    f"Reason: {safe_embed_text(reason, 1024)}"
                ),
            )
            await message.channel.send(embed=warn_embed)

            await self.send_log_embed(
                title="⚠️ Verification needs manual review",
                description=(
                    f"User: {message.author} ({message.author.id})\n"
                    f"Channel: {message.channel.mention}\n"
                    f"Reason: {safe_embed_text(reason, 1024)}"
                ),
                level="warning",
                guild_id=guild_id,
            )


class VerificationPanelView(discord.ui.View):
    def __init__(self, cog: VerificationCog, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog

    @discord.ui.button(
        label="Start verification",
        style=discord.ButtonStyle.primary,
        custom_id="verification_start_btn",
    )
    async def start_verification(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("❌ This button only works in a server.", ephemeral=True)
            return

        try:
            channel = await self.cog._create_verification_channel(interaction)
        except Exception as e:
            logger.exception(f"VerificationPanelView: could not create verification channel: {e}")
            await interaction.followup.send(
                "❌ Something went wrong while creating your verification channel. Please try again later.",
                ephemeral=True,
            )
            return

        if not channel:
            return

        await interaction.followup.send(f"✅ Verification channel created: {channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VerificationCog(bot))

