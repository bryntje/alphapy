import discord
from discord import app_commands
from discord.ext import commands
import config
from utils.validators import requires_owner


class ReloadCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reload", description="Reload a cog/extension (owner only).")
    @app_commands.describe(extension="Name of the extension to reload (e.g. onboarding, reaction_roles).")
    @requires_owner()
    async def reload(self, interaction: discord.Interaction, extension: str):
        try:
            await self.bot.reload_extension(extension)
            await interaction.response.send_message(f"Extension `{extension}` reloaded successfully.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to reload `{extension}`: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReloadCommands(bot))
