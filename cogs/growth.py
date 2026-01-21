import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import checks as app_checks

from gpt.helpers import ask_gpt, log_gpt_error, log_gpt_success
from utils.supabase_client import (
    SupabaseConfigurationError,
    insert_reflection_for_discord,
)

logger = logging.getLogger(__name__)


class GrowthCheckin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="growthcheckin",
        description="Reflect on your goals, obstacles, and how you feel.",
    )
    @app_checks.cooldown(2, 300.0, key=lambda i: (i.guild.id, i.user.id) if i.guild else i.user.id)  # 2 per 5 minuten
    async def growthcheckin(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GrowthModal())


class GrowthModal(discord.ui.Modal, title="🌱 Growth Check-in"):
    goal = discord.ui.TextInput(
        label="What do you want to achieve?",
        placeholder="e.g. more focus, consistent routine…",
    )
    obstacle = discord.ui.TextInput(
        label="What’s standing in your way?",
        placeholder="Internal or external blocks…",
    )
    feeling = discord.ui.TextInput(
        label="How do you feel about it?",
        placeholder="Be honest, be real…",
        style=discord.TextStyle.paragraph,
    )

    async def on_submit(self, interaction: discord.Interaction):
        from utils.sanitizer import safe_prompt
        
        # Sanitize each input field
        safe_goal = safe_prompt(self.goal.value)
        safe_obstacle = safe_prompt(self.obstacle.value)
        safe_feeling = safe_prompt(self.feeling.value)
        
        prompt = f"""
You are a calm, supportive mindset coach.
A user is reflecting on their personal growth.

Goal: {safe_goal}
Obstacle: {safe_obstacle}
Feeling: {safe_feeling}

Gently reflect back what you hear.
Offer a bit of perspective or guidance.
Ask 1 or 2 deeper questions to support clarity.
Be encouraging, not forceful.
"""
        guild_id = interaction.guild.id if interaction.guild else None
        
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
        except Exception as e:
            # Error during defer - log it (happens before ask_gpt)
            # Use response.send_message() since defer failed and followup is not available
            error_type = f"{type(e).__name__}: {str(e)}"
            log_gpt_error(error_type=error_type, user_id=interaction.user.id, guild_id=guild_id)
            try:
                await interaction.response.send_message(
                    "❌ Something went wrong while processing your check-in. Please try again later.",
                    ephemeral=True,
                )
            except Exception:
                # If response is already used, try followup as fallback
                await interaction.followup.send(
                    "❌ Something went wrong while processing your check-in. Please try again later.",
                    ephemeral=True,
                )
            return
        
        # Call ask_gpt (ask_gpt logs its own errors)
        try:
            reply = await ask_gpt(prompt, user_id=interaction.user.id, guild_id=guild_id)
            # ask_gpt() already logs success internally
            await interaction.followup.send(reply, ephemeral=True)

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
                    logger.debug(
                        "Supabase credentials missing; skipping reflection sync."
                    )
                except Exception as exc:  # pragma: no cover - network path
                    logger.warning(
                        "Failed to sync reflection to Supabase for discord_id=%s: %s",
                        interaction.user.id,
                        exc,
                    )

            asyncio.create_task(_store_reflection())
        except Exception as e:
            # ask_gpt() already logs all its errors internally, so we don't log again
            await interaction.followup.send(
                "❌ Something went wrong while processing your check-in. Please try again later.",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(GrowthCheckin(bot))
