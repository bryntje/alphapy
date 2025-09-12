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

    This Cog provides a minimal `/ticket` slash command that lets users
    create a support ticket. Tickets are stored in PostgreSQL in the
    `support_tickets` table. After creation, a confirmation embed is sent
    and a log is posted to `WATCHER_LOG_CHANNEL`.

    Prepared for future extensions like: claim, close, tagging, GPT support.
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

    @app_commands.command(name="ticket", description="Create a support ticket")
    @app_checks.cooldown(1, 30.0)  # simple user cooldown
    @app_commands.describe(description="Short description of your issue")
    async def ticket(self, interaction: discord.Interaction, description: str):
        """Slash command to create a new ticket.

        - Stores the ticket in `support_tickets`
        - Sends a confirmation embed with details
        - Logs to `WATCHER_LOG_CHANNEL`
        """
        await interaction.response.defer(ephemeral=True)

        # Zorg dat DB klaar is
        if self.conn is None:
            try:
                await self.setup_db()
            except Exception as e:
                logger.error(f"❌ TicketBot: DB connect error: {e}")
                await interaction.followup.send("❌ Database is not available. Please try again later.")
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
                title="🚨 Ticket creation failed",
                description=f"User: {user_display}\nError: {e}",
                level="error",
            )
            await interaction.followup.send("❌ Something went wrong creating your ticket.")
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

        # Confirmation embed to the user (ephemeral followup)
        confirm = discord.Embed(
            title="🎟️ Ticket created",
            description="Your ticket has been created successfully.",
            color=discord.Color.green(),
            timestamp=created_at,
        )
        confirm.add_field(name="Ticket ID", value=str(ticket_id), inline=True)
        confirm.add_field(name="User", value=f"{user.mention}", inline=True)
        confirm.add_field(name="Status", value="open", inline=True)
        confirm.add_field(name="Description", value=description[:1024] or "—", inline=False)

        # Create a dedicated channel under the given category with private overwrites
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

            # Initial message in the ticket channel
            ch_embed = discord.Embed(
                title="🎟️ Ticket created",
                color=discord.Color.green(),
                timestamp=created_at,
                description=(
                    f"Ticket ID: `{ticket_id}`\n"
                    f"User: {user.mention}\n"
                    f"Status: **open**\n\n"
                    f"Description:\n{description}"
                )
            )
            view = TicketActionView(
                bot=self.bot,
                conn=conn_safe2,
                ticket_id=ticket_id,
                support_role_id=support_role.id if support_role else None,
                timeout=None,
            )
            await channel.send(
                content=(support_role.mention if support_role else None),
                embed=ch_embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

            channel_mention_text = channel.mention
            confirm.add_field(name="Channel", value=channel_mention_text, inline=False)
        except Exception as e:
            logger.warning(f"⚠️ TicketBot: channel creation failed: {e}")
            confirm.add_field(name="Channel", value="(creation failed)", inline=False)

        await interaction.followup.send(embed=confirm, ephemeral=True)
        if channel_mention_text != "—":
            await interaction.followup.send(f"✅ Ticket created in {channel_mention_text}", ephemeral=True)

        # Public log to WATCHER_LOG_CHANNEL
        await self.send_log_embed(
            title="🟢 Ticket created",
            description=(
                f"ID: {ticket_id}\n"
                f"User: {user_display}\n"
                f"Timestamp: {created_at.isoformat()}\n"
                f"Channel: {channel_mention_text}\n"
                f"Description: {description}"
            ),
            level="success",
        )

    

class TicketActionView(discord.ui.View):
    def __init__(self, bot: commands.Bot, conn: asyncpg.Connection, ticket_id: int, support_role_id: Optional[int] = None, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.conn = conn
        self.ticket_id = ticket_id
        self.support_role_id = support_role_id

    async def _is_staff(self, interaction: discord.Interaction) -> bool:
        return await is_owner_or_admin_interaction(interaction)

    async def _log(self, interaction: discord.Interaction, title: str, desc: str, level: str = "info") -> None:
        # Use channel send via embed helper from a new simple instance-less call
        try:
            color_map = {"info": 0x3498db, "debug": 0x95a5a6, "error": 0xe74c3c, "success": 0x2ecc71, "warning": 0xf1c40f}
            color = color_map.get(level, 0x3498db)
            embed = discord.Embed(title=title, description=desc, color=color)
            embed.set_footer(text="ticketbot")
            channel = self.bot.get_channel(getattr(config, "WATCHER_LOG_CHANNEL", 0))
            if channel and hasattr(channel, "send"):
                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(embed=embed)
        except Exception:
            pass

    async def _post_summary_placeholder(self, channel: discord.TextChannel) -> None:
        """Post a summary placeholder message in English that we can later replace with GPT results.

        TODO: Inject GPT-generated summary here in a future version
        """
        try:
            summary_text = (
                "📄 **Ticket Summary (Placeholder)**  \n"
                "This space is reserved for the automated summary of this ticket.  \n"
                "In a future version, a GPT-based recap of this conversation will appear here."
            )
            await channel.send(summary_text)
        except Exception:
            # Non-fatal; summary can be posted later
            pass

    @discord.ui.button(label="🎟️ Claim ticket", style=discord.ButtonStyle.primary, custom_id="ticket_claim_btn")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Je hebt geen rechten om te claimen.", ephemeral=True)
            return
        try:
            row = await self.conn.fetchrow(
                """
                UPDATE support_tickets
                SET claimed_by = $1, claimed_at = NOW()
                WHERE id = $2 AND (claimed_by IS NULL OR claimed_by = 0) AND status = 'open'
                RETURNING id
                """,
                int(interaction.user.id),
                int(self.ticket_id),
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Claim failed: {e}", ephemeral=True)
            return

        if not row:
            await interaction.response.send_message("❌ Ticket not found or already claimed/closed.", ephemeral=True)
            return

        # Update UI: disable claim
        button.disabled = True
        button.label = "Claimed"
        await interaction.response.edit_message(view=self)

        await interaction.followup.send(f"✅ Ticket claimed by {interaction.user.mention} at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        await self._log(
            interaction,
            title="🟡 Ticket claimed",
            desc=(
                f"ID: {self.ticket_id}\n"
                f"Claimed by: {interaction.user} ({interaction.user.id})\n"
                f"Timestamp: {datetime.utcnow().isoformat()}"
            ),
            level="info",
        )

    @discord.ui.button(label="🔒 Sluit ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Je hebt geen rechten om te sluiten.", ephemeral=True)
            return

        try:
            row = await self.conn.fetchrow(
                """
                UPDATE support_tickets
                SET status = 'closed'
                WHERE id = $1 AND status <> 'closed'
                RETURNING id, user_id, channel_id
                """,
                int(self.ticket_id),
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Close failed: {e}", ephemeral=True)
            return

        if not row:
            await interaction.response.send_message("❌ Ticket not found or already closed.", ephemeral=True)
            return

        # Lock/rename channel
        try:
            ch = interaction.channel
            if isinstance(ch, discord.TextChannel):
                # Fetch ticket owner permissions
                owner_id = row.get("user_id")
                guild = ch.guild
                member = guild.get_member(int(owner_id)) if owner_id else None

                overwrites = ch.overwrites
                if member is not None:
                    overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
                overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                await ch.edit(overwrites=overwrites, reason=f"Ticket {self.ticket_id} closed")

                try:
                    await ch.edit(name=f"ticket-{self.ticket_id}-closed")
                except Exception:
                    pass

        except Exception as e:
            await interaction.followup.send(f"⚠️ Channel lock/rename failed: {e}")

        # Disable entire view
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)

        await interaction.followup.send(f"✅ Ticket closed by {interaction.user.mention} at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        await self._log(
            interaction,
            title="🟢 Ticket closed",
            desc=(
                f"ID: {self.ticket_id}\n"
                f"Closed by: {interaction.user} ({interaction.user.id})\n"
                f"Timestamp: {datetime.utcnow().isoformat()}"
            ),
            level="success",
        )
        # Post summary placeholder last to satisfy required execution order
        if isinstance(interaction.channel, discord.TextChannel):
            await self._post_summary_placeholder(interaction.channel)
    # (end of TicketActionView)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketBot(bot))


