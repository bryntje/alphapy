import discord
from discord.ext import commands
import config

class CustomCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sendfile")
    async def send_file(self, ctx, file_or_link: str, *, context: str = None):
        """
        Stuurt een bericht in een specifiek kanaal met een bestand of een link.
        
        Gebruik:
          !sendfile <bestand_paad_of_link> [contextbericht]

        Voorbeeld:
          !sendfile http://example.com/myfile.pdf "Bekijk dit document"
          !sendfile ./files/document.pdf "Hier is het document."
        """
        # Haal het kanaal op waar het bericht naartoe moet
        channel = self.bot.get_channel(config.SEND_CHANNEL_ID)
        if channel is None:
            await ctx.send("Het opgegeven kanaal is niet gevonden.")
            return

        # Als het argument begint met "http", beschouwen we dit als een link
        if file_or_link.lower().startswith("http"):
            content = f"{context}\n{file_or_link}" if context else file_or_link
            await channel.send(content=content)
            await ctx.send("Link verstuurd!")
        else:
            # Anders proberen we het argument te openen als een bestand
            try:
                file = discord.File(file_or_link)
            except Exception as e:
                await ctx.send(f"Fout bij het openen van het bestand: {e}")
                return

            content = context if context else ""
            await channel.send(content=content, file=file)
            await ctx.send("Bestand verstuurd!")

def setup(bot):
    bot.add_cog(CustomCommands(bot))
