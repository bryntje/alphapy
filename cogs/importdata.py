import discord
import asyncpg
import json
from discord.ext import commands
from typing import Optional
import config

class ImportData(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None

    async def setup_database(self):
        self.db = await asyncpg.create_pool(config.DATABASE_URL)
        assert self.db is not None
        async with self.db.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS onboarding (
                    user_id BIGINT PRIMARY KEY,
                    responses JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')

    @commands.command(name="import_onboarding")
    @commands.is_owner()
    async def import_onboarding(self, ctx):
        """Importeer onboarding data uit embed berichten in het logkanaal."""
        channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("Kanaal niet gevonden!")
            return

        async for message in channel.history(limit=1000):  # Pas aan indien nodig
            if not message.embeds:
                continue

            embed = message.embeds[0]
            description = embed.description or ""
            if "(" not in description or ")" not in description:
                continue

            try:
                user_field = description.split("(")[1].split(")")[0]
            except IndexError:
                continue

            user_id = int(user_field) if user_field.isdigit() else None

            if not user_id:
                continue

            responses = {}
            for field in embed.fields:
                question_raw = field.name or ""
                answer_raw = field.value or ""
                question = question_raw.strip()
                answer = answer_raw.strip()
                responses[question] = answer

            assert self.db is not None
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO onboarding (user_id, responses)
                    VALUES ($1, $2)
                    ON CONFLICT(user_id) DO UPDATE SET responses = $2;
                    """,
                    user_id, json.dumps(responses)
                )
            print(f'✅ Geïmporteerd: {user_id}')
        
        await ctx.send("✅ Import voltooid!")

async def setup(bot: commands.Bot):
    cog = ImportData(bot)
    await bot.add_cog(cog)
    await cog.setup_database()
