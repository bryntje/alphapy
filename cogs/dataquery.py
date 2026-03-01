import discord
from discord import app_commands
from discord.ext import commands
import config
from utils.validators import requires_owner
import csv
import os
import asyncpg
from typing import Optional
from utils.db_helpers import acquire_safe, is_pool_healthy


class DataQuery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None
        from utils.database_helpers import DatabaseManager
        self._db_manager = DatabaseManager("dataquery", {"DATABASE_URL": config.DATABASE_URL})

    async def setup_database(self):
        """Create database connection and table if not present."""
        self.db = await self._db_manager.ensure_pool()
        assert self.db is not None
        async with self._db_manager.connection() as connection:
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

    @app_commands.command(name="export_onboarding", description="Export onboarding data as CSV (owner only).")
    @requires_owner()
    async def export_onboarding(self, interaction: discord.Interaction):
        await interaction.response.defer()

        csv_filename = "onboarding_data.csv"
        
        if not is_pool_healthy(self.db):
            await interaction.followup.send("Database not available.", ephemeral=True)
            return
        async with acquire_safe(self.db) as connection:
            rows = await connection.fetch("SELECT * FROM onboarding")

        if not rows:
            await interaction.followup.send("No onboarding data found.", ephemeral=True)
            return

        columns = ["id", "user_id", "responses", "timestamp"]
        with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(columns)
            csv_writer.writerows([list(row) for row in rows])

        file = discord.File(csv_filename)
        await interaction.followup.send("Exported onboarding data:", file=file)
        os.remove(csv_filename)

async def setup(bot: commands.Bot):
    await bot.add_cog(DataQuery(bot))
    # Command sync is now handled centrally in bot.py on_ready() hook
    # This prevents blocking startup and respects rate limits
