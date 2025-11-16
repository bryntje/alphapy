import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import checks as app_checks
import asyncpg
import json
from datetime import datetime, timedelta
import re
from typing import Optional, List, Dict, cast
from utils.settings_service import SettingsService

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.logger import logger, log_with_guild, log_guild_action, log_database_event
from gpt.helpers import ask_gpt
from utils.checks_interaction import is_owner_or_admin_interaction
from utils.timezone import BRUSSELS_TZ
from version import __version__, CODENAME


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
        settings = getattr(bot, "settings", None)
        if settings is None or not hasattr(settings, 'get'):
            raise RuntimeError("SettingsService not available on bot instance")
        self.settings = settings  # type: ignore
        # Start async setup zonder de event loop te blokkeren
        self.bot.loop.create_task(self.setup_db())
        # Register persistent view so the ticket button keeps working after restarts
        try:
            self.bot.add_view(TicketOpenView(self, timeout=None))
        except Exception as e:
            logger.warning(f"⚠️ TicketBot: kon TicketOpenView niet registreren: {e}")

    async def setup_db(self) -> None:
        """Initialiseer database connectie en zorg dat de tabel bestaat."""
        try:
            conn = await asyncpg.connect(config.DATABASE_URL)
            log_database_event("DB_CONNECTED", details="TicketBot database connection established")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    guild_ticket_id INT NOT NULL,
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

            # Guild-local ticket ID voor per-guild nummering
            try:
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS guild_ticket_id INT;"
                )
                # Vul bestaande records met hun globale ID als fallback
                await conn.execute(
                    "UPDATE support_tickets SET guild_ticket_id = id WHERE guild_ticket_id IS NULL;"
                )
                # Maak index voor performance
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_support_tickets_guild_ticket_id ON support_tickets(guild_id, guild_ticket_id);"
                )
            except Exception as e:
                logger.warning(f"⚠️ TicketBot: kon kolom guild_ticket_id niet toevoegen: {e}")
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
            # Status workflow columns (M2)
            try:
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();"
                )
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS escalated_to BIGINT;"
                )
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;"
                )
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS archived_by BIGINT;"
                )
            except Exception:
                pass
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_updated_at ON support_tickets(updated_at);"
            )
            # Handige index voor claims
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_claimed_by ON support_tickets(claimed_by);"
            )
            # Summaries table for FAQ detection
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_summaries (
                  id SERIAL PRIMARY KEY,
                  ticket_id INT NOT NULL,
                  summary TEXT NOT NULL,
                  similarity_key TEXT,
                  created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ticket_summaries_key ON ticket_summaries(similarity_key);"
            )
            # FAQ entries table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faq_entries (
                  id SERIAL PRIMARY KEY,
                  similarity_key TEXT,
                  summary TEXT NOT NULL,
                  created_by BIGINT,
                  created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            # Metrics snapshots (optional)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_metrics (
                  id BIGSERIAL PRIMARY KEY,
                  snapshot JSONB NOT NULL,
                  created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            # Evolve metrics to structured columns
            try:
                await conn.execute("ALTER TABLE ticket_metrics ADD COLUMN IF NOT EXISTS scope TEXT;")
                await conn.execute("ALTER TABLE ticket_metrics ADD COLUMN IF NOT EXISTS counts JSONB;")
                await conn.execute("ALTER TABLE ticket_metrics ADD COLUMN IF NOT EXISTS average_cycle_time BIGINT;")
                await conn.execute("ALTER TABLE ticket_metrics ADD COLUMN IF NOT EXISTS triggered_by BIGINT;")
                await conn.execute("ALTER TABLE ticket_metrics ADD COLUMN IF NOT EXISTS topics JSONB;")
            except Exception:
                pass
            self.conn = conn
            logger.info("✅ TicketBot: DB ready (support_tickets)")
            log_database_event("DB_READY", details="TicketBot database fully initialized")
        except Exception as e:
            log_database_event("DB_INIT_ERROR", details=f"TicketBot setup failed: {e}")
            logger.error(f"❌ TicketBot: DB init error: {e}")

    async def send_log_embed(self, title: str, description: str, level: str = "info", guild_id: int = 0) -> None:
        """Send log embed to the correct guild's log channel"""
        if guild_id == 0:
            # Fallback for legacy calls without guild_id
            logger.warning("⚠️ TicketBot send_log_embed called without guild_id - skipping Discord log")
            return

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
            embed.set_footer(text=f"ticketbot | Guild: {guild_id}")

            channel_id = self._get_log_channel_id(guild_id)
            if channel_id == 0:
                # No log channel configured for this guild
                log_with_guild(f"No log channel configured for ticketbot logging", guild_id, "debug")
                return

            channel = self.bot.get_channel(channel_id)
            if channel and hasattr(channel, "send"):
                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(embed=embed)
                log_guild_action(guild_id, "LOG_SENT", details=f"ticketbot: {title}")
            else:
                log_with_guild(f"Log channel {channel_id} not found or not accessible", guild_id, "warning")

        except Exception as e:
            log_with_guild(f"Kon ticketbot log embed niet versturen: {e}", guild_id, "error")

    @app_commands.command(name="ticket", description="Create a support ticket")
    @app_checks.cooldown(1, 30.0)  # simple user cooldown
    @app_commands.describe(description="Short description of your issue")
    async def ticket(self, interaction: discord.Interaction, description: str):
        """Slash command to create a new ticket.

        - Stores the ticket in `support_tickets`
        - Sends a confirmation embed with details
        - Logs to `WATCHER_LOG_CHANNEL`
        """
        if not interaction.guild:
            await interaction.response.send_message("❌ Deze command werkt alleen in een server.", ephemeral=True)
            return
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
            # Bereken de volgende guild_ticket_id voor deze guild
            max_guild_ticket = await conn_safe.fetchval(
                "SELECT COALESCE(MAX(guild_ticket_id), 0) FROM support_tickets WHERE guild_id = $1",
                interaction.guild.id
            )
            next_guild_ticket_id = max_guild_ticket + 1

            row = await conn_safe.fetchrow(
                """
                INSERT INTO support_tickets (guild_id, guild_ticket_id, user_id, username, description)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, guild_ticket_id, created_at
                """,
                interaction.guild.id,
                next_guild_ticket_id,
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
                guild_id=interaction.guild.id,
            )
            await interaction.followup.send("❌ Something went wrong creating your ticket.")
            return

        ticket_id: int  # globale ID voor database operaties
        guild_ticket_id: int  # lokale ID voor display
        created_at: datetime
        if row:
            ticket_id = int(row["id"])  # not None after successful insert
            guild_ticket_id = int(row["guild_ticket_id"])
            created_at = row["created_at"]
        else:
            # Fallback: should not happen, but keep types safe
            ticket_id = 0
            guild_ticket_id = 0
            created_at = datetime.utcnow()

        # Confirmation embed to the user (ephemeral followup)
        confirm = discord.Embed(
            title="🎟️ Ticket created",
            description="Your ticket has been created successfully.",
            color=discord.Color.green(),
            timestamp=created_at,
        )
        confirm.add_field(name="Ticket ID", value=str(guild_ticket_id), inline=True)
        confirm.add_field(name="User", value=f"{user.mention}", inline=True)
        confirm.add_field(name="Status", value="open", inline=True)
        confirm.add_field(name="Description", value=description[:1024] or "—", inline=False)

        # Create a dedicated channel under the given category with private overwrites
        channel_mention_text = "—"
        try:
            guild = interaction.guild
            if guild is None:
                raise RuntimeError("Guild context ontbreekt")

            category_id = self._get_ticket_category_id(guild.id)
            if not category_id:
                raise RuntimeError("Ticket categorie niet ingesteld")
            fetched_channel = guild.get_channel(category_id) or await self.bot.fetch_channel(category_id)
            if not isinstance(fetched_channel, discord.CategoryChannel):
                raise RuntimeError("Category kanaal niet gevonden of geen category type")
            category = fetched_channel

            support_role = self._resolve_support_role(guild)

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
                name=f"ticket-{guild_ticket_id}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket {guild_ticket_id} aangemaakt door {user}"
            )

            # Update DB met channel_id
            try:
                conn_safe2 = cast(asyncpg.Connection, self.conn)
                await conn_safe2.execute(
                    "UPDATE support_tickets SET channel_id = $1, updated_at = NOW() WHERE id = $2 AND guild_id = $3",
                    int(channel.id),
                    ticket_id,
                    interaction.guild.id,
                )
            except Exception as e:
                logger.warning(f"⚠️ TicketBot: kon channel_id niet opslaan: {e}")

            # Initial message in the ticket channel
            ch_embed = discord.Embed(
                title="🎟️ Ticket created",
                color=discord.Color.green(),
                timestamp=created_at,
                description=(
                    f"Ticket ID: `{guild_ticket_id}`\n"
                    f"User: {user.mention}\n"
                    f"Status: **open**\n\n"
                    f"Description:\n{description}"
                )
            )
            view = TicketActionView(
                bot=self.bot,
                conn=conn_safe2,
                ticket_id=ticket_id,  # globale ID voor database
                support_role_id=support_role.id if support_role else None,
                cog=self,
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
                f"ID: {guild_ticket_id}\n"
                f"User: {user_display}\n"
                f"Timestamp: {created_at.isoformat()}\n"
                f"Channel: {channel_mention_text}\n"
                f"Description: {description}"
            ),
            level="success",
            guild_id=interaction.guild.id,
        )

    @app_commands.command(name="ticket_panel_post", description="Post a ticket panel with a Create ticket button")
    async def ticket_panel_post(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        target = channel or cast(discord.TextChannel, interaction.channel)
        if target is None:
            await interaction.response.send_message("❌ No channel specified.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Support Tickets",
            description="To create a ticket, click the button below.",
            color=discord.Color.blurple(),
        )
        view = TicketOpenView(self, timeout=None)
        await target.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Ticket panel posted.", ephemeral=True)

    async def create_ticket_for_user(self, interaction: discord.Interaction, description: str) -> None:
        # Ensure DB
        if self.conn is None:
            try:
                await self.setup_db()
            except Exception as e:
                logger.error(f"❌ TicketBot: DB connect error: {e}")
                await interaction.followup.send("❌ Database is not available. Please try again later.")
                return
        # Reuse existing flow by calling the command internals
        user = interaction.user
        user_display = f"{user} ({user.id})"
        try:
            conn_safe = cast(asyncpg.Connection, self.conn)
            # Bereken de volgende guild_ticket_id voor deze guild
            max_guild_ticket = await conn_safe.fetchval(
                "SELECT COALESCE(MAX(guild_ticket_id), 0) FROM support_tickets WHERE guild_id = $1",
                interaction.guild.id
            )
            next_guild_ticket_id = max_guild_ticket + 1

            row = await conn_safe.fetchrow(
                """
                INSERT INTO support_tickets (guild_id, guild_ticket_id, user_id, username, description)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, guild_ticket_id, created_at
                """,
                interaction.guild.id,
                next_guild_ticket_id,
                int(user.id),
                str(user),
                (description or "").strip() or "—",
            )
        except Exception as e:
            logger.exception("🚨 TicketBot: insert failed")
            await self.send_log_embed(
                title="🚨 Ticket creation failed",
                description=f"User: {user_display}\nError: {e}",
                level="error",
                guild_id=interaction.guild.id,
            )
            await interaction.followup.send("❌ Something went wrong creating your ticket.")
            return
        ticket_id = int(row["id"]) if row else 0  # globale ID
        guild_ticket_id = int(row["guild_ticket_id"]) if row else 0  # lokale ID voor display
        created_at: datetime = row["created_at"] if row else datetime.utcnow()
        # Build channel and send initial message — duplicate logic kept for clarity
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Guild context missing.")
            return
        category_id = self._get_ticket_category_id(guild.id)
        if not category_id:
            await interaction.followup.send("❌ Ticket category not configured.")
            return
        fetched = guild.get_channel(category_id) or await self.bot.fetch_channel(category_id)
        if not isinstance(fetched, discord.CategoryChannel):
            await interaction.followup.send("❌ Ticket category not found.")
            return
        category = fetched
        support_role = self._resolve_support_role(guild)
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
            name=f"ticket-{guild_ticket_id}",
            category=category,
            overwrites=overwrites,
            reason=f"Ticket {guild_ticket_id} created by {user}"
        )
        # Store channel id
        try:
            conn_safe2 = cast(asyncpg.Connection, self.conn)
            await conn_safe2.execute(
                "UPDATE support_tickets SET channel_id = $1, updated_at = NOW() WHERE id = $2 AND guild_id = $3",
                int(channel.id), ticket_id, interaction.guild.id
            )
        except Exception:
            pass
        ch_embed = discord.Embed(
            title="🎟️ Ticket created",
            color=discord.Color.green(),
            timestamp=created_at,
            description=(
                f"Ticket ID: `{guild_ticket_id}`\n"
                f"User: {user.mention}\n"
                f"Status: **open**\n\n"
                f"Description:\n{description or '—'}"
            )
        )
        view = TicketActionView(
            bot=self.bot,
            conn=conn_safe2,
            ticket_id=ticket_id,
            support_role_id=support_role.id if support_role else None,
            cog=self,
            timeout=None,
        )
        await channel.send(
            content=(support_role.mention if support_role else None),
            embed=ch_embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )
        await interaction.followup.send(f"✅ Ticket created in {channel.mention}", ephemeral=True)

    def _human_duration(self, seconds: int) -> str:
        mins, sec = divmod(seconds, 60)
        hrs, mins = divmod(mins, 60)
        days, hrs = divmod(hrs, 24)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hrs or days:
            parts.append(f"{hrs}h")
        parts.append(f"{mins}m")
        return " ".join(parts)

    async def _compute_stats(self, scope: str, guild_id: Optional[int] = None) -> tuple[dict, Optional[int]]:
        # scope: 'all' | '7d' | '30d'
        if not self.conn:
            return {}, None
        where_parts = []
        if guild_id is not None:
            where_parts.append(f"guild_id = {guild_id}")
        if scope == "7d":
            where_parts.append("created_at >= NOW() - INTERVAL '7 days'")
        elif scope == "30d":
            where_parts.append("created_at >= NOW() - INTERVAL '30 days'")
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        counts = await self.conn.fetch(f"SELECT status, COUNT(*) c FROM support_tickets {where} GROUP BY status")
        status_to_count = {r["status"] or "-": int(r["c"]) for r in counts}
        # average cycle (closed only)
        avg_where_parts = where_parts + ["status='closed'"] if where_parts else ["status='closed'"]
        avg_where = "WHERE " + " AND ".join(avg_where_parts) if avg_where_parts else ""
        avg_row = await self.conn.fetchrow(
            f"SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) AS avg_s FROM support_tickets {avg_where}"
        )
        avg_seconds: Optional[int] = None
        if avg_row and avg_row["avg_s"] is not None:
            try:
                avg_seconds = int(float(avg_row["avg_s"]))
            except Exception:
                avg_seconds = None
        return status_to_count, avg_seconds

    async def _top_topics(self, limit: int = 5) -> Dict[str, int]:
        if not self.conn:
            return {}
        rows = await self.conn.fetch(
            """
            SELECT similarity_key, COUNT(*) AS cnt
            FROM ticket_summaries
            WHERE similarity_key IS NOT NULL AND similarity_key <> ''
              AND created_at >= NOW() - INTERVAL '30 days'
            GROUP BY similarity_key
            ORDER BY cnt DESC, similarity_key
            LIMIT $1
            """,
            int(limit),
        )
        topics: Dict[str, int] = {}
        for row in rows:
            key = row.get("similarity_key") or "-"
            topics[key] = int(row.get("cnt") or 0)
        return topics

    def _settings_get(self, scope: str, key: str, guild_id: int, fallback: Optional[int] = None):
        if self.settings:
            try:
                return self.settings.get(scope, key, guild_id)
            except KeyError:
                pass
        return fallback

    def _normalize_id(self, value: Optional[object]) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _get_log_channel_id(self, guild_id: int) -> int:
        value = self._settings_get("system", "log_channel_id", guild_id, 0)  # Moet geconfigureerd worden via /config system set_log_channel
        return int(value) if value is not None else 0

    def _get_ticket_category_id(self, guild_id: int) -> Optional[int]:
        value = self._settings_get(
            "ticketbot",
            "category_id",
            guild_id,
            getattr(config, "TICKET_CATEGORY_ID", 1416148921960628275),
        )
        return self._normalize_id(value)

    def _get_support_role_id(self, guild_id: int) -> Optional[int]:
        value = self._settings_get("ticketbot", "staff_role_id", guild_id, getattr(config, "TICKET_ACCESS_ROLE_ID", None))
        normalized = self._normalize_id(value)
        if normalized is not None:
            return normalized
        admin_candidate = getattr(config, "ADMIN_ROLE_ID", None)
        if isinstance(admin_candidate, int):
            return admin_candidate
        if isinstance(admin_candidate, (list, tuple, set)) and admin_candidate:
            for candidate in admin_candidate:
                normalized = self._normalize_id(candidate)
                if normalized is not None:
                    return normalized
        return None

    def _resolve_support_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        role_id = self._get_support_role_id(guild.id)
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                return role
        return None

    def _get_escalation_role_id(self, guild_id: int) -> Optional[int]:
        value = self._settings_get(
            "ticketbot",
            "escalation_role_id",
            getattr(config, "TICKET_ESCALATION_ROLE_ID", None),
        )
        return self._normalize_id(value)

    async def capture_metrics_snapshot(
        self,
        *,
        triggered_by: int,
        scope: str,
        ticket_id: Optional[int] = None,
        topic: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        if not self.conn:
            return

        counts, avg_seconds = await self._compute_stats("all", None)
        snapshot: Dict[str, object] = {
            "counts": counts,
            "avg": avg_seconds,
            "scope": scope,
        }
        if ticket_id is not None:
            snapshot["ticket_id"] = ticket_id
        if topic:
            snapshot["topic"] = topic
        if summary:
            snapshot["summary_preview"] = summary[:280]

        topics_payload: Optional[Dict[str, object]] = None
        latest_topic: Dict[str, object] = {}
        if topic:
            latest_topic = {
                "key": topic,
                "ticket_id": ticket_id,
            }
            if summary:
                latest_topic["summary"] = summary[:280]

        top_topics = await self._top_topics()
        if latest_topic or top_topics:
            topics_payload = {}
            if latest_topic:
                topics_payload["latest"] = latest_topic
            if top_topics:
                topics_payload["top30d"] = top_topics

        snapshot_json = json.dumps(snapshot)
        counts_json = json.dumps(counts)
        topics_json = json.dumps(topics_payload) if topics_payload is not None else None

        await self.conn.execute(
            """
            INSERT INTO ticket_metrics (snapshot, scope, counts, average_cycle_time, triggered_by, topics)
            VALUES ($1::jsonb, $2, $3::jsonb, $4, $5, CASE WHEN $6 IS NULL THEN NULL ELSE $6::jsonb END)
            """,
            snapshot_json,
            scope,
            counts_json,
            avg_seconds,
            int(triggered_by),
            topics_json,
        )

        try:
            await self.send_log_embed(
                title="📊 Ticket metrics snapshot",
                description=(
                    f"scope: `{scope}`\n"
                    f"triggered_by: {triggered_by}\n"
                    f"ticket_id: {ticket_id or '-'}\n"
                    f"topic: {topic or '-'}"
                ),
                level="info",
                guild_id=0,  # Global metrics, no specific guild
            )
        except Exception:
            pass

    def _stats_embed(self, counts: dict, avg_seconds: Optional[int]) -> discord.Embed:
        embed = discord.Embed(title="📊 Ticket Statistics", color=0x5865F2)
        for s in ["open", "claimed", "waiting_for_user", "escalated", "closed", "archived"]:
            embed.add_field(name=s, value=str(counts.get(s, 0)), inline=True)
        if avg_seconds is not None:
            embed.add_field(name="Average cycle time (closed)", value=self._human_duration(avg_seconds), inline=False)
        else:
            embed.add_field(name="Average cycle time (closed)", value="-", inline=False)
        now_bxl = datetime.now(BRUSSELS_TZ)
        embed.set_footer(
            text=f"Innersync • Alphapy v{__version__} — {CODENAME} | Last updated: {now_bxl.strftime('%Y-%m-%d %H:%M')} BXL"
        )
        return embed

    class StatsView(discord.ui.View):
        def __init__(self, cog: "TicketBot", public: bool, scope: str):
            super().__init__(timeout=180)
            self.cog = cog
            self.public = public
            self.scope = scope  # 'all' | '7d' | '30d'

        async def _update(self, interaction: discord.Interaction, scope: Optional[str] = None):
            if scope:
                self.scope = scope
            if not await is_owner_or_admin_interaction(interaction):
                await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
                return
            counts, avg_seconds = await self.cog._compute_stats(self.scope, interaction.guild.id)
            embed = self.cog._stats_embed(counts, avg_seconds)
            await interaction.response.edit_message(embed=embed, view=self)
            try:
                await self.cog.send_log_embed(
                    title="📊 Ticket stats (button)",
                    description=f"by={interaction.user.id} • scope={self.scope} • counts={counts}",
                    level="info",
                    guild_id=interaction.guild.id,
                )
                if self.cog.conn:
                    await self.cog.conn.execute(
                        "INSERT INTO ticket_metrics (snapshot, scope, counts, average_cycle_time, triggered_by) VALUES ($1::jsonb,$2,$3::jsonb,$4,$5)",
                        json.dumps({"counts": counts, "avg": avg_seconds, "scope": self.scope}),
                        self.scope,
                        json.dumps(counts),
                        avg_seconds,
                        int(interaction.user.id)
                    )
            except Exception:
                pass

        @discord.ui.button(label="Last 7d", style=discord.ButtonStyle.secondary, custom_id="stats_7d")
        async def last7(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._update(interaction, "7d")

        @discord.ui.button(label="Last 30d", style=discord.ButtonStyle.secondary, custom_id="stats_30d")
        async def last30(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._update(interaction, "30d")

        @discord.ui.button(label="All time", style=discord.ButtonStyle.secondary, custom_id="stats_all")
        async def alltime(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._update(interaction, "all")

        @discord.ui.button(label="Refresh 🔄", style=discord.ButtonStyle.primary, custom_id="stats_refresh")
        async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._update(interaction, None)

    @app_commands.command(name="ticket_stats", description="Show ticket statistics (admin)")
    @app_commands.describe(public="Post in channel instead of ephemeral (default: false)")
    async def ticket_stats(self, interaction: discord.Interaction, public: bool = False):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=not public)

        if not self.conn:
            await interaction.followup.send("❌ Database not connected.", ephemeral=not public)
            return
        counts, avg_seconds = await self._compute_stats("all", None)
        embed = self._stats_embed(counts, avg_seconds)
        view = TicketBot.StatsView(self, public=public, scope="all")
        await interaction.followup.send(embed=embed, view=view, ephemeral=not public)
        await self.send_log_embed(
            title="📊 Ticket stats",
            description=f"by={interaction.user.id} • scope=all • public={public} • counts={counts}",
            level="info",
            guild_id=0,  # Global stats across all guilds
        )
        try:
            await self.conn.execute(
                "INSERT INTO ticket_metrics (snapshot, scope, counts, average_cycle_time, triggered_by) VALUES ($1::jsonb,$2,$3::jsonb,$4,$5)",
                json.dumps({"counts": counts, "avg": avg_seconds, "scope": "all"}),
                "all",
                json.dumps(counts),
                avg_seconds,
                int(interaction.user.id)
            )
        except Exception:
            pass

    @app_commands.command(name="ticket_status", description="Update a ticket status (admin)")
    @app_commands.describe(
        id="Ticket ID",
        escalate_to="Optional escalation role when setting status to escalated"
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="open", value="open"),
            app_commands.Choice(name="claimed", value="claimed"),
            app_commands.Choice(name="waiting_for_user", value="waiting_for_user"),
            app_commands.Choice(name="escalated", value="escalated"),
            app_commands.Choice(name="closed", value="closed"),
            app_commands.Choice(name="archived", value="archived"),
        ]
    )
    async def ticket_status(
        self,
        interaction: discord.Interaction,
        id: int,
        status: app_commands.Choice[str],
        escalate_to: Optional[discord.Role] = None,
    ):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        if not self.conn:
            await interaction.followup.send("❌ Database not connected.", ephemeral=True)
            return

        new_status = status.value
        try:
            if new_status == "escalated":
                await self.conn.execute(
                    "UPDATE support_tickets SET status=$1, escalated_to=$2, updated_at=NOW() WHERE id=$3 AND guild_id=$4",
                    new_status,
                    int(escalate_to.id) if escalate_to else None,
                    id,
                    interaction.guild.id,
                )
            elif new_status == "claimed":
                await self.conn.execute(
                    "UPDATE support_tickets SET status=$1, updated_at=NOW(), claimed_by=COALESCE(claimed_by,$2), claimed_at=COALESCE(claimed_at,NOW()) WHERE id=$3 AND guild_id=$4",
                    new_status,
                    int(interaction.user.id),
                    id,
                    interaction.guild.id,
                )
            elif new_status == "archived":
                await self.conn.execute(
                    "UPDATE support_tickets SET status=$1, archived_at=NOW(), archived_by=$2, updated_at=NOW() WHERE id=$3 AND guild_id=$4",
                    new_status,
                    int(interaction.user.id),
                    id,
                    interaction.guild.id,
                )
            else:
                await self.conn.execute(
                    "UPDATE support_tickets SET status=$1, updated_at=NOW() WHERE id=$2 AND guild_id=$3",
                    new_status,
                    id,
                    interaction.guild.id,
                )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to update status: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Ticket `{id}` status set to **{new_status}**.", ephemeral=True)
        # Log
        try:
            await self.send_log_embed(
                title="🧭 Ticket status update",
                description=(
                    f"ID: {id}\n"
                    f"New status: **{new_status}**\n"
                    f"By: {interaction.user} ({interaction.user.id})"
                    + (f"\nEscalated to: <@&{escalate_to.id}>" if (new_status == 'escalated' and escalate_to) else "")
                ),
                level="info",
                guild_id=interaction.guild.id,
            )
        except Exception:
            pass


class TicketActionView(discord.ui.View):
    def __init__(self, bot: commands.Bot, conn: asyncpg.Connection, ticket_id: int, support_role_id: Optional[int] = None, cog: Optional["TicketBot"] = None, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.conn = conn
        self.ticket_id = ticket_id
        self.support_role_id = support_role_id
        self.cog = cog

    async def _is_staff(self, interaction: discord.Interaction) -> bool:
        return await is_owner_or_admin_interaction(interaction)

    async def _log(self, interaction: discord.Interaction, title: str, desc: str, level: str = "info") -> None:
        # Use channel send via embed helper from a new simple instance-less call
        try:
            if self.cog:
                await self.cog.send_log_embed(title=title, description=desc, level=level, guild_id=interaction.guild.id)
                return
            color_map = {"info": 0x3498db, "debug": 0x95a5a6, "error": 0xe74c3c, "success": 0x2ecc71, "warning": 0xf1c40f}
            color = color_map.get(level, 0x3498db)
            embed = discord.Embed(title=title, description=desc, color=color)
            embed.set_footer(text="ticketbot")
            channel = self.bot.get_channel(0)  # Moet geconfigureerd worden via /config system set_log_channel
            if channel and hasattr(channel, "send"):
                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(embed=embed)
        except Exception:
            pass

    async def _post_summary(self, channel: discord.TextChannel) -> Optional[Dict[str, str]]:
        """Generate, post and persist a GPT-based summary for this ticket.

        Returns a dict with `summary` and `key` when successful so callers can
        reuse the detected topic for metrics, or ``None`` if no summary was
        generated.
        """
        messages: List[str] = []
        try:
            async for msg in channel.history(limit=100, oldest_first=True):
                if not msg.author.bot:
                    content = (msg.content or "").strip()
                    if content:
                        messages.append(f"{msg.author.display_name}: {content}")

            if not messages:
                await channel.send("No content to summarize.")
                return None

            prompt = (
                "You are a helpful assistant. Summarize the following Discord ticket conversation in clear and concise English.\n\n"
                + "\n".join(messages[-50:])
            )

            try:
                # Use default model from ask_gpt (defaults to gpt-3.5-turbo)
                summary_text = await ask_gpt(
                    messages=[{"role": "user", "content": prompt}],
                    user_id=None,
                )
            except Exception as e:
                await channel.send(f"❌ Failed to generate summary: {e}")
                return None

            embed = discord.Embed(
                title="📄 Ticket Summary",
                description=(summary_text or "").strip() or "(empty)",
                color=discord.Color.green(),
            )
            await channel.send(embed=embed)
            # Register the summary for clustering/FAQ suggestions
            key = await self._register_summary(self.ticket_id, (summary_text or "").strip())
            cleaned = (summary_text or "").strip()
            if key:
                return {"summary": cleaned, "key": key}
            return {"summary": cleaned} if cleaned else None
        except Exception:
            # Non-fatal; do not block the close flow on summary issues
            return None

    def _compute_similarity_key(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        tokens = [t for t in normalized.split() if len(t) >= 4 and t not in {
            "this","that","with","from","have","about","which","their","there","would","could","should",
            "subject","ticket","issue","user","message","chat","channel","please","thank","thanks"
        }]
        # Use top unique tokens alphabetically as a simple key
        unique_tokens = sorted(set(tokens))[:12]
        key = "-".join(unique_tokens)
        return key[:256]

    async def _register_summary(self, ticket_id: int, summary: str) -> Optional[str]:
        try:
            key = self._compute_similarity_key(summary)
            since = datetime.utcnow() - timedelta(days=7)
            # Insert summary
            await self.conn.execute(
                "INSERT INTO ticket_summaries (ticket_id, summary, similarity_key) VALUES ($1, $2, $3)",
                int(ticket_id), summary, key
            )
            # Check recent similar summaries
            rows = await self.conn.fetch(
                """
                SELECT id FROM ticket_summaries
                WHERE similarity_key = $1 AND created_at >= $2
                ORDER BY created_at DESC
                LIMIT 30
                """,
                key, since
            )
            if len(rows) >= 3:
                # Propose FAQ to admins via log channel with a button
                try:
                    embed = discord.Embed(
                        title="💡 Repeated Ticket Pattern Detected",
                        description=(
                            "We detected multiple tickets with a similar topic in the last 7 days.\n\n"
                            f"Similarity key: `{key}`\n"
                            f"Occurrences: **{len(rows)}**\n\n"
                            "Consider adding an FAQ entry for this topic."
                        ),
                        color=discord.Color.gold(),
                    )
                    # Show a sample of the latest summary in the footer to aid admins
                    sample_preview = (summary[:180] + "…") if len(summary) > 180 else summary
                    embed.set_footer(text=f"Sample: {sample_preview}")
                    # Lightweight view with a placeholder button
                    view = discord.ui.View()

                    async def add_faq_callback(interaction: discord.Interaction):
                        if not await is_owner_or_admin_interaction(interaction):
                            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
                            return
                        try:
                            # Insert FAQ entry
                            await self.conn.execute(
                                "INSERT INTO faq_entries (similarity_key, summary, created_by) VALUES ($1, $2, $3)",
                                key, summary, int(interaction.user.id)
                            )
                            await interaction.response.send_message("✅ FAQ entry added.", ephemeral=True)
                            await self._log(
                                interaction,
                                title="✅ FAQ entry created",
                                desc=(
                                    f"Key: `{key}`\n"
                                    f"By: {interaction.user} ({interaction.user.id})\n"
                                    f"Snippet: {sample_preview}"
                                ),
                                level="success",
                            )
                        except Exception as e:
                            await interaction.response.send_message(f"❌ Failed to add FAQ: {e}", ephemeral=True)

                    btn = discord.ui.Button(label="Add to FAQ", style=discord.ButtonStyle.success)
                    btn.callback = add_faq_callback  # type: ignore
                    view.add_item(btn)

                    channel_id = None
                    if self.cog and interaction.guild:
                        channel_id = self.cog._get_log_channel_id(interaction.guild.id)
                    if channel_id is None:
                        channel_id = 0  # Moet geconfigureerd worden via /config system set_log_channel
                    channel = self.bot.get_channel(channel_id)
                    if channel and hasattr(channel, "send"):
                        text_channel = cast(discord.TextChannel, channel)
                        await text_channel.send(embed=embed, view=view)
                except Exception:
                    pass
            return key
        except Exception:
            # Do not block on summary registration failures
            return None

    @discord.ui.button(label="🎟️ Claim ticket", style=discord.ButtonStyle.primary, custom_id="ticket_claim_btn")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Je hebt geen rechten om te claimen.", ephemeral=True)
            return
        try:
            row = await self.conn.fetchrow(
                """
                UPDATE support_tickets
                SET claimed_by = $1, claimed_at = NOW(), updated_at = NOW()
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

    @discord.ui.button(label="🔒 Close ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Je hebt geen rechten om te sluiten.", ephemeral=True)
            return

        try:
            row = await self.conn.fetchrow(
                """
                UPDATE support_tickets
                SET status = 'closed', updated_at = NOW()
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

        # Disable claim/close, enable delete (admin-only enforcement in handler)
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id in {"ticket_claim_btn", "ticket_close_btn"}:
                child.disabled = True
            if isinstance(child, discord.ui.Button) and child.custom_id == "ticket_archive_btn":
                child.disabled = False
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
        # Post GPT summary last to satisfy required execution order
        summary_meta: Optional[Dict[str, str]] = None
        if isinstance(interaction.channel, discord.TextChannel):
            summary_meta = await self._post_summary(interaction.channel)

        # Automatically capture a metrics snapshot (counts, cycle time, topics)
        if self.cog and hasattr(self.cog, "capture_metrics_snapshot"):
            try:
                await self.cog.capture_metrics_snapshot(
                    triggered_by=int(interaction.user.id),
                    scope="auto-close",
                    ticket_id=int(self.ticket_id),
                    topic=summary_meta.get("key") if summary_meta else None,
                    summary=summary_meta.get("summary") if summary_meta else None,
                )
            except Exception as e:
                await self._log(
                    interaction,
                    title="⚠️ Metrics snapshot failed",
                    desc=f"id={self.ticket_id} • error={e}",
                    level="warning",
                )

    @discord.ui.button(label="⏳ Wait for user", style=discord.ButtonStyle.secondary, custom_id="ticket_wait_btn")
    async def wait_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await self.conn.execute(
            "UPDATE support_tickets SET status='waiting_for_user', updated_at = NOW() WHERE id = $1",
            int(self.ticket_id),
        )
        await interaction.response.send_message("✅ Status set to waiting_for_user.", ephemeral=True)
        await self._log(interaction, "🕒 Ticket status", f"id={self.ticket_id} → waiting_for_user")

    @discord.ui.button(label="🚩 Escalate", style=discord.ButtonStyle.secondary, custom_id="ticket_escalate_btn")
    async def escalate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        escalated_to = None
        if self.cog:
            escalated_to = self.cog._get_escalation_role_id(guild.id)
        if escalated_to is None:
            target_role_id = getattr(config, "TICKET_ESCALATION_ROLE_ID", None)
            escalated_to = int(target_role_id) if isinstance(target_role_id, int) else None
        await self.conn.execute(
            "UPDATE support_tickets SET status='escalated', escalated_to=$1, updated_at = NOW() WHERE id = $2",
            escalated_to,
            int(self.ticket_id),
        )
        await interaction.response.send_message("✅ Ticket escalated.", ephemeral=True)
        await self._log(interaction, "🚩 Ticket escalated", f"id={self.ticket_id} • to={escalated_to or '-'}")

    @discord.ui.button(label="🗄 Archive ticket", style=discord.ButtonStyle.secondary, custom_id="ticket_archive_btn", disabled=True)
    async def archive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Admin-only
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        try:
            await self.conn.execute(
                """
                UPDATE support_tickets
                SET status = 'archived', archived_at = NOW(), archived_by = $1, updated_at = NOW()
                WHERE id = $2
                """,
                int(interaction.user.id),
                int(self.ticket_id),
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Archiving failed: {e}", ephemeral=True)
            return

        # Delete the channel after archiving to keep Discord tidy
        try:
            ch = interaction.channel
            if isinstance(ch, discord.TextChannel):
                await interaction.followup.send("🗄 Archiving ticket channel…", ephemeral=True)
                await ch.delete(reason=f"Ticket {self.ticket_id} archived by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Channel delete failed: {e}", ephemeral=True)

        # Log archiving (summaries remain in DB)
        await self._log(
            interaction,
            title="🗄 Ticket archived",
            desc=(
                f"ID: {self.ticket_id}\n"
                f"Archived by: {interaction.user} ({interaction.user.id})\n"
                f"Timestamp: {datetime.utcnow().isoformat()}"
            ),
            level="info",
        )
    
    @discord.ui.button(label="💡 Suggest reply", style=discord.ButtonStyle.success, custom_id="ticket_suggest_btn")
    async def suggest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("❌ Not a text channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        msgs: List[str] = []
        async for m in ch.history(limit=20, oldest_first=False):
            if not m.author.bot and m.content:
                msgs.append(f"{m.author.display_name}: {m.content}")
        msgs = list(reversed(msgs))
        prompt = (
            "You are a support assistant. Summarize the situation and propose a short reply the staff can post.\n\n"
            + "\n".join(msgs)
        )
        try:
            suggestion = await ask_gpt(
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get suggestion: {e}", ephemeral=True)
            return
        embed = discord.Embed(title="💡 Suggested reply", description=(suggestion or "-"), color=discord.Color.teal())
        await interaction.followup.send(embed=embed, ephemeral=True)
        await self._log(interaction, "💡 Suggest reply", f"id={self.ticket_id}")
    # (end of TicketActionView)


class TicketOpenView(discord.ui.View):
    def __init__(self, cog: "TicketBot", timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog

    @discord.ui.button(label="📨 Create ticket", style=discord.ButtonStyle.primary, custom_id="ticket_open_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.cog.create_ticket_for_user(interaction, description="New ticket")


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketBot(bot))
