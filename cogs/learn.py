import discord
from discord.ext import commands
from discord import app_commands
from gpt.helpers import is_allowed_prompt
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

        if not is_allowed_prompt(topic):
            await interaction.followup.send(
                "❌ That question doesn’t align with Innersync • Alphapy’s intent. Try a more purposeful topic.",
                ephemeral=True
            )
            log_gpt_error("filtered_prompt", user_id=interaction.user.id)
            return


        try:
            context = await load_topic_context(topic)
        
            # Als het geen bekend topic is, beschouw het als vraag
            if not context:
                reply = await ask_gpt(
                    [{"role": "user", "content": topic}],
                    user_id=interaction.user.id
                )
                await interaction.followup.send(reply, ephemeral=True)
                return
        
            # Als er wél context is (van Drive of PDF), stuur dat mee naar GPT
            reply = await ask_gpt(
                [{"role": "user", "content": context}],
                user_id=interaction.user.id
            )
            await interaction.followup.send(reply, ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send("❌ Couldn't generate a response. Try again later.", ephemeral=True)




async def setup(bot):
    await bot.add_cog(LearnTopic(bot))

