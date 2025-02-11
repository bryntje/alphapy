import discord
from discord.ext import commands
import sqlite3
import logging
import config
from checks import is_owner_or_admin 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def update_invite_count(inviter_id: str, new_count: int):
    """Werk de invite count voor een bepaalde inviter bij in de database."""
    conn = sqlite3.connect("invite_tracker.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS invite_tracker (
            user_id TEXT PRIMARY KEY,
            invite_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    c.execute("REPLACE INTO invite_tracker (user_id, invite_count) VALUES (?, ?)", (str(inviter_id), new_count))
    conn.commit()
    conn.close()

def get_invite_leaderboard(limit: int = 10):
    """Haal de top 'limit' gebruikers op uit de invite tracker database."""
    conn = sqlite3.connect("invite_tracker.db")
    c = conn.cursor()
    c.execute("SELECT user_id, invite_count FROM invite_tracker ORDER BY invite_count DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

class InviteTracker(commands.Cog):
    """Cog die invite data bijhoudt en een leaderboard genereert."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Cache per guild: {guild_id: {invite.code: invite.uses, ...}}
        self.invite_cache = {}

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Loading invite data for all guilds...")
        for guild in self.bot.guilds:
            try:
                invites = await guild.invites()
                # Sla de huidige uses op in de cache per guild
                self.invite_cache[guild.id] = {invite.code: invite.uses for invite in invites}
                logger.info(f"Loaded invites for guild {guild.id}")
            except Exception as e:
                logger.error(f"Error loading invites for guild {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        print(f"Member joined: {member}")
        guild = member.guild
        try:
            new_invites = await guild.invites()
        except Exception as e:
            logger.error(f"Error fetching invites for guild {guild.id}: {e}")
            return
    
        old_invites = self.invite_cache.get(guild.id, {})
        used_invite = None
    
        # Vergelijk de oude en nieuwe invites om te bepalen welke invite is gebruikt
        for invite in new_invites:
            if invite.code in old_invites and invite.uses > old_invites[invite.code]:
                used_invite = invite
                break
            
        if used_invite:
            inviter = used_invite.inviter
            logger.info(f"{member} joined using invite {used_invite.code} from {inviter}")
    
            # Haal de huidige invite count op voor de inviter uit de database
            try:
                conn = sqlite3.connect("invite_tracker.db")
                c = conn.cursor()
                c.execute("CREATE TABLE IF NOT EXISTS invite_tracker (user_id TEXT PRIMARY KEY, invite_count INTEGER DEFAULT 0)")
                conn.commit()
                c.execute("SELECT invite_count FROM invite_tracker WHERE user_id = ?", (str(inviter.id),))
                row = c.fetchone()
                current_count = row[0] if row else 0
                conn.close()
            except Exception as e:
                logger.error(f"Error fetching invite count: {e}")
                current_count = 0
    
            new_count = current_count + 1
            update_invite_count(inviter.id, new_count)
    
            # Verstuur een announcement-bericht naar het aangewezen kanaal
            announcement_channel = self.bot.get_channel(config.INVITE_ANNOUNCEMENT_CHANNEL_ID)
            if announcement_channel:
                print("Announcement branch reached")
                await announcement_channel.send(
                    f"{member.mention} has been invited by {inviter.mention} and now has {new_count} invites."
                )
    
        # Werk de cache voor deze guild bij met de nieuwe invite data
        self.invite_cache[guild.id] = {invite.code: invite.uses for invite in new_invites}

    @commands.command(name="resetinvite")
    @is_owner_or_admin()  # Of gebruik een eigen check, zoals is_owner_or_admin()
    async def reset_invite(self, ctx, member: discord.Member):
        """
        Reset the invite counter for a specified member back to 0.
        Usage: !resetinvite @member
        """
        # Open de database en voer een update-query uit om de invite_count op 0 te zetten
        try:
            conn = sqlite3.connect("invite_tracker.db")
            c = conn.cursor()
            # Zorg dat de tabel bestaat
            c.execute("""
                CREATE TABLE IF NOT EXISTS invite_tracker (
                    user_id TEXT PRIMARY KEY,
                    invite_count INTEGER DEFAULT 0
                )
            """)
            conn.commit()
            # Update de invite_count naar 0 voor de opgegeven member
            c.execute("REPLACE INTO invite_tracker (user_id, invite_count) VALUES (?, ?)", (str(member.id), 0))
            conn.commit()
            conn.close()
            await ctx.send(f"Invite counter for {member.display_name} has been reset to 0.")
        except Exception as e:
            await ctx.send(f"An error occurred while resetting the invite counter: {e}")
    
    @commands.command(name="setinvites")
    @is_owner_or_admin()
    async def set_invites(self, ctx, member: discord.Member, count: int):
        """
        Manually set the invite count for a specific member.
        Usage: !setinvites @Member 42
        """
        try:
            update_invite_count(member.id, count)
            await ctx.send(f"Invite count for {member.mention} has been set to {count}.")
        except Exception as e:
            await ctx.send(f"An error occurred while updating invite count: {e}")

    @commands.command(name="inviteleaderboard")
    async def invite_leaderboard(self, ctx, limit: int = 10):
        """
        Genereert een leaderboard gebaseerd op het aantal succesvolle invites.
        Gebruik:
          !inviteleaderboard [limit]
        """
        leaderboard = get_invite_leaderboard(limit)
        if not leaderboard:
            await ctx.send("No invite data available.")
            return

        embed = discord.Embed(
            title="Invite Leaderboard",
            description="Top users by number of successful invites",
            color=discord.Color.gold()
        )
        for idx, (user_id, invite_count) in enumerate(leaderboard, start=1):
            member = ctx.guild.get_member(int(user_id))
            name = member.display_name if member else f"User {user_id}"
            embed.add_field(name=f"{idx}. {name}", value=f"Invites: {invite_count}", inline=False)

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTracker(bot))
