import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
import config
import asyncio

class InviteTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invites_cache = {}  # Hier slaan we de invites op
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Laad de bestaande invites bij bot-start."""
        await self.bot.wait_until_ready()  # Wacht tot de bot klaar is
        for guild in self.bot.guilds:
            self.invites_cache[guild.id] = await guild.invites()
        print("✅ Invite cache geladen!")

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

    async def update_invite_count(self, inviter_id: int, count: int = None):
        """Verhoog of stel de invite count in de database in."""
        conn = await asyncpg.connect(config.DATABASE_URL)
    
        if count is None:
            # Verhoog de invites met 1 als er geen specifieke waarde wordt gegeven
            await conn.execute(
                """
                INSERT INTO invite_tracker (user_id, invite_count)
                VALUES ($1, 1)
                ON CONFLICT(user_id) DO UPDATE SET invite_count = invite_tracker.invite_count + 1;
                """,
                inviter_id
            )
        else:
            # Stel het aantal invites handmatig in
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
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setinvites(self, interaction: discord.Interaction, member: discord.Member, count: int):
        await self.update_invite_count(member.id, count)
        await interaction.response.send_message(f"Invite count for {member.display_name} is set to {count}.")

    @app_commands.command(name="resetinvites", description="Reset het invite aantal voor een gebruiker naar 0.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def resetinvites(self, interaction: discord.Interaction, member: discord.Member):
        await self.update_invite_count(member.id, 0)
        await interaction.response.send_message(f"Invite count for {member.display_name} has been reset to 0.")
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.bot.wait_until_ready()  # Zorg dat de bot klaar is

        # Wacht kort om Discord de tijd te geven om invites bij te werken
        await asyncio.sleep(1)

        guild = member.guild
        new_invites = await guild.invites()
        old_invites = self.invites_cache.get(guild.id, [])

        inviter = None

        # Zoek de invite die gebruikt is
        for old_invite in old_invites:
            for new_invite in new_invites:
                if old_invite.code == new_invite.code and old_invite.uses < new_invite.uses:
                    inviter = new_invite.inviter
                    break
        
        # Update de cache met de nieuwe invites
        self.invites_cache[guild.id] = new_invites

        # Stuur een bericht in het kanaal
        channel = guild.get_channel(config.INVITE_ANNOUNCEMENT_CHANNEL_ID)
        if not channel:
            print("⚠️ Kanaal niet gevonden! Controleer config.INVITE_ANNOUNCEMENT_CHANNEL_ID")
            return

        if inviter:
            await self.update_invite_count(inviter.id)
            # Haal de huidige invite count op na de update
            conn = await asyncpg.connect(config.DATABASE_URL)
            row = await conn.fetchrow("SELECT invite_count FROM invite_tracker WHERE user_id = $1", inviter.id)
            await conn.close()

            invite_count = row["invite_count"] if row else "an unknown number of"

            await channel.send(f"{member.mention} joined! {inviter.mention} now has {invite_count} invites.")
        else:
            await channel.send(f"{member.mention} joined, but no inviter data found.")

        print(f"✅ Bericht gestuurd in {channel.name} voor {member.name}") 


async def setup(bot: commands.Bot):
    invite_tracker = InviteTracker(bot)
    await bot.add_cog(invite_tracker)
    await invite_tracker.setup_database()  # Zorg dat de database wordt geconfigureerd

