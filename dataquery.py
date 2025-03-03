import discord
from discord import app_commands
from discord.ext import commands
import config
from checks import is_owner_or_admin
import csv
import os
import asyncpg

class DataQuery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None  # Database pool variabele

    async def setup_database(self):
        """Maakt de database connectie en tabel aan als die nog niet bestaat."""
        self.db = await asyncpg.create_pool(dsn=config.DATABASE_URL)
        
        async with self.db.acquire() as connection:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS onboarding (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE,
                    responses JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    async def cog_load(self):
        """Wordt automatisch uitgevoerd wanneer de cog geladen wordt."""
        await self.setup_database()

    @app_commands.command(name="export_onboarding", description="Exporteer onboarding data als een CSV-bestand.")
    @commands.is_owner()
    async def export_onboarding(self, interaction: discord.Interaction):
        await interaction.response.defer()

        csv_filename = "onboarding_data.csv"
        
        async with self.db.acquire() as connection:
            rows = await connection.fetch("SELECT * FROM onboarding")

        if not rows:
            await interaction.followup.send("⚠️ Geen onboarding data gevonden!", ephemeral=True)
            return
        
        # Kolomnamen ophalen
        columns = ["id", "user_id", "responses", "timestamp"]

        # Schrijf data naar CSV-bestand
        with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(columns)  # Kolomnamen in de eerste rij
            csv_writer.writerows([list(row) for row in rows])  # Data schrijven

        # Upload CSV-bestand naar Discord
        file = discord.File(csv_filename)
        await interaction.followup.send("📂 Hier is de geëxporteerde onboarding data:", file=file)

        # Verwijder bestand na verzending
        os.remove(csv_filename)

async def setup(bot: commands.Bot):
    await bot.add_cog(DataQuery(bot))
    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(id=config.GUILD_ID))