import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.app_commands import checks as app_checks
import asyncpg
from asyncpg import exceptions as pg_exceptions
import json
import asyncio
import time
from datetime import datetime, timedelta
import re
from typing import Optional, List, Dict, Any, cast
from utils.settings_service import SettingsService
from utils.settings_helpers import CachedSettingsHelper
from utils.db_helpers import acquire_safe, is_pool_healthy
from utils.validators import validate_admin
from utils.embed_builder import EmbedBuilder

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.logger import logger, log_with_guild, log_guild_action, log_database_event
from gpt.helpers import ask_gpt
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
        self.db: Optional[asyncpg.Pool] = None
        settings = getattr(bot, "settings", None)
        if not isinstance(settings, SettingsService):
            raise RuntimeError("SettingsService not available on bot instance")
        self.settings: SettingsService = settings
        self.settings_helper = CachedSettingsHelper(settings)
        # In-memory cooldown tracking voor suggest_reply button
        self._suggest_reply_cooldowns: Dict[int, float] = {}  # user_id -> last_used_timestamp
        self._max_cooldown_entries = 1000
        self._max_cooldown_age = 3600  # 1 hour - remove stale entries
        # Start async setup zonder de event loop te blokkeren
        self.bot.loop.create_task(self.setup_db())
        # Register persistent view so the ticket button keeps working after restarts
        try:
            self.bot.add_view(TicketOpenView(self, timeout=None))
        except Exception as e:
            logger.warning(f"⚠️ TicketBot: kon TicketOpenView niet registreren: {e}")
        
        # Note: check_idle_tickets task will be started in cog_load hook

    def _cleanup_cooldowns(self) -> None:
        """Remove expired cooldown entries (called on access, not periodic loop)."""
        current_time = time.time()
        expired_keys = [
            user_id for user_id, last_used in self._suggest_reply_cooldowns.items()
            if current_time - last_used > self._max_cooldown_age
        ]
        for key in expired_keys:
            del self._suggest_reply_cooldowns[key]
        
        # Enforce max size
        if len(self._suggest_reply_cooldowns) > self._max_cooldown_entries:
            sorted_by_age = sorted(self._suggest_reply_cooldowns.items(), key=lambda x: x[1])
            excess = len(self._suggest_reply_cooldowns) - self._max_cooldown_entries
            for key, _ in sorted_by_age[:excess]:
                del self._suggest_reply_cooldowns[key]
            logger.debug(f"Ticket cooldowns: Evicted {excess} oldest entries, size now: {len(self._suggest_reply_cooldowns)}")
    
    async def setup_db(self) -> None:
        """Initialiseer database connectie en zorg dat de tabel bestaat."""
        try:
            from utils.db_helpers import create_db_pool
            pool = await create_db_pool(
                config.DATABASE_URL,
                name="ticketbot",
                min_size=1,
                max_size=10,
                command_timeout=10.0
            )
            log_database_event("DB_CONNECTED", details="TicketBot database pool created")
            
            async with acquire_safe(pool) as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS support_tickets (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
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
            
            self.db = pool
            logger.info("✅ TicketBot: DB ready (support_tickets)")
            log_database_event("DB_READY", details="TicketBot database fully initialized")
        except Exception as e:
            log_database_event("DB_INIT_ERROR", details=f"TicketBot setup failed: {e}")
            logger.error(f"❌ TicketBot: DB init error: {e}")
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None

    async def send_log_embed(self, title: str, description: str, level: str = "info", guild_id: int = 0) -> None:
        """Send log embed to the correct guild's log channel"""
        if guild_id == 0:
            # Fallback for legacy calls without guild_id
            logger.warning("⚠️ TicketBot send_log_embed called without guild_id - skipping Discord log")
            return

        # Check log level filtering
        from utils.logger import should_log_to_discord
        if not should_log_to_discord(level, guild_id):
            return

        try:
            embed = EmbedBuilder.log(title, description, level, guild_id)
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
    async def ticket(self, interaction: discord.Interaction, description: str) -> None:
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
        if not is_pool_healthy(self.db):
            try:
                await self.setup_db()
            except Exception as e:
                logger.error(f"❌ TicketBot: DB connect error: {e}")
                await interaction.followup.send("❌ Database is not available. Please try again later.")
                return

        user = interaction.user
        user_display = f"{user} ({user.id})"

        try:
            async with acquire_safe(self.db) as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO support_tickets (guild_id, user_id, username, description)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, created_at
                    """,
                    interaction.guild.id,
                    int(user.id),
                    str(user),
                    description.strip(),
                )
        except RuntimeError as e:
            await interaction.followup.send("❌ Database not available. Please try again later.", ephemeral=True)
            return
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None
            logger.warning(f"Database connection error: {conn_err}")
            await interaction.followup.send("❌ Database connection error. Please try again later.")
            return
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

        ticket_id: int
        created_at: datetime
        if row:
            ticket_id = int(row["id"])  # not None after successful insert
            created_at = row["created_at"]
        else:
            # Fallback: should not happen, but keep types safe
            ticket_id = 0
            created_at = datetime.utcnow()

        # Confirmation embed to the user (ephemeral followup) using EmbedBuilder
        confirm = EmbedBuilder.success(
            title="🎟️ Ticket created",
            description="Your ticket has been created successfully."
        )
        confirm.timestamp = created_at
        confirm.add_field(name="Ticket ID", value=str(ticket_id), inline=True)
        confirm.add_field(name="User", value=f"{user.mention}", inline=True)
        confirm.add_field(name="Status", value="open", inline=True)
        from utils.sanitizer import safe_embed_text
        confirm.add_field(name="Description", value=safe_embed_text(description[:1024] or "—"), inline=False)

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
                raise RuntimeError("Category channel not found or not a category type")
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
                name=f"ticket-{ticket_id}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket {ticket_id} created by {user}"
            )

            # Update DB met channel_id
            try:
                async with acquire_safe(self.db) as conn:
                    await conn.execute(
                        "UPDATE support_tickets SET channel_id = $1, updated_at = NOW() WHERE id = $2 AND guild_id = $3",
                        int(channel.id),
                        ticket_id,
                        interaction.guild.id,
                    )
            except RuntimeError:
                logger.warning("⚠️ TicketBot: Database pool not available for channel_id update")
            except Exception as e:
                logger.warning(f"⚠️ TicketBot: kon channel_id niet opslaan: {e}")

            # Initial message in the ticket channel using EmbedBuilder
            ch_embed = EmbedBuilder.success(
                title="🎟️ Ticket created",
                description=(
                    f"Ticket ID: `{ticket_id}`\n"
                    f"User: {user.mention}\n"
                    f"Status: **open**\n\n"
                    f"Description:\n{description}"
                )
            )
            ch_embed.timestamp = created_at
            view = TicketActionView(
                bot=self.bot,
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
            guild_id=interaction.guild.id,
        )

    @app_commands.command(name="ticket_panel_post", description="Post a ticket panel with a Create ticket button")
    async def ticket_panel_post(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
            return
        target = channel or cast(discord.TextChannel, interaction.channel)
        if target is None:
            await interaction.response.send_message("❌ No channel specified.", ephemeral=True)
            return
        embed = EmbedBuilder.info(
            title="Support Tickets",
            description="To create a ticket, click the button below."
        )
        view = TicketOpenView(self, timeout=None)
        await target.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Ticket panel posted.", ephemeral=True)

    async def create_ticket_for_user(self, interaction: discord.Interaction, description: str) -> None:
        # Ensure DB
        if not is_pool_healthy(self.db):
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
            async with acquire_safe(self.db) as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO support_tickets (guild_id, user_id, username, description)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, created_at
                    """,
                    interaction.guild.id if interaction.guild else 0,
                    int(user.id),
                    str(user),
                    (description or "").strip() or "—",
                )
        except RuntimeError as e:
            await interaction.followup.send("❌ Database not available. Please try again later.", ephemeral=True)
            return
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None
            logger.warning(f"Database connection error: {conn_err}")
            await interaction.followup.send("❌ Database connection error. Please try again later.")
            return
        except Exception as e:
            logger.exception("🚨 TicketBot: insert failed")
            await self.send_log_embed(
                title="🚨 Ticket creation failed",
                description=f"User: {user_display}\nError: {e}",
                level="error",
                guild_id=interaction.guild.id if interaction.guild else 0,
            )
            await interaction.followup.send("❌ Something went wrong creating your ticket.")
            return
        ticket_id = int(row["id"]) if row else 0
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
            name=f"ticket-{ticket_id}",
            category=category,
            overwrites=overwrites,
            reason=f"Ticket {ticket_id} created by {user}"
        )
        # Store channel id
        try:
            if row and "id" in row:
                async with acquire_safe(self.db) as conn:
                    await conn.execute(
                        "UPDATE support_tickets SET channel_id = $1, updated_at = NOW() WHERE id = $2 AND guild_id = $3",
                        int(channel.id), int(row["id"]), interaction.guild.id if interaction.guild else 0
                    )
        except RuntimeError:
            # Pool not available - log but don't fail ticket creation
            logger.warning("⚠️ TicketBot: Database pool not available for channel_id update")
        except Exception as e:
            # Log the error but don't fail the ticket creation
            await self.send_log_embed(
                title="⚠️ Ticket channel update failed",
                description=f"Ticket ID: {ticket_id}\nChannel: {channel.mention}\nError: {e}",
                level="warning",
                guild_id=interaction.guild.id if interaction.guild else 0,
            )

        # Create success embed (always shown, even if channel_id update failed) using EmbedBuilder
        ch_embed = EmbedBuilder.success(
            title="🎟️ Ticket created",
            description=(
                f"Ticket ID: `{ticket_id}`\n"
                f"User: {user.mention}\n"
                f"Status: **open**\n\n"
                f"Description:\n{description or '—'}"
            )
        )
        ch_embed.timestamp = created_at
        view = TicketActionView(
            bot=self.bot,
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

    async def _compute_stats(self, scope: str, guild_id: Optional[int] = None) -> tuple[dict, Optional[int], Optional[List[int]]]:
        # scope: 'all' | '7d' | '30d'
        if not is_pool_healthy(self.db):
            return {}, None, None
        try:
            async with acquire_safe(self.db) as conn:
                where_parts = []
                params: List[Any] = []
                param_index = 1
                
                if guild_id is not None:
                    where_parts.append(f"guild_id = ${param_index}")
                    params.append(guild_id)
                    param_index += 1
                if scope == "7d":
                    where_parts.append("created_at >= NOW() - INTERVAL '7 days'")
                elif scope == "30d":
                    where_parts.append("created_at >= NOW() - INTERVAL '30 days'")
                where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
                
                # Get status counts
                counts_query = f"SELECT status, COUNT(*) c FROM support_tickets {where} GROUP BY status"
                counts = await conn.fetch(counts_query, *params) if params else await conn.fetch(counts_query)
                status_to_count = {r["status"] or "-": int(r["c"]) for r in counts}
                
                # Get open ticket IDs (only non-closed tickets)
                # Build open_where with same parameters as main query
                open_where_parts = where_parts.copy() if where_parts else []
                open_where_parts.append("status IS DISTINCT FROM 'closed'")
                open_where = "WHERE " + " AND ".join(open_where_parts) if open_where_parts else "WHERE status IS DISTINCT FROM 'closed'"
                open_ids_query = f"SELECT id FROM support_tickets {open_where} ORDER BY id ASC"
                # Use same params as main query (guild_id filter applies to open tickets too)
                open_ids_rows = await conn.fetch(open_ids_query, *params) if params else await conn.fetch(open_ids_query)
                open_ticket_ids = [int(row["id"]) for row in open_ids_rows] if open_ids_rows else []
                
                # average cycle (closed only)
                avg_where_parts = where_parts.copy() if where_parts else []
                avg_where_parts.append("status='closed'")
                avg_where = "WHERE " + " AND ".join(avg_where_parts) if avg_where_parts else ""
                avg_query = f"SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) AS avg_s FROM support_tickets {avg_where}"
                avg_row = await conn.fetchrow(avg_query, *params) if params else await conn.fetchrow(avg_query)
                avg_seconds: Optional[int] = None
                if avg_row and avg_row["avg_s"] is not None:
                    try:
                        avg_seconds = int(float(avg_row["avg_s"]))
                    except Exception:
                        avg_seconds = None
                return status_to_count, avg_seconds, open_ticket_ids
        except RuntimeError:
            return {}, None, None
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in _compute_stats: {conn_err}")
            return {}, None, None
        except Exception as e:
            logger.error(f"Database error in _compute_stats: {e}")
            return {}, None, None

    async def _top_topics(self, limit: int = 5) -> Dict[str, int]:
        if not is_pool_healthy(self.db):
            return {}
        try:
            async with acquire_safe(self.db) as conn:
                rows = await conn.fetch(
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
        except RuntimeError:
            return {}
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in _top_topics: {conn_err}")
            return {}
        except Exception as e:
            logger.error(f"Database error in _top_topics: {e}")
            return {}

    def _settings_get(self, scope: str, key: str, guild_id: int, fallback: Optional[int] = None):
        """Get setting using cached helper. Returns fallback if not found."""
        try:
            if fallback is not None:
                return self.settings_helper.get_int(scope, key, guild_id, fallback=fallback)
            else:
                return self.settings_helper.get_int(scope, key, guild_id, fallback=0)
        except Exception:
            return fallback

    async def _post_ticket_summary(self, channel: discord.TextChannel, ticket_id: int, guild_id: int) -> Optional[Dict[str, str]]:
        """Generate and post a GPT-based summary for a ticket (used by auto-close)."""
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

            from utils.sanitizer import safe_prompt, safe_embed_text
            # Sanitize each message before sending to GPT
            safe_messages = [safe_prompt(msg) for msg in messages[-50:]]
            prompt = (
                "You are a helpful assistant. Summarize the following Discord ticket conversation in clear and concise English.\n\n"
                + "\n".join(safe_messages)
            )

            try:
                summary_text = await ask_gpt(
                    messages=[{"role": "user", "content": prompt}],
                    user_id=None,
                    guild_id=guild_id,
                )
            except Exception as e:
                await channel.send(f"❌ Failed to generate summary: {e}")
                return None

            embed = EmbedBuilder.success(
                title="📄 Ticket Summary",
                description=safe_embed_text((summary_text or "").strip() or "(empty)")
            )
            await channel.send(embed=embed)
            
            # Register summary for FAQ detection
            if is_pool_healthy(self.db):
                try:
                    # Create a temporary view instance for the static method
                    temp_view = TicketActionView(
                        bot=self.bot,
                        ticket_id=ticket_id,
                        support_role_id=None,
                        cog=self,
                        timeout=None
                    )
                    key = await TicketActionView._register_summary(
                        temp_view,
                        ticket_id,
                        (summary_text or "").strip()
                    )
                    cleaned = (summary_text or "").strip()
                    if key:
                        return {"summary": cleaned, "key": key}
                    return {"summary": cleaned} if cleaned else None
                except Exception as e:
                    logger.warning(f"⚠️ Failed to register summary: {e}")
            
            return {"summary": (summary_text or "").strip()}
        except Exception as e:
            logger.exception(f"❌ Error generating ticket summary: {e}")
            return None

    def _normalize_id(self, value: Optional[object]) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _get_log_channel_id(self, guild_id: int) -> int:
        value = self._settings_get("system", "log_channel_id", guild_id, 0)  # Must be configured via /config system set_log_channel
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
            guild_id,
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
        guild_id: Optional[int] = None,
    ) -> None:
        if not is_pool_healthy(self.db):
            return

        # Use guild_id if provided, otherwise compute stats for all guilds (legacy behavior)
        counts, avg_seconds, _ = await self._compute_stats("all", guild_id)
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

        try:
            async with acquire_safe(self.db) as conn:
                await conn.execute(
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
        except RuntimeError:
            logger.debug("Database pool not available for metrics snapshot")
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in capture_metrics_snapshot: {conn_err}")
        except Exception as e:
            logger.error(f"Database error in capture_metrics_snapshot: {e}")

        try:
            # Only log if guild_id is provided
            if guild_id:
                await self.send_log_embed(
                    title="📊 Ticket metrics snapshot",
                    description=(
                        f"scope: `{scope}`\n"
                        f"triggered_by: {triggered_by}\n"
                        f"ticket_id: {ticket_id or '-'}\n"
                        f"topic: {topic or '-'}"
                    ),
                    level="info",
                    guild_id=guild_id,
                )
        except Exception:
            pass

    def _stats_embed(self, counts: dict, avg_seconds: Optional[int], open_ticket_ids: Optional[List[int]] = None) -> discord.Embed:
        embed = EmbedBuilder.info(title="📊 Ticket Statistics")
        for s in ["open", "claimed", "waiting_for_user", "escalated", "closed", "archived"]:
            embed.add_field(name=s, value=str(counts.get(s, 0)), inline=True)
        
        # Add open ticket IDs if available
        if open_ticket_ids and len(open_ticket_ids) > 0:
            # Format IDs nicely (max 10 IDs shown, rest truncated)
            ids_display = open_ticket_ids[:10]
            ids_text = ", ".join(str(tid) for tid in ids_display)
            if len(open_ticket_ids) > 10:
                ids_text += f" (+{len(open_ticket_ids) - 10} more)"
            embed.add_field(
                name="🎫 Open Ticket IDs",
                value=f"`{ids_text}`" if ids_text else "None",
                inline=False
            )
        elif counts.get("open", 0) > 0:
            # If there are open tickets but we don't have IDs, show a note
            embed.add_field(
                name="🎫 Open Ticket IDs",
                value="*Unable to fetch IDs*",
                inline=False
            )
        
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

        async def _update(self, interaction: discord.Interaction, scope: Optional[str] = None) -> None:
            if scope:
                self.scope = scope
            is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
            if not is_admin:
                await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
                return
            counts, avg_seconds, open_ticket_ids = await self.cog._compute_stats(self.scope, interaction.guild.id if interaction.guild else None)
            embed = self.cog._stats_embed(counts, avg_seconds, open_ticket_ids)
            await interaction.response.edit_message(embed=embed, view=self)
            try:
                if interaction.guild:
                    await self.cog.send_log_embed(
                        title="📊 Ticket stats (button)",
                        description=f"by={interaction.user.id} • scope={self.scope} • counts={counts}",
                        level="info",
                        guild_id=interaction.guild.id,
                    )
                if is_pool_healthy(self.cog.db):
                    try:
                        async with acquire_safe(self.cog.db) as conn:
                            await conn.execute(
                                "INSERT INTO ticket_metrics (snapshot, scope, counts, average_cycle_time, triggered_by) VALUES ($1::jsonb,$2,$3::jsonb,$4,$5)",
                                json.dumps({"counts": counts, "avg": avg_seconds, "scope": self.scope}),
                                self.scope,
                                json.dumps(counts),
                                avg_seconds,
                                int(interaction.user.id)
                            )
                    except RuntimeError:
                        pass
                    except Exception:
                        pass
            except Exception:
                pass

        @discord.ui.button(label="Last 7d", style=discord.ButtonStyle.secondary, custom_id="stats_7d")
        async def last7(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await self._update(interaction, "7d")

        @discord.ui.button(label="Last 30d", style=discord.ButtonStyle.secondary, custom_id="stats_30d")
        async def last30(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await self._update(interaction, "30d")

        @discord.ui.button(label="All time", style=discord.ButtonStyle.secondary, custom_id="stats_all")
        async def alltime(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await self._update(interaction, "all")

        @discord.ui.button(label="Refresh 🔄", style=discord.ButtonStyle.primary, custom_id="stats_refresh")
        async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await self._update(interaction, None)

    @app_commands.command(name="ticket_stats", description="Show ticket statistics (admin)")
    @app_commands.describe(public="Post in channel instead of ephemeral (default: false)")
    async def ticket_stats(self, interaction: discord.Interaction, public: bool = False) -> None:
        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=not public)

        if not is_pool_healthy(self.db):
            await interaction.followup.send("❌ Database not connected.", ephemeral=not public)
            return
        guild_id = interaction.guild.id if interaction.guild else None
        counts, avg_seconds, open_ticket_ids = await self._compute_stats("all", guild_id)
        embed = self._stats_embed(counts, avg_seconds, open_ticket_ids)
        view = TicketBot.StatsView(self, public=public, scope="all")
        await interaction.followup.send(embed=embed, view=view, ephemeral=not public)
        if interaction.guild:
            await self.send_log_embed(
                title="📊 Ticket stats",
                description=f"by={interaction.user.id} • scope=all • public={public} • counts={counts}",
                level="info",
                guild_id=interaction.guild.id,
            )
        try:
            async with acquire_safe(self.db) as conn:
                await conn.execute(
                    "INSERT INTO ticket_metrics (snapshot, scope, counts, average_cycle_time, triggered_by) VALUES ($1::jsonb,$2,$3::jsonb,$4,$5)",
                    json.dumps({"counts": counts, "avg": avg_seconds, "scope": "all"}),
                    "all",
                    json.dumps(counts),
                    avg_seconds,
                    int(interaction.user.id)
                )
        except RuntimeError:
            pass
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
        id: str,
        status: app_commands.Choice[str],
        escalate_to: Optional[discord.Role] = None,
    ):
        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        if not is_pool_healthy(self.db):
            await interaction.followup.send("❌ Database not connected.", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.followup.send("❌ This command only works in a server.", ephemeral=True)
            return

        # Convert string ID to int
        try:
            ticket_id = int(id)
        except ValueError:
            await interaction.followup.send(f"❌ Invalid ticket ID: `{id}`. Please use a valid number.", ephemeral=True)
            return

        new_status = status.value
        try:
            async with acquire_safe(self.db) as conn:
                if new_status == "escalated":
                    await conn.execute(
                        "UPDATE support_tickets SET status=$1, escalated_to=$2, updated_at=NOW() WHERE id=$3 AND guild_id=$4",
                        new_status,
                        int(escalate_to.id) if escalate_to else None,
                        ticket_id,
                        interaction.guild.id,
                    )
                elif new_status == "claimed":
                    await conn.execute(
                        "UPDATE support_tickets SET status=$1, updated_at=NOW(), claimed_by=COALESCE(claimed_by,$2), claimed_at=COALESCE(claimed_at,NOW()) WHERE id=$3 AND guild_id=$4",
                        new_status,
                        int(interaction.user.id),
                        ticket_id,
                        interaction.guild.id,
                    )
                elif new_status == "archived":
                    await conn.execute(
                        "UPDATE support_tickets SET status=$1, archived_at=NOW(), archived_by=$2, updated_at=NOW() WHERE id=$3 AND guild_id=$4",
                        new_status,
                        int(interaction.user.id),
                        ticket_id,
                        interaction.guild.id,
                    )
                else:
                    await conn.execute(
                        "UPDATE support_tickets SET status=$1, updated_at=NOW() WHERE id=$2 AND guild_id=$3",
                        new_status,
                        ticket_id,
                        interaction.guild.id,
                    )
        except RuntimeError as e:
            await interaction.followup.send("❌ Database not available. Please try again later.", ephemeral=True)
            return
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None
            logger.warning(f"Database connection error: {conn_err}")
            await interaction.followup.send("❌ Database connection error. Please try again later.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to update status: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Ticket `{ticket_id}` status set to **{new_status}**.", ephemeral=True)
        # Log
        try:
            if interaction.guild:
                await self.send_log_embed(
                    title="🧭 Ticket status update",
                    description=(
                        f"ID: {ticket_id}\n"
                        f"New status: **{new_status}**\n"
                        f"By: {interaction.user} ({interaction.user.id})"
                        + (f"\nEscalated to: <@&{escalate_to.id}>" if (new_status == 'escalated' and escalate_to) else "")
                    ),
                    level="info",
                    guild_id=interaction.guild.id,
                )
        except Exception:
            pass

    @ticket_status.autocomplete("id")
    async def ticket_id_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for ticket IDs - shows open tickets."""
        if not interaction.guild:
            return []
        is_admin, _ = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            return []
        if not is_pool_healthy(self.db):
            return []
        
        try:
            async with acquire_safe(self.db) as conn:
                # Get open tickets (non-closed) for this guild
                rows = await conn.fetch(
                    """
                    SELECT id, username, status, description
                    FROM support_tickets
                    WHERE guild_id = $1 AND status IS DISTINCT FROM 'closed'
                    ORDER BY id DESC
                    LIMIT 25
                    """,
                    interaction.guild.id
                )
            
            choices: List[app_commands.Choice[str]] = []
            current_lower = current.lower() if current else ""
            
            for row in rows:
                ticket_id = str(row["id"])
                username = row.get("username") or "Unknown"
                ticket_status = row.get("status") or "open"
                description = (row.get("description") or "")[:30]
                
                # Show ID, username, and status in the choice name
                name = f"#{ticket_id} - {username} ({ticket_status})"
                if description:
                    name += f" - {description}"
                
                # Filter by current input (matches ID or username)
                if not current_lower or current_lower in ticket_id or current_lower in username.lower():
                    choices.append(app_commands.Choice(
                        name=name[:100],  # Discord limit is 100 chars
                        value=ticket_id
                    ))
                    if len(choices) >= 25:  # Discord limit
                        break
            
            return choices
        except Exception as e:
            logger.debug(f"Error in ticket_id_autocomplete: {e}")
            return []

    @tasks.loop(hours=24)
    async def check_idle_tickets(self) -> None:
        """Check for idle tickets and send reminders or auto-close."""
        if not is_pool_healthy(self.db):
            return
        
        try:
            # Get thresholds from settings (default to 5 and 14 days)
            idle_threshold = self._settings_get("ticketbot", "idle_days_threshold", 0, 5) or 5
            auto_close_threshold = self._settings_get("ticketbot", "auto_close_days_threshold", 0, 14) or 14
            
            async with acquire_safe(self.db) as conn:
                # Query idle tickets (5+ days, not closed/archived, but not old enough for auto-close)
                idle_tickets = await conn.fetch(
                    """
                    SELECT id, guild_id, user_id, username, channel_id, description, updated_at
                    FROM support_tickets
                    WHERE status IN ('open', 'claimed', 'waiting_for_user')
                      AND updated_at < NOW() - ($1 || ' days')::INTERVAL
                      AND updated_at >= NOW() - ($2 || ' days')::INTERVAL
                    ORDER BY updated_at ASC
                    """,
                    str(idle_threshold), str(auto_close_threshold)
                )
                
                # Query very old tickets (14+ days, auto-close)
                old_tickets = await conn.fetch(
                    """
                    SELECT id, guild_id, user_id, username, channel_id, description, updated_at
                    FROM support_tickets
                    WHERE status IN ('open', 'claimed', 'waiting_for_user')
                      AND updated_at < NOW() - ($1 || ' days')::INTERVAL
                    ORDER BY updated_at ASC
                    """,
                    str(auto_close_threshold)
                )
            
            # Process idle tickets (send DM reminders)
            for ticket in idle_tickets:
                try:
                    guild_id = ticket["guild_id"]
                    user_id = ticket["user_id"]
                    ticket_id = ticket["id"]
                    
                    # Get guild
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue
                    
                    # Get user
                    user = guild.get_member(user_id) or await self.bot.fetch_user(user_id)
                    if not user:
                        continue
                    
                    # Send DM with reminder
                    try:
                        embed = EmbedBuilder.warning(
                            title="⏰ Ticket Idle Reminder",
                            description=(
                                f"Your ticket **#{ticket_id}** has been inactive for {idle_threshold} days.\n\n"
                                f"**Description:** {ticket['description'][:200]}{'...' if len(ticket['description']) > 200 else ''}\n\n"
                                f"Would you like to close it or keep it open?"
                            )
                        )
                        view = IdleTicketView(self, ticket_id, guild_id)
                        await user.send(embed=embed, view=view)
                        logger.info(f"✅ Sent idle reminder DM for ticket {ticket_id} to user {user_id}")
                    except discord.Forbidden:
                        logger.debug(f"⚠️ Cannot send DM to user {user_id} (DMs disabled)")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to send idle reminder DM: {e}")
                    
                    # Also notify staff in ticket channel if channel exists
                    channel_id = ticket.get("channel_id")
                    if channel_id:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if isinstance(channel, discord.TextChannel):
                                support_role = self._resolve_support_role(guild)
                                await channel.send(
                                    content=(support_role.mention if support_role else None),
                                    embed=EmbedBuilder.warning(
                                        title="⏰ Ticket Idle",
                                        description=f"This ticket has been inactive for {idle_threshold} days. Creator has been notified."
                                    ),
                                    allowed_mentions=discord.AllowedMentions(roles=True)
                                )
                        except Exception as e:
                            logger.debug(f"⚠️ Failed to notify staff in channel: {e}")
                
                except Exception as e:
                    logger.exception(f"❌ Error processing idle ticket {ticket.get('id')}: {e}")
            
            # Process very old tickets (auto-close)
            for ticket in old_tickets:
                try:
                    ticket_id = ticket["id"]
                    guild_id = ticket["guild_id"]
                    channel_id = ticket.get("channel_id")
                    
                    # Auto-close the ticket
                    if is_pool_healthy(self.db):
                        try:
                            async with acquire_safe(self.db) as conn:
                                await conn.execute(
                                    """
                                    UPDATE support_tickets
                                    SET status = 'closed', updated_at = NOW()
                                    WHERE id = $1 AND guild_id = $2
                                    """,
                                    ticket_id, guild_id
                                )
                        except RuntimeError:
                            logger.debug(f"⚠️ Database pool not available for auto-close ticket {ticket_id}")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to auto-close ticket {ticket_id} in DB: {e}")
                    
                    # Get channel and post summary
                    if channel_id:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if isinstance(channel, discord.TextChannel):
                                # Lock channel
                                owner_id = ticket.get("user_id")
                                member = channel.guild.get_member(owner_id) if owner_id else None
                                overwrites = channel.overwrites
                                if member:
                                    overwrites[member] = discord.PermissionOverwrite(
                                        view_channel=True, send_messages=False, read_message_history=True
                                    )
                                overwrites[channel.guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                                await channel.edit(overwrites=overwrites, reason=f"Ticket {ticket_id} auto-closed after {auto_close_threshold} days")
                                
                                # Rename channel
                                try:
                                    await channel.edit(name=f"ticket-{ticket_id}-closed")
                                except Exception:
                                    pass
                                
                                # Post summary using helper method
                                summary_meta = await self._post_ticket_summary(channel, ticket_id, guild_id)
                                
                                # Post auto-close message
                                await channel.send(
                                    embed=EmbedBuilder.error(
                                        title="🔒 Ticket Auto-Closed",
                                        description=f"This ticket was automatically closed after {auto_close_threshold} days of inactivity."
                                    )
                                )
                                
                                logger.info(f"✅ Auto-closed ticket {ticket_id} after {auto_close_threshold} days")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to auto-close ticket {ticket_id} channel: {e}")
                    
                    # Log the auto-close
                    await self.send_log_embed(
                        title="🔒 Ticket auto-closed",
                        description=(
                            f"ID: {ticket_id}\n"
                            f"Auto-closed after {auto_close_threshold} days of inactivity"
                        ),
                        level="warning",
                        guild_id=guild_id,
                    )
                
                except Exception as e:
                    logger.exception(f"❌ Error auto-closing ticket {ticket.get('id')}: {e}")
        
        except Exception as e:
            logger.exception(f"❌ Error in check_idle_tickets task: {e}")

    @check_idle_tickets.before_loop
    async def before_check_idle_tickets(self):
        await self.bot.wait_until_ready()
        # Wait for database to be ready
        while not is_pool_healthy(self.db):
            await asyncio.sleep(2)

    def cog_load(self):
        """Called when the cog is loaded - start the idle ticket check task."""
        if not self.check_idle_tickets.is_running():
            self.check_idle_tickets.start()

    async def cog_unload(self):
        """Called when the cog is unloaded - close the database pool."""
        if self.db:
            try:
                await self.db.close()
            except Exception:
                pass
            self.db = None


class TicketActionView(discord.ui.View):
    def __init__(self, bot: commands.Bot, ticket_id: int, support_role_id: Optional[int] = None, cog: Optional["TicketBot"] = None, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.ticket_id = ticket_id
        self.support_role_id = support_role_id
        self.cog = cog

    async def _is_staff(self, interaction: discord.Interaction) -> bool:
        is_admin, _ = await validate_admin(interaction, raise_on_fail=False)
        return is_admin

    async def _log(self, interaction: discord.Interaction, title: str, desc: str, level: str = "info") -> None:
        # Use channel send via embed helper from a new simple instance-less call
        try:
            if self.cog and interaction.guild:
                await self.cog.send_log_embed(
                    title=title,
                    description=desc,
                    level=level,
                    guild_id=interaction.guild.id
                )
                return
            embed = EmbedBuilder.log(title=title, description=desc, level=level)
            embed.set_footer(text="ticketbot")
            channel = self.bot.get_channel(0)  # Must be configured via /config system set_log_channel
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

            from utils.sanitizer import safe_prompt, safe_embed_text
            # Sanitize each message before sending to GPT
            safe_messages = [safe_prompt(msg) for msg in messages[-50:]]
            prompt = (
                "You are a helpful assistant. Summarize the following Discord ticket conversation in clear and concise English.\n\n"
                + "\n".join(safe_messages)
            )

            try:
                # Use default model from ask_gpt (defaults to grok-3 for Grok, gpt-3.5-turbo for OpenAI)
                guild_id = channel.guild.id if channel.guild else None
                summary_text = await ask_gpt(
                    messages=[{"role": "user", "content": prompt}],
                    user_id=None,
                    guild_id=guild_id,
                )
            except Exception as e:
                await channel.send(f"❌ Failed to generate summary: {e}")
                return None

            embed = EmbedBuilder.success(
                title="📄 Ticket Summary",
                description=safe_embed_text((summary_text or "").strip() or "(empty)")
            )
            await channel.send(embed=embed)
            # Register the summary for clustering/FAQ suggestions
            key = await TicketActionView._register_summary(self, self.ticket_id, (summary_text or "").strip())
            cleaned = (summary_text or "").strip()
            if key:
                return {"summary": cleaned, "key": key}
            return {"summary": cleaned} if cleaned else None
        except Exception:
            # Non-fatal; do not block the close flow on summary issues
            return None

    @staticmethod
    def _compute_similarity_key(text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        tokens = [t for t in normalized.split() if len(t) >= 4 and t not in {
            "this","that","with","from","have","about","which","their","there","would","could","should",
            "subject","ticket","issue","user","message","chat","channel","please","thank","thanks"
        }]
        # Use top unique tokens alphabetically as a simple key
        unique_tokens = sorted(set(tokens))[:12]
        key = "-".join(unique_tokens)
        return key[:256]

    @staticmethod
    async def _register_summary(view_instance, ticket_id: int, summary: str) -> Optional[str]:
        try:
            if not view_instance.cog or not is_pool_healthy(view_instance.cog.db):
                return None
            key = TicketActionView._compute_similarity_key(summary)
            since = datetime.utcnow() - timedelta(days=7)
            async with acquire_safe(view_instance.cog.db) as conn:
                # Insert summary
                await conn.execute(
                    "INSERT INTO ticket_summaries (ticket_id, summary, similarity_key) VALUES ($1, $2, $3)",
                    int(ticket_id), summary, key
                )
                # Check recent similar summaries
                rows = await conn.fetch(
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
                    embed = EmbedBuilder.warning(
                        title="💡 Repeated Ticket Pattern Detected",
                        description=(
                            "We detected multiple tickets with a similar topic in the last 7 days.\n\n"
                            f"Similarity key: `{key}`\n"
                            f"Occurrences: **{len(rows)}**\n\n"
                            "Consider adding an FAQ entry for this topic."
                        )
                    )
                    # Show a sample of the latest summary in the footer to aid admins
                    sample_preview = (summary[:180] + "…") if len(summary) > 180 else summary
                    embed.set_footer(text=f"Sample: {sample_preview}")
                    # Lightweight view with a placeholder button
                    view = discord.ui.View()

                    async def add_faq_callback(interaction: discord.Interaction) -> None:
                        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
                        if not is_admin:
                            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
                            return
                        if not view_instance.cog or not is_pool_healthy(view_instance.cog.db):
                            await interaction.response.send_message("❌ Database not available.", ephemeral=True)
                            return
                        try:
                            async with acquire_safe(view_instance.cog.db) as conn:
                                # Insert FAQ entry
                                await conn.execute(
                                    "INSERT INTO faq_entries (similarity_key, summary, created_by) VALUES ($1, $2, $3)",
                                    key, summary, int(interaction.user.id)
                                )
                            await interaction.response.send_message("✅ FAQ entry added.", ephemeral=True)
                            await view_instance._log(
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

                # Send to log channel
                try:
                    channel_id = 0  # Default fallback - should be configured via /config system set_log_channel
                    channel = view_instance.bot.get_channel(channel_id)
                    if channel and hasattr(channel, "send"):
                        text_channel = cast(discord.TextChannel, channel)
                        await text_channel.send(embed=embed, view=view)
                except Exception:
                    pass
                return key  # Return key only when FAQ is proposed

            return None  # Normal case: no FAQ proposed
        except Exception:
            # Do not block on summary registration failures
            return None

    @discord.ui.button(label="🎟️ Claim ticket", style=discord.ButtonStyle.primary, custom_id="ticket_claim_btn")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Je hebt geen rechten om te claimen.", ephemeral=True)
            return
        if not self.cog or not is_pool_healthy(self.cog.db):
            await interaction.response.send_message("❌ Database not available.", ephemeral=True)
            return
        try:
            async with acquire_safe(self.cog.db) as conn:
                row = await conn.fetchrow(
                    """
                    UPDATE support_tickets
                    SET claimed_by = $1, claimed_at = NOW(), updated_at = NOW()
                    WHERE id = $2 AND (claimed_by IS NULL OR claimed_by = 0) AND status = 'open'
                    RETURNING id
                    """,
                    int(interaction.user.id),
                    int(self.ticket_id),
                )
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in claim_button: {conn_err}")
            await interaction.response.send_message("❌ Database connection error. Please try again later.", ephemeral=True)
            return
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
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Je hebt geen rechten om te sluiten.", ephemeral=True)
            return
        if not self.cog or not is_pool_healthy(self.cog.db):
            await interaction.response.send_message("❌ Database not available.", ephemeral=True)
            return

        try:
            async with acquire_safe(self.cog.db) as conn:
                row = await conn.fetchrow(
                    """
                    UPDATE support_tickets
                    SET status = 'closed', updated_at = NOW()
                    WHERE id = $1 AND status <> 'closed'
                    RETURNING id, user_id, channel_id
                    """,
                    int(self.ticket_id),
                )
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in close_button: {conn_err}")
            await interaction.response.send_message("❌ Database connection error. Please try again later.", ephemeral=True)
            return
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
                    guild_id=interaction.guild.id if interaction.guild else None,
                )
            except Exception as e:
                await self._log(
                    interaction,
                    title="⚠️ Metrics snapshot failed",
                    desc=f"id={self.ticket_id} • error={e}",
                    level="warning",
                )

    @discord.ui.button(label="⏳ Wait for user", style=discord.ButtonStyle.secondary, custom_id="ticket_wait_btn")
    async def wait_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        if not self.cog or not is_pool_healthy(self.cog.db):
            await interaction.response.send_message("❌ Database not available.", ephemeral=True)
            return
        try:
            async with acquire_safe(self.cog.db) as conn:
                await conn.execute(
                    "UPDATE support_tickets SET status='waiting_for_user', updated_at = NOW() WHERE id = $1",
                    int(self.ticket_id),
                )
            await interaction.response.send_message("✅ Status set to waiting_for_user.", ephemeral=True)
            await self._log(interaction, "🕒 Ticket status", f"id={self.ticket_id} → waiting_for_user")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to update status: {e}", ephemeral=True)

    @discord.ui.button(label="🚩 Escalate", style=discord.ButtonStyle.secondary, custom_id="ticket_escalate_btn")
    async def escalate_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        if not self.cog or not is_pool_healthy(self.cog.db):
            await interaction.response.send_message("❌ Database not available.", ephemeral=True)
            return
        escalated_to = None
        if self.cog and interaction.guild:
            escalated_to = self.cog._get_escalation_role_id(interaction.guild.id)
        if escalated_to is None:
            target_role_id = getattr(config, "TICKET_ESCALATION_ROLE_ID", None)
            escalated_to = int(target_role_id) if isinstance(target_role_id, int) else None
        try:
            async with acquire_safe(self.cog.db) as conn:
                await conn.execute(
                    "UPDATE support_tickets SET status='escalated', escalated_to=$1, updated_at = NOW() WHERE id = $2",
                    escalated_to,
                    int(self.ticket_id),
                )
            await interaction.response.send_message("✅ Ticket escalated.", ephemeral=True)
            await self._log(interaction, "🚩 Ticket escalated", f"id={self.ticket_id} • to={escalated_to or '-'}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to escalate: {e}", ephemeral=True)

    @discord.ui.button(label="🗄 Archive ticket", style=discord.ButtonStyle.secondary, custom_id="ticket_archive_btn", disabled=True)
    async def archive_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Admin-only
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        if not self.cog or not is_pool_healthy(self.cog.db):
            await interaction.response.send_message("❌ Database not available.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        try:
            async with acquire_safe(self.cog.db) as conn:
                await conn.execute(
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
    async def suggest_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("❌ Not a text channel.", ephemeral=True)
            return
        
        # In-memory cooldown check (5 seconden tussen clicks)
        if self.cog:
            # Cleanup stale entries before checking
            self.cog._cleanup_cooldowns()
            
            current_time = time.time()
            last_used = self.cog._suggest_reply_cooldowns.get(interaction.user.id, 0)
            if current_time - last_used < 5.0:
                await interaction.response.send_message(
                    "⏳ Even wachten... Supabase die weer eens een edge-case vindt als 100 replies in een burst. Probeer over 5 seconden opnieuw.",
                    ephemeral=True
                )
                return
            self.cog._suggest_reply_cooldowns[interaction.user.id] = current_time
        
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
            guild_id = interaction.guild.id if interaction.guild else None
            suggestion = await ask_gpt(
                messages=[{"role": "user", "content": prompt}],
                user_id=interaction.user.id,
                guild_id=guild_id,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get suggestion: {e}", ephemeral=True)
            return
        embed = EmbedBuilder.status(
            title="💡 Suggested reply",
            description=(suggestion or "-")
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        await self._log(interaction, "💡 Suggest reply", f"id={self.ticket_id}")
    # (end of TicketActionView)


class TicketOpenView(discord.ui.View):
    def __init__(self, cog: "TicketBot", timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog

    @discord.ui.button(label="📨 Create ticket", style=discord.ButtonStyle.primary, custom_id="ticket_open_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.cog.create_ticket_for_user(interaction, description="New ticket")


class IdleTicketView(discord.ui.View):
    """View for idle ticket reminder with Close/Keep Open buttons."""
    def __init__(self, cog: TicketBot, ticket_id: int, guild_id: int):
        super().__init__(timeout=604800)  # 7 days timeout
        self.cog = cog
        self.ticket_id = ticket_id
        self.guild_id = guild_id

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="idle_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not is_pool_healthy(self.cog.db):
            await interaction.response.send_message("❌ Database not connected.", ephemeral=True)
            return
        
        try:
            # Update ticket status
            async with acquire_safe(self.cog.db) as conn:
                await conn.execute(
                    """
                    UPDATE support_tickets
                    SET status = 'closed', updated_at = NOW()
                    WHERE id = $1 AND guild_id = $2
                    """,
                    self.ticket_id, self.guild_id
                )
            
            await interaction.response.send_message(
                f"✅ Ticket #{self.ticket_id} has been closed.",
                ephemeral=True
            )
            
            # Log
            await self.cog.send_log_embed(
                title="🔒 Ticket closed (idle reminder)",
                description=f"ID: {self.ticket_id}\nClosed by: {interaction.user.mention}",
                level="info",
                guild_id=self.guild_id,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to close ticket: {e}", ephemeral=True)

    @discord.ui.button(label="Keep Open", style=discord.ButtonStyle.secondary, custom_id="idle_keep")
    async def keep_open(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not is_pool_healthy(self.cog.db):
            await interaction.response.send_message("❌ Database not connected.", ephemeral=True)
            return
        
        try:
            # Update updated_at to reset idle timer
            async with acquire_safe(self.cog.db) as conn:
                await conn.execute(
                    """
                    UPDATE support_tickets
                    SET updated_at = NOW()
                    WHERE id = $1 AND guild_id = $2
                    """,
                    self.ticket_id, self.guild_id
                )
            
            await interaction.response.send_message(
                f"✅ Ticket #{self.ticket_id} will remain open. The idle timer has been reset.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to update ticket: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketBot(bot))
