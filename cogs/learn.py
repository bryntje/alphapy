import discord
from discord.ext import commands
from discord import app_commands
from gpt.helpers import ask_gpt, log_gpt_success, log_gpt_error
from gpt.dataset_loader import load_topic_context
from utils.drive_sync import fetch_pdf_text_by_name

class LearnTopic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="learn_topic", description="Ask a topic and get a short, clear explanation from GPT.")
    @app_commands.describe(topic="e.g. RSI, scalping, risk management…")
    async def learn_topic(self, interaction: discord.Interaction, topic: str):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            context = await load_topic_context(topic)

            if not context:
                context = fetch_pdf_text_by_name(topic)

            messages = [
                {"role": "system", "content": "You are a helpful and human-like trading coach."},
                {"role": "user", "content": f"""
Explain the topic '{topic}' in simple, accessible language.
If context is provided, use it as source material.
Limit to 250 words. Be clear, warm, and focused.

Context:
{context if context else '[no context available]'}
"""}
            ]

            reply = await ask_gpt(messages, user_id=interaction.user.id)
            await interaction.followup.send(reply, ephemeral=True)

        except Exception as e:
            await interaction.followup.send("❌ Couldn't generate a response. Try again later.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LearnTopic(bot))

