import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import asyncio
from datetime import datetime, time as dtime
import config
from utils.timezone import BRUSSELS_TZ
import re
from datetime import timedelta
from utils.checks_interaction import is_owner_or_admin_interaction
from typing import Optional, List, Dict, Any, cast
from config import GUILD_ID
from cogs.embed_watcher import parse_embed_for_reminder
from utils.logger import logger

# All logging timestamps in this module use Brussels time for clarity.


class ReminderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn: Optional[asyncpg.Connection] = None
        self.bot.loop.create_task(self.setup())

    async def setup(self) -> None:
        await self.bot.wait_until_ready()
        try:
            conn = await asyncpg.connect(config.DATABASE_URL)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    time TIME,
                    call_time TIME,
                    days TEXT[],
                    message TEXT,
                    created_by BIGINT,
                    origin_channel_id BIGINT,
                    origin_message_id BIGINT,
                    event_time TIMESTAMPTZ,
                    location TEXT,
                    last_sent_at TIMESTAMPTZ,
                    second_ping BOOLEAN DEFAULT FALSE
                );
                """
            )
            # Ensure call_time column is present for recurring reminders
            await conn.execute(
                "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS call_time TIME;"
            )
            # Idempotency timestamp
            await conn.execute(
                "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMPTZ;"
            )
            # Optional T0 support flag
            await conn.execute(
                "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS second_ping BOOLEAN DEFAULT FALSE;"
            )
            # Useful indexes for scheduler
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(time);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_reminder_date ON reminders(((event_time - INTERVAL '60 minutes')::date));"
            )
            self.conn = conn
            logger.info("✅ Verbonden met database!")
        except Exception as e:
            logger.error(f"❌ Fout bij verbinden met database: {e}")
        self.check_reminders.start()

    async def send_log_embed(self, title: str, description: str, level: str = "info") -> None:
        try:
            color_map = {
                "info": 0x3498db,
                "debug": 0x95a5a6,
                "error": 0xe74c3c,
                "success": 0x2ecc71,
                "warning": 0xf1c40f,
            }
            color = color_map.get(level, 0x3498db)
            from discord import Embed
            embed = Embed(title=title, description=description, color=color)
            embed.set_footer(text="reminders")
            channel = self.bot.get_channel(getattr(config, "WATCHER_LOG_CHANNEL", 0))
            if channel and hasattr(channel, "send"):
                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"⚠️ Kon log embed niet versturen: {e}")

    @app_commands.command(name="add_reminder", description="Plan een herhaalbare of eenmalige reminder in via formulier of berichtlink.")
    @app_commands.describe(
        name="Naam van de reminder",
        channel="Kanaal waar de reminder gestuurd moet worden",
        time="Tijdstip in HH:MM formaat",
        days="Dagen van de week (bv. ma,di,wo)",
        message="De remindertekst",
        link="(Optioneel) Link naar bericht met embed"
    )
    async def add_reminder(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: discord.TextChannel,
        time: Optional[str] = None,
        days: Optional[str] = None,
        message: Optional[str] = None,
        link: Optional[str] = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not self.conn:
            await interaction.followup.send("⛔ Database niet verbonden. Probeer later opnieuw.", ephemeral=True)
            return

        origin_channel_id = origin_message_id = event_time = None
        debug_info: List[str] = []

        # 👇 Als een embed-link is opgegeven: fetch en parse de embed
        if link:
            match = re.match(r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)", link)
            if not match:
                await interaction.followup.send("❌ Ongeldige berichtlink opgegeven.", ephemeral=True)
                return

            _, channel_id, message_id = map(int, match.groups())
            try:
                msg_channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                # Cast to TextChannel for type safety (fetch_message exists there)
                text_ch = cast(discord.TextChannel, msg_channel)
                msg = await text_ch.fetch_message(message_id)

                if not msg.embeds:
                    await interaction.followup.send("❌ Geen embed gevonden in dat bericht.", ephemeral=True)
                    return

                parsed = parse_embed_for_reminder(msg.embeds[0])

                if not parsed:
                    await interaction.followup.send("❌ Fout bij embed parsing.", ephemeral=True)
                    return

                if parsed.get("title"):
                    name = parsed["title"]
                    debug_info.append(f"📝 Titel: `{name}`")

                if parsed.get("description") is not None:
                    desc_val = str(parsed.get("description") or "")
                    message = desc_val
                    debug_info.append(f"💬 Bericht: `{desc_val[:25]}...`" if len(desc_val) > 25 else f"💬 Bericht: `{desc_val}`")

                if parsed.get("reminder_time"):
                    time = parsed["reminder_time"].strftime("%H:%M")
                    event_time = parsed["datetime"].astimezone(BRUSSELS_TZ)
                    debug_info.append(f"⏰ Tijd: `{time}`")

                days_input: Optional[Any] = days
                if parsed.get("days") is not None:
                    days_input = parsed["days"]
                    days_for_debug = list(days_input) if isinstance(days_input, list) else [str(days_input)]
                    debug_info.append(f"📅 Dag: `{', '.join(days_for_debug)}`")
                elif parsed.get("datetime"):
                    # Treat parsed embeds with a concrete date as one-off events
                    days_input = []
                    debug_info.append("📅 Eenmalig event (geen days ingesteld)")

                if parsed.get("location"):
                    debug_info.append(f"📍 Locatie: `{parsed['location']}`")

                origin_channel_id = str(channel_id)
                origin_message_id = str(message_id)

            except Exception as e:
                await interaction.followup.send(f"❌ Fout bij embed parsing: `{e}`", ephemeral=True)
                return

        # ⏰ Tijd moet zeker bestaan
        if not time:
            await interaction.followup.send("❌ Geen tijd opgegeven en geen geldige embed gevonden.", ephemeral=True)
            return

        # ⏳ Parse time string naar datetime.time
        time_obj = datetime.strptime(time, "%H:%M").time()

        # Normaliseer days
        if 'days_input' in locals() and days_input is not None:
            raw_days = days_input
        else:
            raw_days = days

        if not raw_days:
            days_list: List[str] = []
        elif isinstance(raw_days, str):
            # comma- of spatiegescheiden invoer → lijst
            parts = re.split(r",\s*|\s+", raw_days.strip())
            days_list = [p for p in parts if p]
        else:
            days_list = list(raw_days)

        origin_channel_id = int(origin_channel_id) if origin_channel_id else None
        origin_message_id = int(origin_message_id) if origin_message_id else None
        created_by = int(interaction.user.id)
        channel_id = int(channel.id)

        # Bepaal call_time: de daadwerkelijke event tijd of fallback naar time_obj
        call_time_obj = event_time.time() if event_time else time_obj

        await self.conn.execute(
            """INSERT INTO reminders (name, channel_id, time, call_time, days, message, created_by, origin_channel_id, origin_message_id, event_time)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               RETURNING id""",
            name,
            channel_id,
            time_obj,
            call_time_obj,
            days_list if days_list else [],
            message,
            created_by,
            origin_channel_id,
            origin_message_id,
            event_time
        )
        rid_row = await self.conn.fetchrow("SELECT currval(pg_get_serial_sequence('reminders','id')) AS id")
        rid = rid_row["id"] if rid_row else None
        logger.info(f"🟢 Reminder aangemaakt (ID={rid}): {name} @ {time_obj} days={days_list} channel={channel_id}")
        await self.send_log_embed(
            title="🟢 Reminder aangemaakt",
            description=(
                f"ID: `{rid}`\n"
                f"Naam: **{name}**\n"
                f"Kanaal: <#{channel_id}>\n"
                f"Tijd: `{time_obj.strftime('%H:%M')}`\n"
                f"Call time: `{call_time_obj.strftime('%H:%M')}`\n"
                f"Dagen: `{', '.join(days_list) if days_list else '—'}`"
            ),
            level="success",
        )

        debug_str = "\n".join(debug_info) if debug_info else "ℹ️ Geen extra info uit embed gehaald."
        await interaction.followup.send(
            f"✅ Reminder **'{name}'** toegevoegd in {channel.mention}.\n{debug_str}",
            ephemeral=True
        )

    @app_commands.command(name="reminder_list", description="📋 Bekijk je actieve reminders")
    async def reminder_list(self, interaction: discord.Interaction):
        if not self.conn:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("⛔ Database niet verbonden.", ephemeral=True)
            return
        user_id = interaction.user.id
        channel_id = getattr(interaction.channel, "id", 0)
        await interaction.response.defer(ephemeral=True)

        is_admin = await is_owner_or_admin_interaction(interaction)

        if is_admin:
            query = "SELECT id, name, time, days FROM reminders ORDER BY time;"
            params: List[Any] = []
        else:
            query = (
                """
                SELECT id, name, time, days FROM reminders
                WHERE created_by = $1 OR channel_id = $2
                ORDER BY time;
                """
            )
            params = [user_id, channel_id]

        try:
            rows = await self.conn.fetch(query, *params)
            logger.info(f"🔍 Fetched {len(rows)} reminders ({'admin' if is_admin else 'user'})")

            if not rows:
                await interaction.followup.send("❌ Geen reminders gevonden.")
                return

            msg_lines = [f"📋 **Actieve Reminders:**"]
            for row in rows:
                # Normalize days from DB
                days_db = row["days"]
                if not days_db:
                    days_list = []
                elif isinstance(days_db, str):
                    days_list = [days_db]
                else:
                    days_list = list(days_db)
                days_str = ", ".join(days_list)
                time_str = row["time"].strftime("%H:%M") if row["time"] else "⛔"
                msg_lines.append(
                    f"🔹 **{row['name']}** — ⏰ `{time_str}` op `{days_str}` (ID: `{row['id']}`)"
                )

            await interaction.followup.send("\n".join(msg_lines))
        except Exception as e:
            logger.exception("Fout bij ophalen reminders")
            await interaction.followup.send(f"⚠️ Fout bij ophalen reminders: `{e}`")

    @app_commands.command(name="reminder_delete", description="🗑️ Verwijder een reminder via ID")
    @app_commands.describe(reminder_id="Het ID van de reminder die je wil verwijderen")
    async def reminder_delete(self, interaction: discord.Interaction, reminder_id: int):
        if not self.conn:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("⛔ Database niet verbonden.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        row = await self.conn.fetchrow("SELECT * FROM reminders WHERE id = $1", reminder_id)
        
        if not row:
            await interaction.followup.send(f"❌ Geen reminder gevonden met ID `{reminder_id}`.")
            return

        await self.conn.execute("DELETE FROM reminders WHERE id = $1", reminder_id)
        await interaction.followup.send(
            f"🗑️ Reminder **{row['name']}** (ID: `{reminder_id}`) werd succesvol verwijderd."
        )
    
    @reminder_delete.autocomplete("reminder_id")
    async def reminder_id_autocomplete(self, interaction: discord.Interaction, current: str):
        if not self.conn:
            return []
        rows = await self.conn.fetch("SELECT id, name FROM reminders ORDER BY id DESC LIMIT 25")
        return [
            app_commands.Choice(name=f"ID {row['id']} – {row['name'][:30]}", value=row["id"])
            for row in rows if current.lower() in str(row["id"]) or current.lower() in row["name"].lower()
        ]

    @tasks.loop(seconds=60)
    async def check_reminders(self) -> None:
        if not self.conn:
            logger.warning("⛔ Database connection not ready.")
            return

        now = datetime.now(BRUSSELS_TZ).replace(second=0, microsecond=0)
        current_time_str = now.strftime("%H:%M:%S")
        current_day = str(now.weekday())
        current_date = now.date()

        logger.debug(f"🔁 Reminder check: {current_time_str} op dag {current_day}")

        try:
            rows = await self.conn.fetch(
                """
                SELECT id, channel_id, name, message, location,
                       origin_channel_id, origin_message_id, event_time, days, call_time,
                       last_sent_at, second_ping
                FROM reminders
                WHERE (
                    -- One-off at T−60
                    (event_time IS NOT NULL AND time::text = $1 AND (event_time - INTERVAL '60 minutes')::date = $2)
                    OR
                    -- One-off at T0 (always enabled if event_time is present)
                    (event_time IS NOT NULL AND (event_time::time)::text = $1)
                    OR
                    -- Recurring by days
                    (event_time IS NULL AND time::text = $1 AND ($3 = ANY(days)))
                )
                """,
                current_time_str, current_date , current_day
            )

            logger.debug(f"🔎 Matching reminders op {current_time_str} (rows={len(rows)})")
            for row in rows:
                # Idempotency guard: skip if already sent in this minute
                last_sent = row.get("last_sent_at")
                if last_sent is not None:
                    try:
                        last_sent_bxl = last_sent.astimezone(BRUSSELS_TZ)
                    except Exception:
                        last_sent_bxl = last_sent
                    if last_sent_bxl.replace(second=0, microsecond=0) == now:
                        logger.info(f"⏭️ Skip reminder {row['id']} (already sent this minute)")
                        continue

                channel = self.bot.get_channel(int(row["channel_id"]))
                if not channel or not hasattr(channel, "send"):
                    logger.warning(f"⚠️ Kanaal {row['channel_id']} niet gevonden.")
                    continue

                from discord import Embed
                dt = now
                embed = Embed(
                    title=f"⏰ Reminder: {row['name']}",
                    description=row['message'] or "-",
                    color=0x2ecc71
                )
                # Datum & Tijd
                event_dt = row.get("event_time")
                if not event_dt:
                    event_dt = dt
                else:
                    event_dt = event_dt.astimezone(BRUSSELS_TZ)
                call_time_obj = row.get("call_time") or event_dt.time()
                embed.add_field(name="📅 Date", value=event_dt.strftime("%A %d %B %Y"), inline=False)
                embed.add_field(name="⏰ Time", value=call_time_obj.strftime("%H:%M"), inline=False)
                # Locatie
                if row.get("location") and row["location"] != "-":
                    embed.add_field(name="📍 Location", value=row["location"], inline=False)
                # Link naar origineel bericht
                if row.get("origin_channel_id") and row.get("origin_message_id"):
                    link = f"https://discord.com/channels/{config.GUILD_ID}/{row['origin_channel_id']}/{row['origin_message_id']}"
                    embed.add_field(name="🔗 Origineel", value=f"[Klik hier]({link})", inline=False)

                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(
                    "@everyone",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(everyone=config.ENABLE_EVERYONE_MENTIONS)
                )
                logger.info(f"📤 Reminder verzonden (ID={row['id']}) naar kanaal {row['channel_id']}: {row['name']}")
                await self.send_log_embed(
                    title="📤 Reminder verzonden",
                    description=(
                        f"ID: `{row['id']}`\n"
                        f"Naam: **{row['name']}**\n"
                        f"Kanaal: <#{row['channel_id']}>\n"
                        f"Datum: {event_dt.strftime('%Y-%m-%d')}\n"
                        f"Tijd (weergave): `{call_time_obj.strftime('%H:%M')}`"
                    ),
                    level="info",
                )
                # Update idempotency marker
                try:
                    await self.conn.execute(
                        "UPDATE reminders SET last_sent_at = $1 WHERE id = $2",
                        now,
                        row["id"],
                    )
                except Exception:
                    logger.exception("⚠️ Kon last_sent_at niet updaten")
                # Eenmalige reminders verwijderen: enkel na T0 (niet na T−60)
                if row.get("event_time") and not row.get("days"):
                    # Determine if this send corresponds to T0
                    event_dt_for_delete = row.get("event_time")
                    is_t0_send = False
                    if event_dt_for_delete is not None:
                        try:
                            event_dt_for_delete = event_dt_for_delete.astimezone(BRUSSELS_TZ)
                        except Exception:
                            pass
                        event_time_str = event_dt_for_delete.strftime("%H:%M:%S")
                        is_t0_send = (event_time_str == current_time_str)
                    if is_t0_send:
                        await self.conn.execute("DELETE FROM reminders WHERE id = $1", row["id"])
                        logger.info(f"🗑️ Reminder {row['id']} (eenmalig) verwijderd na T0-verzenden.")
                        await self.send_log_embed(
                            title="🗑️ Reminder verwijderd (one-off)",
                            description=(
                                f"ID: `{row['id']}`\n"
                                f"Naam: **{row['name']}**\n"
                                f"Kanaal: <#{row['channel_id']}>\n"
                                f"Verwijderd na T0 op {now.strftime('%Y-%m-%d %H:%M')}"
                            ),
                            level="warning",
                        )

        except Exception as e:
            logger.exception("🚨 Reminder loop error")
            await self.send_log_embed(
                title="🚨 Reminder loop error",
                description=str(e),
                level="error",
            )


# Voor extern gebruik via FastAPI
async def get_reminders_for_user(conn: asyncpg.Connection, user_id: str):
    query = (
        """
        SELECT id, name, time, days, message, channel_id, created_by
        FROM reminders
        WHERE created_by = $1 OR created_by = '717695552669745152'
        ORDER BY time
        """
    )
    return await conn.fetch(query, user_id)


async def create_reminder(conn: asyncpg.Connection, data: Dict[str, Any]) -> None:
    days = data.get("days")
    if not days:
        days_list: List[str] = []
    elif isinstance(days, str):
        days_list = [days]
    else:
        days_list = list(days)
    await conn.execute(
        """
        INSERT INTO reminders (name, channel_id, time, days, message, created_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        data["name"],
        str(data["channel_id"]),
        data["time"],
        days_list,
        data["message"],
        data["created_by"]
    )


async def update_reminder(conn: asyncpg.Connection, data: Dict[str, Any]) -> None:
    days = data.get("days")
    if not days:
        days_list: List[str] = []
    elif isinstance(days, str):
        days_list = [days]
    else:
        days_list = list(days)
    await conn.execute(
        """
        UPDATE reminders
        SET name = $1, time = $2, days = $3, message = $4
        WHERE id = $5 AND created_by = $6
        """,
        data["name"],
        data["time"],
        days_list,
        data["message"],
        data["id"],
        data["created_by"]
    )


async def delete_reminder(conn: asyncpg.Connection, reminder_id: int, created_by: str) -> None:
    await conn.execute(
        "DELETE FROM reminders WHERE id = $1 AND created_by = $2",
        reminder_id,
        created_by
    )


async def setup(bot: commands.Bot):
    await bot.add_cog(ReminderCog(bot))
