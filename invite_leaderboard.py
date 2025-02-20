import discord
from discord.ext import commands
import sqlite3
import logging
import config
from checks import is_owner_or_admin

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def update_invite_count(inviter_id: str, count: int = None):
    """
    Verhoogt de globale invite teller voor een gebruiker met 1 als count None is,
    of stelt de teller in op de opgegeven count als deze is meegegeven.
    """
    conn = sqlite3.connect("invite_tracker.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS invite_tracker (
            user_id TEXT PRIMARY KEY,
            invite_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    if count is None:
        # Verhoog met 1
        c.execute("""
            INSERT INTO invite_tracker (user_id, invite_count)
            VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET invite_count = invite_count + 1;
        """, (str(inviter_id),))
    else:
        # Stel de teller in op de opgegeven count
        c.execute("""
            INSERT INTO invite_tracker (user_id, invite_count)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET invite_count = ?;
        """, (str(inviter_id), count, count))
    conn.commit()
    conn.close()

class InviteTracker(commands.Cog):
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
                self.invite_cache[guild.id] = {invite.code: invite.uses for invite in invites}
                logger.info(f"Loaded invites for guild {guild.id}")
            except Exception as e:
                logger.error(f"Error loading invites for guild {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        try:
            new_invites = await guild.invites()
        except Exception as e:
            logger.error(f"Error fetching invites for guild {guild.id}: {e}")
            return

        old_invites = self.invite_cache.get(guild.id, {})

        # Controleer of er invite-codes zijn die eerder aanwezig waren maar nu ontbreken
        missing_codes = set(old_invites.keys()) - {invite.code for invite in new_invites}
        if missing_codes:
            logger.info(f"In guild {guild.id}, missing invite codes: {missing_codes}")

        # Controleer op resets: als een invite-code al in de cache stond maar nu een lagere uses heeft
        for invite in new_invites:
            if invite.code in old_invites:
                old_count = old_invites[invite.code]
                if invite.uses < old_count:
                    logger.warning(f"Invite code {invite.code} lijkt gereset: oude uses {old_count}, nieuwe uses {invite.uses}")

        # Zoek de invite die is gebruikt (toename in uses)
        used_invite = None
        for invite in new_invites:
            if invite.code in old_invites and invite.uses > old_invites[invite.code]:
                used_invite = invite
                break

        if used_invite:
            inviter = used_invite.inviter
            logger.info(f"{member} joined using invite {used_invite.code} from {inviter}")
            update_invite_count(inviter.id)
            # Haal de nieuwe teller op voor een optionele aankondiging
            conn = sqlite3.connect("invite_tracker.db")
            c = conn.cursor()
            c.execute("SELECT invite_count FROM invite_tracker WHERE user_id = ?", (str(inviter.id),))
            row = c.fetchone()
            current_count = row[0] if row else 0
            conn.close()

            announcement_channel = self.bot.get_channel(config.INVITE_ANNOUNCEMENT_CHANNEL_ID)
            if announcement_channel:
                await announcement_channel.send(
                    f"{member.mention} joined! {inviter.mention} now has {current_count} invites."
                )
        else:
            logger.info(f"Geen gebruikte invite gevonden voor {member}. Mogelijk is er een reset of ontbrekende invite.")

        # Update de cache voor deze guild
        self.invite_cache[guild.id] = {invite.code: invite.uses for invite in new_invites}

    @commands.command(name="recalc_invites", help="Herschal alle invites van een gebruiker en update de teller.")
    @is_owner_or_admin()
    async def recalc_invites(self, ctx, member: discord.Member):
        total_invites = 0
        try:
            # Loop door alle guilds waarin de bot zit
            for guild in self.bot.guilds:
                invites = await guild.invites()
                for invite in invites:
                    if invite.inviter and invite.inviter.id == member.id:
                        total_invites += invite.uses
        except Exception as e:
            logger.error(f"Error recalculating invites: {e}")
            await ctx.send("Er is een fout opgetreden tijdens het herberekenen van de invites.")
            return

        update_invite_count(member.id, total_invites)
        await ctx.send(f"De totale invites voor {member.display_name} zijn bijgewerkt naar {total_invites}.")

    @commands.command(name="inviteleaderboard", help="Toon een leaderboard van de hoogste invite counts.")
    async def inviteleaderboard(self, ctx, limit: int = 10):
        conn = sqlite3.connect("invite_tracker.db")
        c = conn.cursor()
        c.execute("SELECT user_id, invite_count FROM invite_tracker ORDER BY invite_count DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            await ctx.send("Er is nog geen invite data beschikbaar.")
            return

        embed = discord.Embed(title="Invite Leaderboard", color=discord.Color.gold())
        for idx, (user_id, invite_count) in enumerate(rows, start=1):
            member = ctx.guild.get_member(int(user_id))
            name = member.display_name if member else f"User {user_id}"
            embed.add_field(name=f"{idx}. {name}", value=f"Invites: {invite_count}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="setinvites", help="Stelt handmatig het aantal invites voor een gebruiker in.")
    @is_owner_or_admin()
    async def setinvites(self, ctx, member: discord.Member, count: int):
        update_invite_count(member.id, count)
        await ctx.send(f"Invite count for {member.display_name} is set to {count}.")

    @commands.command(name="resetinvites", help="Reset het invite aantal voor een gebruiker naar 0.")
    @commands.has_permissions(manage_guild=True)
    async def resetinvites(self, ctx, member: discord.Member):
        update_invite_count(member.id, 0)
        await ctx.send(f"Invite count for {member.display_name} has been reset to 0.")

async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTracker(bot))
