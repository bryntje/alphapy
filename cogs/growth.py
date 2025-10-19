import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

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
        prompt = f"""
You are a calm, supportive mindset coach.
A user is reflecting on their personal growth.

Goal: {self.goal.value}
Obstacle: {self.obstacle.value}
Feeling: {self.feeling.value}

Gently reflect back what you hear.
Offer a bit of perspective or guidance.
Ask 1 or 2 deeper questions to support clarity.
Be encouraging, not forceful.
"""
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            reply = await ask_gpt(prompt)
            log_gpt_success(user_id=interaction.user.id)
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
        except Exception:
            log_gpt_error("growthcheckin", user_id=interaction.user.id)
            await interaction.followup.send(
                "❌ Something went wrong while processing your check-in. Please try again later.",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(GrowthCheckin(bot))
