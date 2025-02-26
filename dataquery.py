import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import json
import datetime
import config
from checks import is_owner_or_admin

class DataQuery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = "onboarding.db"  # Zorg dat dit het juiste pad is

    @app_commands.command(
        name="querydata",
        description="Query de onboarding data met optionele filters."
    )
    @app_commands.describe(
        member="Filter op gebruiker (optioneel)",
        days="Toon data van de afgelopen X dagen (optioneel)",
        limit="Maximaal aantal resultaten (standaard 10)"
    )
    @is_owner_or_admin()
    async def querydata(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None,
        days: int = None,
        limit: int = 10
    ):
        await interaction.response.defer()  # 👈 voorkomt een timeout
    
        query = "SELECT user_id, responses, timestamp FROM onboarding WHERE 1=1"
        params = []
    
        if member is not None:
            query += " AND user_id = ?"
            params.append(str(member.id))
    
        if days is not None:
            since_time = datetime.datetime.now() - datetime.timedelta(days=days)
            since_str = since_time.strftime("%Y-%m-%d %H:%M:%S")
            query += " AND timestamp >= ?"
            params.append(since_str)
    
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
    
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
    
        if not rows:
            await interaction.followup.send("Geen resultaten gevonden met de opgegeven filters.", ephemeral=True)
            return
    
        embed = discord.Embed(title="Onboarding Data Query Results", color=discord.Color.blue())
        for row in rows:
            user_id = row["user_id"]
            responses = row["responses"]
            timestamp = row["timestamp"]
            try:
                responses_dict = json.loads(responses)
                responses_str = json.dumps(responses_dict, indent=2)
            except Exception:
                responses_str = responses
            embed.add_field(
                name=f"User: {user_id} | {timestamp}",
                value=f"Responses:\n```json\n{responses_str}```",
                inline=False
            )
    
        await interaction.followup.send(embed=embed, ephemeral=True)  # 👈 Gebruik followup voor vertraagde response


async def setup(bot: commands.Bot):
    await bot.add_cog(DataQuery(bot))
    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(id=config.GUILD_ID))