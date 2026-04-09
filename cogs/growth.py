import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import checks as app_checks

from gpt.helpers import ask_gpt, log_gpt_error, log_gpt_success
from utils.sanitizer import safe_embed_text
from utils.supabase_client import (
    SupabaseConfigurationError,
    insert_reflection_for_discord,
    get_user_id_for_discord,
    _supabase_get,
)

logger = logging.getLogger(__name__)

_GROWTH_EMBED_COLOR = 0x57F287  # green


def _build_growth_embed(
    user: Optional[discord.Member | discord.User],
    goal: str,
    obstacle: str,
    feeling: str,
    reply: str,
) -> discord.Embed:
    """Build the public growth check-in embed for the growth channel."""
    embed = discord.Embed(
        title="🌱 Growth Check-in",
        color=_GROWTH_EMBED_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    if user:
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    else:
        embed.set_author(name="Anonymous community member")

    embed.add_field(name="Goal", value=safe_embed_text(goal[:1024]), inline=False)
    embed.add_field(name="Obstacle", value=safe_embed_text(obstacle[:1024]), inline=False)
    embed.add_field(name="How I feel", value=safe_embed_text(feeling[:1024]), inline=False)

    grok_text = reply[:1021] + "…" if len(reply) > 1024 else reply
    embed.add_field(name="Grok's reflection", value=safe_embed_text(grok_text), inline=False)

    embed.set_footer(text="Innersync • Growth")
    return embed


class GrowthShareView(discord.ui.View):
    """Ephemeral view shown after a check-in, letting the user share to the growth channel."""

    def __init__(
        self,
        goal: str,
        obstacle: str,
        feeling: str,
        reply: str,
        growth_channel: discord.TextChannel,
    ):
        super().__init__(timeout=300)
        self.goal = goal
        self.obstacle = obstacle
        self.feeling = feeling
        self.reply = reply
        self.growth_channel = growth_channel

    @discord.ui.button(label="Share anonymously", style=discord.ButtonStyle.secondary, emoji="🌱")
    async def share_anonymous(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_growth_embed(None, self.goal, self.obstacle, self.feeling, self.reply)
        try:
            await self.growth_channel.send(embed=embed)
            await interaction.response.edit_message(
                content="✅ Shared anonymously to the growth channel.", view=None
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                content="❌ I can't post in the growth channel. Ask an admin to check my permissions.", view=None
            )
        self.stop()

    @discord.ui.button(label="Share with my name", style=discord.ButtonStyle.primary, emoji="🌿")
    async def share_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_growth_embed(interaction.user, self.goal, self.obstacle, self.feeling, self.reply)
        try:
            await self.growth_channel.send(embed=embed)
            await interaction.response.edit_message(
                content=f"✅ Shared to {self.growth_channel.mention}!", view=None
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                content="❌ I can't post in the growth channel. Ask an admin to check my permissions.", view=None
            )
        self.stop()

    @discord.ui.button(label="Keep private", style=discord.ButtonStyle.danger, emoji="🔒")
    async def keep_private(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Your check-in stays private. 🔒", view=None)
        self.stop()


class GrowthCheckin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="growthcheckin",
        description="Reflect on your goals, obstacles, and how you feel.",
    )
    @app_checks.cooldown(2, 300.0, key=lambda i: (i.guild.id, i.user.id) if i.guild else i.user.id)
    async def growthcheckin(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GrowthModal())


class GrowthModal(discord.ui.Modal, title="🌱 Growth Check-in"):
    goal = discord.ui.TextInput(
        label="What do you want to achieve?",
        placeholder="e.g. more focus, consistent routine…",
    )
    obstacle = discord.ui.TextInput(
        label="What's standing in your way?",
        placeholder="Internal or external blocks…",
    )
    feeling = discord.ui.TextInput(
        label="How do you feel about it?",
        placeholder="Be honest, be real…",
        style=discord.TextStyle.paragraph,
    )

    async def on_submit(self, interaction: discord.Interaction):
        from utils.sanitizer import safe_prompt

        safe_goal = safe_prompt(self.goal.value)
        safe_obstacle = safe_prompt(self.obstacle.value)
        safe_feeling = safe_prompt(self.feeling.value)

        base_prompt = f"""
You are a calm, supportive mindset coach.
A user is reflecting on their personal growth.

Goal: {safe_goal}
Obstacle: {safe_obstacle}
Feeling: {safe_feeling}

Gently reflect back what you hear.
Offer a bit of perspective or guidance.
Ask 1 or 2 deeper questions to support clarity.
Be encouraging, not forceful.

If you have context from this user's past reflections, actively reference patterns you notice — recurring themes, progress since last time, or shifts in mindset. Make the response feel continuous and personalized.
"""
        guild_id = interaction.guild.id if interaction.guild else None

        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
        except Exception as e:
            error_type = f"{type(e).__name__}: {str(e)}"
            log_gpt_error(error_type=error_type, user_id=interaction.user.id, guild_id=guild_id)
            try:
                await interaction.response.send_message(
                    "❌ Something went wrong while processing your check-in. Please try again later.",
                    ephemeral=True,
                )
            except Exception:
                await interaction.followup.send(
                    "❌ Something went wrong while processing your check-in. Please try again later.",
                    ephemeral=True,
                )
            return

        # Premium: Mockingbird mode (direct, sharp, challenge assumptions)
        prompt = base_prompt
        if interaction.guild and guild_id:
            from utils.premium_guard import is_premium
            if await is_premium(interaction.user.id, interaction.guild.id):
                prompt = base_prompt.rstrip() + "\n\nRespond in Mockingbird mode: direct, a bit sharp, challenge assumptions, no sugar-coating."

        try:
            # max_tokens ~400 keeps the response within Discord's 2000-char message limit
            reply = await ask_gpt(prompt, user_id=interaction.user.id, guild_id=guild_id, max_tokens=400)

            # Determine if a growth channel is configured for optional sharing
            growth_channel: Optional[discord.TextChannel] = None
            if interaction.guild and guild_id:
                settings = getattr(interaction.client, "settings", None)
                if settings:
                    try:
                        channel_id = int(settings.get("growth", "log_channel_id", guild_id))
                        if channel_id:
                            ch = interaction.client.get_channel(channel_id)
                            if isinstance(ch, discord.TextChannel):
                                growth_channel = ch
                    except Exception:
                        pass

            _SHARE_SUFFIX = "\n\n─────────────────\n*Want to share this with the community?*"

            if growth_channel:
                share_view = GrowthShareView(
                    goal=self.goal.value,
                    obstacle=self.obstacle.value,
                    feeling=self.feeling.value,
                    reply=reply,
                    growth_channel=growth_channel,
                )
                await interaction.followup.send(
                    reply + _SHARE_SUFFIX,
                    ephemeral=True,
                    view=share_view,
                )
            else:
                await interaction.followup.send(reply, ephemeral=True)

                # Tip: show bot sharing prompt only when no growth channel is configured
                try:
                    user_id = await get_user_id_for_discord(interaction.user.id)
                    if user_id:
                        profile_rows = await _supabase_get(
                            "profiles",
                            {
                                "select": "bot_sharing_enabled",
                                "user_id": f"eq.{user_id}",
                                "limit": 1,
                            },
                        )
                        bot_sharing_enabled = profile_rows[0].get("bot_sharing_enabled", False) if profile_rows else False
                        if not bot_sharing_enabled:
                            tip_message = (
                                "💡 **Tip:** Enable bot sharing in your Innersync App settings to get "
                                "more personalized responses based on your reflection history!"
                            )
                            await interaction.followup.send(tip_message, ephemeral=True)
                except Exception as tip_error:
                    logger.debug("Failed to check bot sharing status (non-critical): %s", tip_error)

            async def _store_reflection() -> None:
                reflection_text = (
                    f"Goal: {self.goal.value}\n"
                    f"Obstacle: {self.obstacle.value}\n"
                    f"Feeling: {self.feeling.value}"
                )
                try:
                    success = await insert_reflection_for_discord(
                        interaction.user.id,
                        reflection=reflection_text,
                        future_message=reply,
                        date=datetime.now(timezone.utc),
                    )
                    if not success:
                        logger.debug(
                            "Skipping Supabase reflection sync: no profile linked to discord_id=%s",
                            interaction.user.id,
                        )
                except SupabaseConfigurationError:
                    logger.debug("Supabase credentials missing; skipping reflection sync.")
                except Exception as exc:  # pragma: no cover - network path
                    logger.warning(
                        "Failed to sync reflection to Supabase for discord_id=%s: %s",
                        interaction.user.id,
                        exc,
                    )

            asyncio.create_task(_store_reflection())
        except Exception:
            await interaction.followup.send(
                "❌ Something went wrong while processing your check-in. Please try again later.",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(GrowthCheckin(bot))
