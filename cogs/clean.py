import discord
from discord import app_commands
from discord.ext import commands

class Clean(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clean", description="Verwijdert het opgegeven aantal berichten (max 100).")
    @app_commands.describe(limit="Aantal berichten om te verwijderen (max 100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clean(self, interaction: discord.Interaction, limit: int = 10):
        """
        Verwijdert 'limit' aantal berichten uit het kanaal.
        """
        if limit > 100:
            limit = 100
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Dit commando werkt alleen in tekstkanalen.",
                ephemeral=True,
            )
            return
        await channel.purge(limit=limit)
        await interaction.response.send_message(
            f"✅ {limit} berichten verwijderd.",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Clean(bot))
