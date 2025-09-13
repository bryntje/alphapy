import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import checks as app_checks
import asyncpg
from datetime import datetime, timedelta
import re
from typing import Optional, List, cast

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.logger import logger
from gpt.helpers import ask_gpt
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
            # Status workflow columns (M2)
            try:
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();"
                )
                await conn.execute(
                    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS escalated_to BIGINT;"
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
                    "UPDATE support_tickets SET channel_id = $1, updated_at = NOW() WHERE id = $2",
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
            row = await conn_safe.fetchrow(
                """
                INSERT INTO support_tickets (user_id, username, description)
                VALUES ($1, $2, $3)
                RETURNING id, created_at
                """,
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
        category_id = int(getattr(config, "TICKET_CATEGORY_ID", 1416148921960628275))
        fetched = guild.get_channel(category_id) or await self.bot.fetch_channel(category_id)
        if not isinstance(fetched, discord.CategoryChannel):
            await interaction.followup.send("❌ Ticket category not found.")
            return
        category = fetched
        # Determine support role
        support_role: Optional[discord.Role] = None
        srid = getattr(config, "TICKET_ACCESS_ROLE_ID", None)
        if isinstance(srid, int):
            support_role = guild.get_role(srid)
        elif isinstance(srid, str) and srid.isdigit():
            support_role = guild.get_role(int(srid))
        if support_role is None:
            admin_candidate = getattr(config, "ADMIN_ROLE_ID", None)
            if isinstance(admin_candidate, int):
                support_role = guild.get_role(admin_candidate)
            elif isinstance(admin_candidate, list) and admin_candidate:
                first_role = admin_candidate[0]
                if isinstance(first_role, int):
                    support_role = guild.get_role(first_role)
                elif isinstance(first_role, str) and first_role.isdigit():
                    support_role = guild.get_role(int(first_role))
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
            conn_safe2 = cast(asyncpg.Connection, self.conn)
            await conn_safe2.execute(
                "UPDATE support_tickets SET channel_id = $1, updated_at = NOW() WHERE id = $2",
                int(channel.id), ticket_id
            )
        except Exception:
            pass
        ch_embed = discord.Embed(
            title="🎟️ Ticket created",
            color=discord.Color.green(),
            timestamp=created_at,
            description=(
                f"Ticket ID: `{ticket_id}`\n"
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
            timeout=None,
        )
        await channel.send(
            content=(support_role.mention if support_role else None),
            embed=ch_embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )
        await interaction.followup.send(f"✅ Ticket created in {channel.mention}", ephemeral=True)


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

    async def _post_summary(self, channel: discord.TextChannel) -> None:
        """Generate and post a GPT-based summary of the ticket conversation.

        # TODO: Inject GPT-generated summary here in a future version
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
                return

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
                return

            embed = discord.Embed(
                title="📄 Ticket Summary",
                description=(summary_text or "").strip() or "(empty)",
                color=discord.Color.green(),
            )
            await channel.send(embed=embed)
            # Register the summary for clustering/FAQ suggestions
            await self._register_summary(self.ticket_id, (summary_text or "").strip())
        except Exception:
            # Non-fatal; do not block the close flow on summary issues
            pass

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

    async def _register_summary(self, ticket_id: int, summary: str) -> None:
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

                    channel = self.bot.get_channel(getattr(config, "WATCHER_LOG_CHANNEL", 0))
                    if channel and hasattr(channel, "send"):
                        text_channel = cast(discord.TextChannel, channel)
                        await text_channel.send(embed=embed, view=view)
                except Exception:
                    pass
        except Exception:
            # Do not block on summary registration failures
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
            if isinstance(child, discord.ui.Button) and child.custom_id == "ticket_delete_btn":
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
        if isinstance(interaction.channel, discord.TextChannel):
            await self._post_summary(interaction.channel)

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
        target_role_id = getattr(config, "TICKET_ESCALATION_ROLE_ID", None)
        escalated_to = int(target_role_id) if isinstance(target_role_id, int) else None
        await self.conn.execute(
            "UPDATE support_tickets SET status='escalated', escalated_to=$1, updated_at = NOW() WHERE id = $2",
            escalated_to,
            int(self.ticket_id),
        )
        await interaction.response.send_message("✅ Ticket escalated.", ephemeral=True)
        await self._log(interaction, "🚩 Ticket escalated", f"id={self.ticket_id} • to={escalated_to or '-'}")

    @discord.ui.button(label="🗑 Delete ticket", style=discord.ButtonStyle.secondary, custom_id="ticket_delete_btn", disabled=True)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Admin-only
        if not await self._is_staff(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        # Delete DB entries first
        try:
            await self.conn.execute("DELETE FROM ticket_summaries WHERE ticket_id = $1", int(self.ticket_id))
        except Exception:
            pass
        try:
            await self.conn.execute("DELETE FROM support_tickets WHERE id = $1", int(self.ticket_id))
        except Exception:
            pass
        # Delete channel
        try:
            ch = interaction.channel
            if isinstance(ch, discord.TextChannel):
                await interaction.followup.send("🗑 Deleting ticket channel...", ephemeral=True)
                await ch.delete(reason=f"Ticket {self.ticket_id} deleted by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Channel delete failed: {e}", ephemeral=True)
        # Log deletion
        await self._log(
            interaction,
            title="🗑 Ticket deleted",
            desc=(
                f"ID: {self.ticket_id}\n"
                f"Deleted by: {interaction.user} ({interaction.user.id})\n"
                f"Timestamp: {datetime.utcnow().isoformat()}"
            ),
            level="warning",
        )
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


