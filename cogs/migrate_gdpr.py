import asyncpg
import sqlite3
import discord
from discord.ext import commands
import config
from datetime import datetime
from utils.logger import logger

class GDPRMigration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def setup_database(self):
        """Maakt de GDPR-tabel aan als deze nog niet bestaat."""
        pg_conn = await asyncpg.connect(config.DATABASE_URL)

        await pg_conn.execute("""
            CREATE TABLE IF NOT EXISTS gdpr_acceptance (
                user_id BIGINT PRIMARY KEY,
                accepted INTEGER DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await pg_conn.close()
        logger.info("GDPR table checked/created")


    @commands.command(name="migrate_gdpr")
    @commands.is_owner()
    async def migrate_gdpr(self, ctx):
        """Migreert GDPR-gegevens van SQLite naar PostgreSQL."""
        await ctx.send("📦 GDPR-migratie gestart... Dit kan even duren!")
        await self.setup_database()

        # ✅ Stap 1: Connectie met SQLite
        sqlite_conn = sqlite3.connect("onboarding.db")
        sqlite_cursor = sqlite_conn.cursor()

        # ✅ Stap 2: GDPR-data ophalen
        sqlite_cursor.execute("SELECT user_id, accepted, timestamp FROM gdpr_acceptance")
        data = sqlite_cursor.fetchall()

        if not data:
            await ctx.send("❌ Geen GDPR-data gevonden in SQLite.")
            return

        await ctx.send(f"📦 {len(data)} GDPR-records gevonden, starten met migratie...")

        # ✅ Stap 3: Connectie met PostgreSQL
        pg_conn = await asyncpg.connect(config.DATABASE_URL)

        for user_id, accepted, timestamp in data:
            timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            # ✅ Stap 4: GDPR-data invoegen in PostgreSQL
            await pg_conn.execute(
                """
                INSERT INTO gdpr_acceptance (user_id, accepted, timestamp)
                VALUES ($1, $2, $3)
                ON CONFLICT(user_id) DO UPDATE SET accepted = $2, timestamp = $3;
                """,
                int(user_id), accepted, timestamp
            )

        # ✅ Stap 5: Connecties sluiten
        await pg_conn.close()
        sqlite_conn.close()

        await ctx.send("✅ GDPR-migratie voltooid! 🎉")

async def setup(bot):
    await bot.add_cog(GDPRMigration(bot))
