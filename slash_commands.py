import discord
from discord import app_commands
from discord.ext import commands
import config

# De gecombineerde check-functie
def is_owner_or_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        # Haal de applicatie-informatie op om de eigenaar te achterhalen
        app_info = await interaction.client.application_info()
        if interaction.user.id == app_info.owner.id:
            return True
        # Check of de gebruiker in de extra OWNER_IDS staat
        if interaction.user.id in config.OWNER_IDS:
            return True
        # Check of de gebruiker de admin-rol heeft (als hij/zij een Member is)
        if isinstance(interaction.user, discord.Member):
            admin_role = discord.utils.get(interaction.user.roles, id=config.ADMIN_ROLE_ID)
            if admin_role is not None:
                return True
        return False
    return app_commands.check(predicate)

class CustomSlashCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="sendto",
        description="Verstuurt een bericht naar een specifiek kanaal met ondersteuning voor newlines."
    )
    @app_commands.describe(
        channel="Het kanaal waarnaar het bericht verstuurd moet worden",
        message="Het bericht dat verstuurd moet worden. Gebruik \\n voor een nieuwe regel."
    )
    async def sendto(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        """
        Stuur een bericht naar het opgegeven kanaal.
        Voorbeeld:
          /sendto channel:#algemeen message:"Hallo\\ncommunity!"
        """
        # Vervang de letterlijke "\n" door een echte newline
        formatted_message = message.replace("\\n", "\n")
        try:
            await channel.send(formatted_message)
            await interaction.response.send_message(f"Bericht verstuurd naar {channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Er is een fout opgetreden: {e}", ephemeral=True)

    @app_commands.command(name="sync", description="Synchroniseer alle slash commands")
    @commands.is_owner()
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.client.tree.sync()
        await interaction.followup.send("✅ Slash commands zijn gesynchroniseerd!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomSlashCommands(bot))

