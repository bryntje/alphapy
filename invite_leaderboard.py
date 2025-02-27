import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
import config

class InviteTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def setup_database(self):
        """Initialiseer de PostgreSQL database en maak tabellen aan indien nodig."""
        conn = await asyncpg.connect(config.DATABASE_URL)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS invite_tracker (
                user_id BIGINT PRIMARY KEY,
                invite_count INTEGER DEFAULT 0
            );
        ''')
        await conn.close()

    async def update_invite_count(self, inviter_id, count=None):
        """Werk de invite count bij voor een gebruiker."""
        conn = await asyncpg.connect(config.DATABASE_URL)
        if count is None:
            await conn.execute(
                """
                INSERT INTO invite_tracker (user_id, invite_count)
                VALUES ($1, 1)
                ON CONFLICT(user_id) DO UPDATE SET invite_count = invite_tracker.invite_count + 1;
                """,
                inviter_id
            )
        else:
            await conn.execute(
                """
                INSERT INTO invite_tracker (user_id, invite_count)
                VALUES ($1, $2)
                ON CONFLICT(user_id) DO UPDATE SET invite_count = $2;
                """,
                inviter_id, count
            )
        await conn.close()

    async def get_invite_leaderboard(self, limit=10):
        """Haal de top gebruikers op met de meeste invites."""
        conn = await asyncpg.connect(config.DATABASE_URL)
        rows = await conn.fetch(
            "SELECT user_id, invite_count FROM invite_tracker ORDER BY invite_count DESC LIMIT $1",
            limit
        )
        await conn.close()
        return rows

    @app_commands.command(name="inviteleaderboard", description="Toon een leaderboard van de hoogste invite counts.")
    async def inviteleaderboard(self, interaction: discord.Interaction, limit: int = 10):
        rows = await self.get_invite_leaderboard(limit)
        if not rows:
            await interaction.response.send_message("Er is nog geen invite data beschikbaar.")
            return

        embed = discord.Embed(title="Invite Leaderboard", color=discord.Color.gold())
        for idx, row in enumerate(rows, start=1):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"User {row['user_id']}"
            embed.add_field(name=f"{idx}. {name}", value=f"Invites: {row['invite_count']}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setinvites", description="Stelt handmatig het aantal invites voor een gebruiker in.")
    @commands.has_permissions(manage_guild=True)
    async def setinvites(self, interaction: discord.Interaction, member: discord.Member, count: int):
        await self.update_invite_count(member.id, count)
        await interaction.response.send_message(f"Invite count for {member.display_name} is set to {count}.")

    @app_commands.command(name="resetinvites", description="Reset het invite aantal voor een gebruiker naar 0.")
    @commands.has_permissions(manage_guild=True)
    async def resetinvites(self, interaction: discord.Interaction, member: discord.Member):
        await self.update_invite_count(member.id, 0)
        await interaction.response.send_message(f"Invite count for {member.display_name} has been reset to 0.")

async def setup(bot: commands.Bot):
    invite_tracker = InviteTracker(bot)
    await bot.add_cog(invite_tracker)
    await invite_tracker.setup_database()

    # ✅ Forceer registratie van slash commands
    bot.tree.add_command(invite_tracker.inviteleaderboard)
    bot.tree.add_command(invite_tracker.setinvites)
    bot.tree.add_command(invite_tracker.resetinvites)

    await bot.tree.sync()

