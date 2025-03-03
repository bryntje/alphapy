import discord
import asyncpg
import re
from discord.ext import commands
import config

class ImportInvites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = None

    async def setup_database(self):
        self.db = await asyncpg.create_pool(config.DATABASE_URL)
        async with self.db.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS invite_tracker (
                    user_id BIGINT PRIMARY KEY,
                    invite_count INTEGER DEFAULT 0
                );
            ''')

    @commands.command(name="import_invites")
    @commands.is_owner()
    async def import_invites(self, ctx):
        """Importeer invites vanuit het invite-tracker kanaal."""
        channel = self.bot.get_channel(config.INVITE_ANNOUNCEMENT_CHANNEL_ID)
        if not channel:
            await ctx.send("Kanaal niet gevonden!")
            return

        invite_counts = {}
        pattern = re.compile(r'@(.+?) joined! @(.+?) now has (\d+) invites?\.')

        async for message in channel.history(limit=1000):  # Pas aan indien nodig
            match = pattern.search(message.content)
            if match:
                _, inviter, count = match.groups()
                print(f"✅ Gevonden: {inviter} heeft nu {count} invites.")
                count = int(count)
                invite_counts[inviter] = max(invite_counts.get(inviter, 0), count)

        async with self.db.acquire() as conn:
            for inviter, count in invite_counts.items():
                print(f"📌 Opslaan: {inviter} → {count} invites")
                await conn.execute(
                    """
                    INSERT INTO invite_tracker (user_id, invite_count)
                    VALUES ((SELECT id FROM users WHERE username = $1), $2)
                    ON CONFLICT(user_id) DO UPDATE SET invite_count = $2;
                    """,
                    inviter, count
                )
                print(f'✅ Geïmporteerd: {inviter} met {count} invites')
        
        await ctx.send("✅ Import voltooid!")

async def setup(bot: commands.Bot):
    cog = ImportInvites(bot)
    await bot.add_cog(cog)
    await cog.setup_database()