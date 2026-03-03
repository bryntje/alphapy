import discord
from discord import app_commands
from discord.ext import commands
import config
from utils.validators import requires_owner


class ReloadCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reload", description="Reload a cog/extension (owner only).")
    @app_commands.describe(extension="Extension to reload (e.g. cogs.embed_watcher or embed_watcher).")
    @requires_owner()
    async def reload(self, interaction: discord.Interaction, extension: str):
        # Normalize: extensions are loaded as "cogs.embed_watcher" etc.
        ext = extension.strip()
        if not ext.startswith("cogs."):
            ext = f"cogs.{ext}"
        try:
            await self.bot.reload_extension(ext)
            await interaction.response.send_message(f"Extension `{ext}` reloaded successfully.", ephemeral=True)
        except Exception as e:
            err_msg = str(e).lower()
            if "not loaded" in err_msg:
                loaded = list(self.bot.extensions.keys())
                hint = f" Loaded: {', '.join(sorted(loaded)[:8])}{'…' if len(loaded) > 8 else ''}." if loaded else ""
                await interaction.response.send_message(
                    f"Extension `{ext}` is not loaded.{hint} Use the full name (e.g. `cogs.embed_watcher`).",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(f"Failed to reload `{ext}`: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReloadCommands(bot))
