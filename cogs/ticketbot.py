import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import checks as app_checks
import asyncpg
from datetime import datetime
from typing import Optional, List, cast

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.logger import logger
from utils.checks_interaction import is_owner_or_admin_interaction


class TicketBot(commands.Cog):
    """TicketBot MVP

    Deze Cog biedt een minimale `/ticket` slash command waarmee gebruikers
    een supportticket kunnen aanmaken. Tickets worden opgeslagen in PostgreSQL
    in de tabel `support_tickets`. Na aanmaak wordt er een bevestigings-embed
    gestuurd in het kanaal en wordt er tevens gelogd naar `WATCHER_LOG_CHANNEL`.

    Voorbereid op uitbreidingen zoals: claimen, closen, tagging, GPT-ondersteuning.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn: Optional[asyncpg.Connection] = None
        # Start async setup zonder de event loop te blokkeren
        self.bot.loop.create_task(self.setup_db())

    async def setup_db(self) -> None:
        """Initialiseer database connectie en zorg dat de tabel bestaat."""
        try:
            conn = await asyncpg.connect(config.DATABASE_URL)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    description TEXT NOT NULL,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            # Nieuwe kolom voor ticketkanaal
            try:
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS channel_id BIGINT;"
                )
            except Exception as e:
                logger.warning(f"⚠️ TicketBot: kon kolom channel_id niet toevoegen: {e}")
            # Backwards compatible schema upgrades
            try:
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS claimed_by BIGINT;"
                )
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;"
                )
            except Exception as e:
                logger.warning(f"⚠️ TicketBot: kon schema niet upgraden: {e}")
            # Indexen voor snellere queries later
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_user_id ON support_tickets(user_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_channel_id ON support_tickets(channel_id);"
            )
            # Handige index voor claims
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_claimed_by ON support_tickets(claimed_by);"
            )
            self.conn = conn
            logger.info("✅ TicketBot: DB ready (support_tickets)")
        except Exception as e:
            logger.error(f"❌ TicketBot: DB init error: {e}")

    async def send_log_embed(self, title: str, description: str, level: str = "info") -> None:
        """Stuur een log-embed naar het `WATCHER_LOG_CHANNEL` kanaal.

        Houdt gelijke stijl aan als andere cogs. Vervangt kleur per level.
        """
        try:
            color_map = {
                "info": 0x3498db,
                "debug": 0x95a5a6,
                "error": 0xe74c3c,
                "success": 0x2ecc71,
                "warning": 0xf1c40f,
            }
            color = color_map.get(level, 0x3498db)
            embed = discord.Embed(title=title, description=description, color=color)
            embed.set_footer(text="ticketbot")
            channel = self.bot.get_channel(getattr(config, "WATCHER_LOG_CHANNEL", 0))
            if channel and hasattr(channel, "send"):
                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"⚠️ TicketBot: kon log embed niet versturen: {e}")

    @app_commands.command(name="ticket", description="Maak een supportticket aan")
    @app_checks.cooldown(1, 30.0)  # simpele user cooldown
    @app_commands.describe(description="Korte omschrijving van je issue")
    async def ticket(self, interaction: discord.Interaction, description: str):
        """Slash command om een nieuw ticket aan te maken.

        - Slaat ticket op in `support_tickets`
        - Stuurt een bevestigings-embed met ticketdetails
        - Logt naar `WATCHER_LOG_CHANNEL`
        """
        await interaction.response.defer(ephemeral=True)

        # Zorg dat DB klaar is
        if self.conn is None:
            try:
                await self.setup_db()
            except Exception as e:
                logger.error(f"❌ TicketBot: DB connect error: {e}")
                await interaction.followup.send("❌ Database is niet beschikbaar. Probeer later opnieuw.")
                return

        user = interaction.user
        user_display = f"{user} ({user.id})"

        try:
            conn_safe = cast(asyncpg.Connection, self.conn)
            row = await conn_safe.fetchrow(
                """
                INSERT INTO support_tickets (user_id, username, description)
                VALUES ($1, $2, $3)
                RETURNING id, created_at
                """,
                int(user.id),
                str(user),
                description.strip(),
            )
        except Exception as e:
            logger.exception("🚨 TicketBot: insert failed")
            await self.send_log_embed(
                title="🚨 Ticket aanmaken mislukt",
                description=f"User: {user_display}\nFout: {e}",
                level="error",
            )
            await interaction.followup.send("❌ Er ging iets mis bij het aanmaken van je ticket.")
            return

        ticket_id: int
        created_at: datetime
        if row:
            ticket_id = int(row["id"])  # not None after successful insert
            created_at = row["created_at"]
        else:
            # Fallback: should not happen, but keep types safe
            ticket_id = 0
            created_at = datetime.utcnow()

        # Bevestigings-embed naar gebruiker (ephemeral followup)
        confirm = discord.Embed(
            title="🎟️ Ticket aangemaakt",
            description="Je ticket is succesvol aangemaakt.",
            color=discord.Color.green(),
            timestamp=created_at,
        )
        confirm.add_field(name="Ticket ID", value=str(ticket_id), inline=True)
        confirm.add_field(name="User", value=f"{user.mention}", inline=True)
        confirm.add_field(name="Status", value="open", inline=True)
        confirm.add_field(name="Omschrijving", value=description[:1024] or "—", inline=False)

        # Maak een dedicated kanaal aan onder opgegeven category met private overwrites
        channel_mention_text = "—"
        try:
            guild = interaction.guild
            if guild is None:
                raise RuntimeError("Guild context ontbreekt")

            # Category via config of fallback naar gegeven ID
            category_id = int(getattr(config, "TICKET_CATEGORY_ID", 1416148921960628275))
            fetched_channel = guild.get_channel(category_id) or await self.bot.fetch_channel(category_id)
            if not isinstance(fetched_channel, discord.CategoryChannel):
                raise RuntimeError("Category kanaal niet gevonden of geen category type")
            category = fetched_channel

            # Support role bepalen: TICKET_ACCESS_ROLE_ID > ADMIN_ROLE_ID (fallback)
            support_role_id_value: Optional[int] = None
            srid = getattr(config, "TICKET_ACCESS_ROLE_ID", None)
            if isinstance(srid, int):
                support_role_id_value = srid
            elif isinstance(srid, str) and srid.isdigit():
                support_role_id_value = int(srid)
            if support_role_id_value is None:
                admin_candidate = getattr(config, "ADMIN_ROLE_ID", None)
                if isinstance(admin_candidate, int):
                    support_role_id_value = admin_candidate
                elif isinstance(admin_candidate, list) and admin_candidate:
                    first_role = admin_candidate[0]
                    if isinstance(first_role, int):
                        support_role_id_value = first_role
                    elif isinstance(first_role, str) and first_role.isdigit():
                        support_role_id_value = int(first_role)
            support_role = guild.get_role(support_role_id_value) if support_role_id_value else None

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                ),
            }
            if support_role is not None:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )

            channel = await guild.create_text_channel(
                name=f"ticket-{ticket_id}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket {ticket_id} aangemaakt door {user}"
            )

            # Update DB met channel_id
            try:
                conn_safe2 = cast(asyncpg.Connection, self.conn)
                await conn_safe2.execute(
                    "UPDATE support_tickets SET channel_id = $1 WHERE id = $2",
                    int(channel.id),
                    ticket_id,
                )
            except Exception as e:
                logger.warning(f"⚠️ TicketBot: kon channel_id niet opslaan: {e}")

            # Initieel bericht in ticketkanaal
            ch_embed = discord.Embed(
                title="🎟️ Ticket aangemaakt",
                color=discord.Color.green(),
                timestamp=created_at,
                description=(
                    f"Ticket ID: `{ticket_id}`\n"
                    f"Gebruiker: {user.mention}\n"
                    f"Status: **open**\n\n"
                    f"Omschrijving:\n{description}"
                )
            )
            await channel.send(content=(support_role.mention if support_role else None), embed=ch_embed, allowed_mentions=discord.AllowedMentions(roles=True))

            channel_mention_text = channel.mention
            confirm.add_field(name="Kanaal", value=channel_mention_text, inline=False)
        except Exception as e:
            logger.warning(f"⚠️ TicketBot: kanaal aanmaken mislukt: {e}")
            confirm.add_field(name="Kanaal", value="(aanmaken mislukt)", inline=False)

        await interaction.followup.send(embed=confirm, ephemeral=True)
        if channel_mention_text != "—":
            await interaction.followup.send(f"✅ Ticket succesvol aangemaakt in {channel_mention_text}", ephemeral=True)

        # Publieke log naar WATCHER_LOG_CHANNEL
        await self.send_log_embed(
            title="🟢 Ticket aangemaakt",
            description=(
                f"ID: {ticket_id}\n"
                f"User: {user_display}\n"
                f"Timestamp: {created_at.isoformat()}\n"
                f"Kanaal: {channel_mention_text}\n"
                f"Omschrijving: {description}"
            ),
            level="success",
        )

    @app_commands.command(name="ticket_list", description="Toon alle open tickets (admins/mods)")
    async def ticket_list(self, interaction: discord.Interaction):
        # Permissie: enkel staff
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Je hebt geen toegang tot dit commando.", ephemeral=True)
            return
        if self.conn is None:
            await interaction.response.send_message("⛔ Database is niet verbonden.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        try:
            rows: List[asyncpg.Record] = await self.conn.fetch(
                """
                SELECT id, user_id, username, description, status, created_at, claimed_by, claimed_at
                FROM support_tickets
                WHERE status = 'open'
                ORDER BY created_at ASC
                LIMIT 25
                """
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ Fout bij ophalen tickets: {e}", ephemeral=True)
            return

        if not rows:
            await interaction.followup.send("✅ Geen open tickets.", ephemeral=True)
            return

        embed = discord.Embed(title="📋 Open tickets", color=discord.Color.blurple())
        for r in rows:
            claimed = f" (claimed by {r['claimed_by']})" if r.get('claimed_by') else ""
            embed.add_field(
                name=f"ID {r['id']} — {r['username']}",
                value=f"{(r['description'] or '-')[:140]}{claimed}",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ticket_claim", description="Claim een ticket (admins/mods)")
    @app_commands.describe(ticket_id="Het ID van het ticket om te claimen")
    async def ticket_claim(self, interaction: discord.Interaction, ticket_id: int):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Je hebt geen toegang tot dit commando.", ephemeral=True)
            return
        if self.conn is None:
            await interaction.response.send_message("⛔ Database is niet verbonden.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        # Zorg dat kolommen bestaan (backwards compat)
        try:
            await self.conn.execute("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS claimed_by BIGINT;")
            await self.conn.execute("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;")
        except Exception:
            pass

        staff_id = int(interaction.user.id)

        try:
            row = await self.conn.fetchrow(
                """
                UPDATE support_tickets
                SET claimed_by = $1, claimed_at = NOW()
                WHERE id = $2 AND (claimed_by IS NULL OR claimed_by = 0) AND status = 'open'
                RETURNING id, user_id, username, description, created_at
                """,
                staff_id,
                ticket_id,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Claim mislukt: {e}", ephemeral=True)
            return

        if not row:
            await interaction.followup.send("❌ Ticket niet gevonden of al geclaimd/gesloten.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Ticket `{ticket_id}` geclaimd door {interaction.user.mention}.", ephemeral=True)
        await self.send_log_embed(
            title="🟡 Ticket geclaimd",
            description=(
                f"ID: {ticket_id}\n"
                f"Claimed by: {interaction.user} ({interaction.user.id})\n"
                f"Timestamp: {datetime.utcnow().isoformat()}"
            ),
            level="info",
        )

    @app_commands.command(name="ticket_close", description="Sluit een ticket (admins/mods)")
    @app_commands.describe(ticket_id="Het ID van het ticket om te sluiten")
    async def ticket_close(self, interaction: discord.Interaction, ticket_id: int):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Je hebt geen toegang tot dit commando.", ephemeral=True)
            return
        if self.conn is None:
            await interaction.response.send_message("⛔ Database is niet verbonden.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        try:
            row = await self.conn.fetchrow(
                """
                UPDATE support_tickets
                SET status = 'closed'
                WHERE id = $1 AND status <> 'closed'
                RETURNING id, user_id, username, description
                """,
                ticket_id,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Sluiten mislukt: {e}", ephemeral=True)
            return

        if not row:
            await interaction.followup.send("❌ Ticket niet gevonden of al gesloten.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Ticket `{ticket_id}` gesloten.", ephemeral=True)
        await self.send_log_embed(
            title="🟢 Ticket gesloten",
            description=(
                f"ID: {ticket_id}\n"
                f"Closed by: {interaction.user} ({interaction.user.id})\n"
                f"Timestamp: {datetime.utcnow().isoformat()}"
            ),
            level="success",
        )

    # Placeholder voor toekomstige GPT-integratie
    async def handle_gpt_response(self, ticket_row: asyncpg.Record) -> None:
        return


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketBot(bot))


