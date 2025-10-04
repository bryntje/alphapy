import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
import config
import asyncio

from typing import Optional, Dict

from utils.logger import logger

class InviteTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invites_cache = {}  # Hier slaan we de invites op
        self.settings = getattr(bot, "settings", None)
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Laad de bestaande invites bij bot-start."""
        await self.bot.wait_until_ready()  # Wacht tot de bot klaar is
        if not self._is_enabled():
            logger.info("📴 InviteTracker staat uit; cache wordt niet geladen.")
            return
        for guild in self.bot.guilds:
            try:
                self.invites_cache[guild.id] = await guild.invites()
            except Exception as exc:
                logger.warning(f"⚠️ InviteTracker: kon invites niet laden voor guild {guild.id}: {exc}")
        logger.info("✅ Invite cache geladen!")

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

    def _is_enabled(self) -> bool:
        if self.settings:
            try:
                return bool(self.settings.get("invites", "enabled"))
            except KeyError:
                pass
        return True

    def _get_announcement_channel_id(self) -> Optional[int]:
        if self.settings:
            try:
                value = self.settings.get("invites", "announcement_channel_id")
                if value:
                    return int(value)
            except KeyError:
                pass
            except (TypeError, ValueError):
                logger.warning("⚠️ InviteTracker: announcement_channel_id ongeldig in settings.")
        return getattr(config, "INVITE_ANNOUNCEMENT_CHANNEL_ID", 0)

    def _get_template(self, *, with_inviter: bool) -> str:
        key = "with_inviter_template" if with_inviter else "no_inviter_template"
        if self.settings:
            try:
                value = self.settings.get("invites", key)
                if isinstance(value, str) and value.strip():
                    return value
            except KeyError:
                pass
        defaults = {
            True: "{member} joined! {inviter} now has {count} invites.",
            False: "{member} joined, but no inviter data found.",
        }
        return defaults[with_inviter]

    def _render_template(
        self,
        template: str,
        *,
        member: discord.Member,
        inviter: Optional[discord.abc.User],
        count: Optional[int],
    ) -> str:
        context: Dict[str, str] = {
            "member": member.mention,
            "member_name": member.display_name,
            "inviter": inviter.mention if inviter and hasattr(inviter, "mention") else (inviter.name if inviter else ""),
            "inviter_name": (
                inviter.display_name
                if inviter and hasattr(inviter, "display_name")
                else (inviter.name if inviter else "")
            ),
            "count": str(count) if count is not None else "0",
        }
        try:
            return template.format(**context)
        except KeyError as exc:
            logger.warning(f"⚠️ InviteTracker: ontbrekende placeholder in template: {exc}")
            return template

    @app_commands.command(name="inviteleaderboard", description="Toon een leaderboard van de hoogste invite counts.")
    async def inviteleaderboard(self, interaction: discord.Interaction, limit: int = 10):
        if not self._is_enabled():
            await interaction.response.send_message("⚠️ Invite tracker staat momenteel uit.")
            return
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
        if not self._is_enabled():
            await interaction.response.send_message("⚠️ Invite tracker staat momenteel uit.")
            return
        await self.update_invite_count(member.id, count)
        await interaction.response.send_message(f"Invite count for {member.display_name} is set to {count}.")

    @app_commands.command(name="resetinvites", description="Reset het invite aantal voor een gebruiker naar 0.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def resetinvites(self, interaction: discord.Interaction, member: discord.Member):
        if not self._is_enabled():
            await interaction.response.send_message("⚠️ Invite tracker staat momenteel uit.")
            return
        await self.update_invite_count(member.id, 0)
        await interaction.response.send_message(f"Invite count for {member.display_name} has been reset to 0.")
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self._is_enabled():
            return
        await self.bot.wait_until_ready()  # Zorg dat de bot klaar is

        # Wacht kort om Discord de tijd te geven om invites bij te werken
        await asyncio.sleep(1)

        guild = member.guild
        try:
            new_invites = await guild.invites()
        except Exception as e:
            print(f"⚠️ Kan guild invites niet ophalen: {e}")
            return
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
        channel_id = self._get_announcement_channel_id()
        if not channel_id:
            logger.warning("⚠️ InviteTracker: announcement channel niet ingesteld.")
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.warning("⚠️ InviteTracker: kon announcement channel niet vinden of betreden.")
            return

        conn: Optional[asyncpg.Connection] = None

        if inviter:
            await self.update_invite_count(inviter.id)
            # Haal de huidige invite count op na de update
            try:
                conn = await asyncpg.connect(config.DATABASE_URL)
                row = await conn.fetchrow("SELECT invite_count FROM invite_tracker WHERE user_id = $1", inviter.id)
            except Exception as e:
                logger.warning(f"⚠️ InviteTracker: DB-fout bij ophalen invite_count: {e}")
                row = None
            finally:
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass

            invite_count = row["invite_count"] if row else 0
            message = self._render_template(
                self._get_template(with_inviter=True),
                member=member,
                inviter=inviter,
                count=invite_count,
            )
            await channel.send(message)
        else:
            message = self._render_template(
                self._get_template(with_inviter=False),
                member=member,
                inviter=None,
                count=None,
            )
            await channel.send(message)

        logger.info(f"✅ InviteTracker: bericht gestuurd in {getattr(channel, 'name', channel_id)} voor {member}") 


async def setup(bot: commands.Bot):
    invite_tracker = InviteTracker(bot)
    await bot.add_cog(invite_tracker)
    await invite_tracker.setup_database()  # Zorg dat de database wordt geconfigureerd
