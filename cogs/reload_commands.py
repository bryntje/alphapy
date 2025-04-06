import discord
from discord import app_commands
from discord.ext import commands
import config
from utils.checks import is_owner_or_admin

class ReloadCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reload", description="Herlaadt een specifieke extension (bijv. onboarding of reaction_roles).")
    @app_commands.describe(extension="De naam van de extension die herladen moet worden.")
    @is_owner_or_admin()
    async def reload(self, interaction: discord.Interaction, extension: str):
        try:
            await self.bot.reload_extension(extension)
            await interaction.response.send_message(f"✅ Extension `{extension}` succesvol herladen.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Fout bij het herladen van `{extension}`: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReloadCommands(bot))
