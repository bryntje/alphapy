import asyncio
import logging

import discord
from discord.ext import commands
from discord import app_commands

from gpt.helpers import ask_gpt, log_gpt_success, log_gpt_error
from utils.supabase_client import (
    SupabaseConfigurationError,
    insert_insight_for_discord,
)

logger = logging.getLogger(__name__)

STYLES = [
    "punchy",
    "vulnerable",
    "educational",
    "spiritual",
    "motivational",
    "formal"
]

class ContentGen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create_caption", description="Generate a social caption based on topic and style")
    @app_commands.describe(
        topic="What should the caption be about? (e.g. trading discipline, mindset, risk)",
        style="Choose the tone of the caption"
    )
    @app_commands.choices(style=[
        app_commands.Choice(name=style.capitalize(), value=style) for style in STYLES
    ])
    async def create_caption(self, interaction: discord.Interaction, topic: str, style: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True, thinking=True)

        messages = [
            {"role": "system", "content": "You are an AI content creator."},
            {"role": "user", "content": f"""
Generate a short caption (max 300 characters) for social media.
Tone: {style.value}
Topic: {topic}
Be original, real, and in tune with an audience that's self-aware and growth-oriented.
Avoid clichés.
"""}
        ]

        try:
            reply = await ask_gpt(messages, user_id=interaction.user.id)
            log_gpt_success(user_id=interaction.user.id)
            await interaction.followup.send(reply.strip(), ephemeral=True)

            async def _store_caption_insight() -> None:
                try:
                    success = await insert_insight_for_discord(
                        interaction.user.id,
                        summary=reply.strip(),
                        source="system",
                        tags=["content", style.value],
                    )
                    if not success:
                        logger.debug(
                            "Skipping content insight sync: no profile for discord_id=%s",
                            interaction.user.id,
                        )
                except SupabaseConfigurationError:
                    logger.debug(
                        "Supabase credentials missing; skipping content insight sync."
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to sync content insight for discord_id=%s: %s",
                        interaction.user.id,
                        exc,
                    )

            asyncio.create_task(_store_caption_insight())
        except Exception as e:
            log_gpt_error("create_caption", user_id=interaction.user.id)
            await interaction.followup.send("❌ Couldn't generate the caption. Try again later.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ContentGen(bot))
