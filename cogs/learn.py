import asyncio
import logging

import discord
from discord.ext import commands
from discord import app_commands

from gpt.helpers import is_allowed_prompt
from gpt.helpers import ask_gpt, log_gpt_success, log_gpt_error
from gpt.dataset_loader import load_topic_context
from utils.supabase_client import (
    SupabaseConfigurationError,
    insert_insight_for_discord,
)

logger = logging.getLogger(__name__)

class LearnTopic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="learn_topic", description="Ask a topic and get a short, clear explanation from GPT.")
    @app_commands.describe(topic="e.g. RSI, scalping, risk management…")
    async def learn_topic(self, interaction: discord.Interaction, topic: str):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not is_allowed_prompt(topic):
            await interaction.followup.send(
                "❌ That question doesn't align with Innersync • Alphapy's intent. Try a more purposeful topic.",
                ephemeral=True
            )
            guild_id = interaction.guild.id if interaction.guild else None
            log_gpt_error("filtered_prompt", user_id=interaction.user.id, guild_id=guild_id)
            return


        try:
            context = await load_topic_context(topic)

            # Als het geen bekend topic is, beschouw het als vraag
            prompt_messages = (
                [{"role": "user", "content": topic}]
                if not context
                else [{"role": "user", "content": context}]
            )

            guild_id = interaction.guild.id if interaction.guild else None
            reply = await ask_gpt(
                prompt_messages,
                user_id=interaction.user.id,
                guild_id=guild_id
            )
            # ask_gpt() already logs success internally
            await interaction.followup.send(reply, ephemeral=True)

            async def _store_learn_insight() -> None:
                try:
                    success = await insert_insight_for_discord(
                        interaction.user.id,
                        summary=reply,
                        source="system",
                        tags=["learn_topic", topic.lower()],
                    )
                    if not success:
                        logger.debug(
                            "Skipping learn insight sync: no profile for discord_id=%s",
                            interaction.user.id,
                        )
                except SupabaseConfigurationError:
                    logger.debug(
                        "Supabase credentials missing; skipping learn insight sync."
                    )
                except Exception as exc:  # pragma: no cover - network path
                    logger.warning(
                        "Failed to sync learn insight for discord_id=%s: %s",
                        interaction.user.id,
                        exc,
                    )

            asyncio.create_task(_store_learn_insight())

        except Exception as e:
            guild_id = interaction.guild.id if interaction.guild else None
            error_type = f"{type(e).__name__}: {str(e)}"
            # Check if error occurred before ask_gpt() was called (e.g., load_topic_context failure)
            # ask_gpt() logs its own errors internally, so we only log pre-call errors
            # RuntimeError with API key message indicates ask_gpt() was called and failed
            is_ask_gpt_error = (
                isinstance(e, RuntimeError) and 
                ("GROK_API_KEY" in str(e) or "OPENAI_API_KEY" in str(e) or "ontbreekt" in str(e))
            )
            if not is_ask_gpt_error:
                # Error occurred before ask_gpt() call (e.g., load_topic_context, network issues)
                log_gpt_error(error_type=error_type, user_id=interaction.user.id, guild_id=guild_id)
            await interaction.followup.send("❌ Couldn't generate a response. Try again later.", ephemeral=True)




async def setup(bot):
    await bot.add_cog(LearnTopic(bot))

