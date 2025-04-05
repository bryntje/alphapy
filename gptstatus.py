import discord
from discord.ext import commands
from discord import app_commands
import datetime
import config

# Tijdstempels bijhouden van GPT status
last_gpt_status = {
    "success": None,
    "last_error": None,
    "error_type": None
}

class GPTStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gptstatus", description="Show the current GPT API status.")
    async def gptstatus(self, interaction: discord.Interaction):
        now = datetime.datetime.utcnow()

        success_time = last_gpt_status["success"]
        error_time = last_gpt_status["last_error"]
        error_type = last_gpt_status["error_type"]

        status_msg = "🧠 **GPT API Status**\n"

        if success_time:
            delta = now - success_time
            status_msg += f"✅ Last successful reply: `{delta.seconds} sec ago`\n"
        else:
            status_msg += "⚠️ No successful replies logged yet.\n"

        if error_time:
            delta = now - error_time
            status_msg += f"❌ Last error: `{delta.seconds} sec ago` (`{error_type}`)\n"

        await interaction.response.send_message(status_msg, ephemeral=True)


# Hulpfuncties voor andere modules om status bij te werken

def log_gpt_success():
    last_gpt_status["success"] = datetime.datetime.utcnow()

def log_gpt_error(error_type="general"):
    last_gpt_status["last_error"] = datetime.datetime.utcnow()
    last_gpt_status["error_type"] = error_type


async def setup(bot: commands.Bot):
    await bot.add_cog(GPTStatus(bot))
