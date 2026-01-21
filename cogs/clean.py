import discord
from discord import app_commands
from discord.ext import commands

class Clean(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clean", description="Delete the specified number of messages (max 100).")
    @app_commands.describe(limit="Number of messages to delete (max 100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clean(self, interaction: discord.Interaction, limit: int = 10):
        """
        Delete 'limit' number of messages from the channel.
        """
        if limit > 100:
            limit = 100
        
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ This command only works in text channels.",
                ephemeral=True,
            )
            return
        
        # Defer response immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=True)
        
        # Perform the purge operation (may take time)
        deleted = await channel.purge(limit=limit)
        deleted_count = len(deleted)
        
        # Send followup message
        await interaction.followup.send(
            f"✅ {deleted_count} message{'s' if deleted_count != 1 else ''} deleted.",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Clean(bot))
