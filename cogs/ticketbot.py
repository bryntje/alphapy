import discord
from discord.ext import commands
from discord import app_commands
import asyncpg
from datetime import datetime
from typing import Optional

try:
    import config_local as config
except ImportError:
    import config

from utils.logger import logger


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
            self.conn = await asyncpg.connect(config.DATABASE_URL)
            await self.conn.execute(
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
            # Indexen voor snellere queries later
            await self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_user_id ON support_tickets(user_id);"
            )
            await self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);"
            )
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
                await channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"⚠️ TicketBot: kon log embed niet versturen: {e}")

    @app_commands.command(name="ticket", description="Maak een supportticket aan")
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
            row = await self.conn.fetchrow(
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

        ticket_id = row["id"] if row else None
        created_at: datetime = row["created_at"] if row else datetime.utcnow()

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
        await interaction.followup.send(embed=confirm, ephemeral=True)

        # Publieke log naar WATCHER_LOG_CHANNEL
        await self.send_log_embed(
            title="🟢 Ticket aangemaakt",
            description=(
                f"ID: {ticket_id}\n"
                f"User: {user_display}\n"
                f"Timestamp: {created_at.isoformat()}\n"
                f"Omschrijving: {description}"
            ),
            level="success",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketBot(bot))


