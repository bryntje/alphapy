import discord
import asyncpg
import re
from typing import Optional
from discord.ext import commands
import config
from utils.logger import log_with_guild

class ImportInvites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None

    async def setup_database(self):
        self.db = await asyncpg.create_pool(config.DATABASE_URL)
        assert self.db is not None
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
        # Gebruik guild-specifieke announcement kanaal setting
        try:
            announcement_channel_id = int(self.bot.settings.get("invites", "announcement_channel_id", ctx.guild.id))
            if announcement_channel_id == 0:
                await ctx.send("❌ Invite announcement kanaal niet geconfigureerd voor deze server. Stel eerst `/config invites announcement_channel_id #invites` in.")
                return
        except (KeyError, ValueError):
            await ctx.send("❌ Invite announcement kanaal niet geconfigureerd voor deze server. Stel eerst `/config invites announcement_channel_id #invites` in.")
            return

        channel = self.bot.get_channel(announcement_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("Invite announcement kanaal niet gevonden! Configureer eerst `/config invites announcement_channel_id` voor deze server.")
            return

        invite_counts = {}
        pattern_invited = re.compile(r'<@(\d+)> has been invited by <@(\d+)> and now has (\d+) invites?\.')
        pattern_joined = re.compile(r'<@(\d+)> joined! <@(\d+)> now has (\d+) invites?\.')


        print(f"🔍 Kanaal check: {channel} (ID: {announcement_channel_id}) voor guild {ctx.guild.name}")
        async for message in channel.history(limit=1000):  # Pas aan indien nodig
            match = pattern_invited.search(message.content) or pattern_joined.search(message.content)
            print(f"📩 Bericht gevonden: {message.content}")
            if match:
                print(f"✅ Regex match: {match.groups()}")  # ✅ Debug of regex werkt
                _, inviter_mention, count = match.groups()
                inviter = int(re.sub(r'[^\d]', '', inviter_mention))
                print(f"✅ Gevonden: {inviter} heeft nu {count} invites.")
                count = int(count)
                invite_counts[inviter] = max(invite_counts.get(inviter, 0), count)
            else:
                print(f"❌ Geen match: {message.content}")  # ❌ Debug als er GEEN match is

        assert self.db is not None
        async with self.db.acquire() as conn:
            for inviter, count in invite_counts.items():
                print(f"📌 Opslaan: {inviter} → {count} invites")
                await conn.execute(
                    """
                    INSERT INTO invite_tracker (user_id, invite_count)
                    VALUES ($1, $2)
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
