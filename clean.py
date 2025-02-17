import discord
from discord.ext import commands

class Clean(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="clean", help="Verwijdert het opgegeven aantal berichten uit het huidige kanaal (max. 100).")
    @commands.has_permissions(manage_messages=True)
    async def clean(self, ctx, limit: int = 10):
        """
        Verwijdert 'limit' aantal berichten uit het kanaal en stuurt een bevestigingsbericht.
        Het bevestigingsbericht wordt na 5 seconden verwijderd.
        Als een getal groter dan 100 wordt opgegeven, wordt het limiet teruggezet naar 100.
        """
        if limit > 100:
            limit = 100
        # +1 verwijdert ook het command bericht
        deleted = await ctx.channel.purge(limit=limit + 1)
        confirmation = await ctx.send(f"✅ {len(deleted)-1} berichten zijn verwijderd.")
        await confirmation.delete(delay=5)

def setup(bot: commands.Bot):
    bot.add_cog(Clean(bot))
