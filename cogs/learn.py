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
        guild_id = interaction.guild.id if interaction.guild else None
        
        # Defer the interaction response
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception as e:
            # Error during defer - log it and use response.send_message() instead
            error_type = f"{type(e).__name__}: {str(e)}"
            log_gpt_error(error_type=error_type, user_id=interaction.user.id, guild_id=guild_id)
            try:
                await interaction.response.send_message(
                    "❌ Something went wrong while processing your request. Please try again later.",
                    ephemeral=True,
                )
            except Exception:
                # If response is already used, try followup as fallback
                await interaction.followup.send(
                    "❌ Something went wrong while processing your request. Please try again later.",
                    ephemeral=True,
                )
            return

        if not is_allowed_prompt(topic):
            await interaction.followup.send(
                "❌ That question doesn't align with Innersync • Alphapy's intent. Try a more purposeful topic.",
                ephemeral=True
            )
            log_gpt_error("filtered_prompt", user_id=interaction.user.id, guild_id=guild_id)
            return


        guild_id = interaction.guild.id if interaction.guild else None
        
        # Step 1: Load topic context (may fail before ask_gpt is called)
        try:
            context = await load_topic_context(topic)
        except Exception as e:
            # Error occurred before ask_gpt() - log it
            error_type = f"{type(e).__name__}: {str(e)}"
            log_gpt_error(error_type=error_type, user_id=interaction.user.id, guild_id=guild_id)
            await interaction.followup.send("❌ Couldn't generate a response. Try again later.", ephemeral=True)
            return

        # Step 2: Prepare prompt and call ask_gpt (ask_gpt logs its own errors)
        try:
            # Als het geen bekend topic is, beschouw het als vraag
            prompt_messages = (
                [{"role": "user", "content": topic}]
                if not context
                else [{"role": "user", "content": context}]
            )

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
            # ask_gpt() already logs all its errors internally, so we don't log again
            await interaction.followup.send("❌ Couldn't generate a response. Try again later.", ephemeral=True)




async def setup(bot):
    await bot.add_cog(LearnTopic(bot))

