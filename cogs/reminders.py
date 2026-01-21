import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
from asyncpg import exceptions as pg_exceptions
import asyncio
from datetime import datetime, time as dtime
import config
from utils.timezone import BRUSSELS_TZ
import re
from datetime import timedelta
from utils.checks_interaction import is_owner_or_admin_interaction
from typing import Optional, List, Dict, Any, cast
from utils.settings_service import SettingsService
# from config import GUILD_ID  # Removed - no longer needed for multi-guild support
from cogs.embed_watcher import parse_embed_for_reminder
from utils.logger import logger, log_with_guild, log_guild_action, log_database_event

# All logging timestamps in this module use Brussels time for clarity.


class ReminderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None  # Use connection pool instead of single connection
        settings = getattr(bot, "settings", None)
        if settings is None or not hasattr(settings, 'get'):
            raise RuntimeError("SettingsService not available on bot instance")
        self.settings = settings  # type: ignore
        self.bot.loop.create_task(self.setup())

    async def setup(self) -> None:
        await self.bot.wait_until_ready()
        await self.bot.wait_until_ready()
        try:
            await self._connect_database()
        except Exception as e:
            log_database_event("DB_CONNECT_FAILED", details=f"Initial connection: {e}")
            logger.error(f"❌ Error connecting to database: {e}")
            return

        if not self.check_reminders.is_running():
            self.check_reminders.start()

    async def send_log_embed(self, title: str, description: str, level: str = "info", guild_id: int = 0) -> None:
        """Send log embed to the correct guild's log channel"""
        if guild_id == 0:
            # Fallback for legacy calls without guild_id
            logger.warning("⚠️ send_log_embed called without guild_id - skipping Discord log")
            return

        # Check log level filtering
        from utils.logger import should_log_to_discord
        if not should_log_to_discord(level, guild_id):
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
            from discord import Embed
            embed = Embed(title=title, description=description, color=color)
            embed.set_footer(text=f"reminders | Guild: {guild_id}")

            channel_id = self._get_log_channel_id(guild_id)
            if channel_id == 0:
                # No log channel configured for this guild
                log_with_guild(f"No log channel configured for reminders logging", guild_id, "debug")
                return

            channel = self.bot.get_channel(channel_id)
            if channel and hasattr(channel, "send"):
                text_channel = cast(discord.TextChannel, channel)
                await text_channel.send(embed=embed)
                log_guild_action(guild_id, "LOG_SENT", details=f"reminders: {title}")
            else:
                log_with_guild(f"Log channel {channel_id} not found or not accessible", guild_id, "warning")

        except Exception as e:
            log_with_guild(f"Could not send reminders log embed: {e}", guild_id, "error")

    async def _connect_database(self) -> None:
        try:
            pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=10)
            log_database_event("DB_CONNECTED", details="Reminders database pool created")
        except Exception as e:
            log_database_event("DB_CONNECT_ERROR", details=f"Failed to create pool: {e}")
            raise

        # Store the pool first
        if self.db:
            try:
                await self.db.close()
            except Exception:
                pass

        self.db = pool

        # Perform all setup operations in a single connection
        try:
            async with pool.acquire() as conn:
                # Create table
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reminders (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
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
                        last_sent_at TIMESTAMPTZ
                    );
                    """
                )
                # Add columns if they don't exist
                await conn.execute(
                    "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS call_time TIME;"
                )
                await conn.execute(
                    "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMPTZ;"
                )
                # Create indexes
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(time);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_event_time ON reminders(event_time);")
        except Exception as setup_e:
            log_database_event("DB_SETUP_ERROR", details=f"Failed to setup reminders table: {setup_e}")
            raise

        logger.info("✅ Connected to database pool!")
        log_database_event("DB_CONNECTION_ESTABLISHED", details="Reminders database pool ready")

    async def _ensure_connection(self) -> bool:
        if self.db and not self.db.is_closing():
            return True
        if self.db and self.db.is_closing():
            logger.debug("Reminder DB pool is closing, cannot ensure connection")
            return False
        try:
            await self._connect_database()
            return True
        except Exception as e:
            logger.error(f"❌ Reminder DB reconnect failed: {e}")
            return False

    async def _handle_connection_lost(self, error: Exception) -> None:
        logger.warning(f"⚠️ Reminder DB-verbinding verbroken: {error}")
        if self.db:
            try:
                await self.db.close()
            except Exception:
                pass
        self.db = None

    @app_commands.command(name="add_reminder", description="Schedule a recurring or one-off reminder via form or message link.")
    @app_commands.describe(
        name="Name of the reminder",
        channel="Channel where the reminder should be sent (optional if default is set)",
        time="Time in HH:MM format",
        days="Days of the week (e.g. mon,tue,wed)",
        message="The reminder message text",
        link="(Optional) Link to message with embed"
    )
    async def add_reminder(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: Optional[discord.TextChannel] = None,
        time: Optional[str] = None,
        days: Optional[str] = None,
        message: Optional[str] = None,
        link: Optional[str] = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("❌ Dit commando werkt alleen in een server.", ephemeral=True)
            return

        if not self._is_enabled(interaction.guild.id):
            await interaction.followup.send("⚠️ Reminders staan momenteel uit.", ephemeral=True)
            return

        if not await self._ensure_connection():
            await interaction.followup.send("⛔ Database not connected. Please try again later.", ephemeral=True)
            return

        origin_channel_id = origin_message_id = event_time = None
        debug_info: List[str] = []
        days_input: Optional[Any] = None

        # 👇 Als een embed-link is opgegeven: fetch en parse de embed
        if link:
            match = re.match(r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)", link)
            if not match:
                await interaction.followup.send("❌ Invalid message link provided.", ephemeral=True)
                return

            _, channel_id, message_id = map(int, match.groups())
            try:
                msg_channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                # Cast to TextChannel for type safety (fetch_message exists there)
                text_ch = cast(discord.TextChannel, msg_channel)
                msg = await text_ch.fetch_message(message_id)

                if not msg.embeds:
                    await interaction.followup.send("❌ No embed found in that message.", ephemeral=True)
                    return

                parsed = await parse_embed_for_reminder(msg.embeds[0])

                if not parsed:
                    await interaction.followup.send("❌ Error parsing embed.", ephemeral=True)
                    return

                if parsed.get("title"):
                    name = parsed["title"]
                    debug_info.append(f"📝 Title: `{name}`")

                if parsed.get("description") is not None:
                    desc_val = str(parsed.get("description") or "")
                    message = desc_val
                    debug_info.append(f"💬 Message: `{desc_val[:25]}...`" if len(desc_val) > 25 else f"💬 Message: `{desc_val}`")

                if parsed.get("reminder_time"):
                    time = parsed["reminder_time"].strftime("%H:%M")
                    event_time = parsed["datetime"].astimezone(BRUSSELS_TZ)
                    debug_info.append(f"⏰ Time: `{time}`")

                days_input = days
                if parsed.get("days") is not None:
                    days_input = parsed["days"]
                    days_for_debug = list(days_input) if isinstance(days_input, list) else [str(days_input)]
                    debug_info.append(f"📅 Day: `{', '.join(days_for_debug)}`")
                elif parsed.get("datetime"):
                    # Treat parsed embeds with a concrete date as one-off events
                    days_input = []
                    debug_info.append("📅 One-off event (no days set)")

                if parsed.get("location"):
                    debug_info.append(f"📍 Location: `{parsed['location']}`")

                origin_channel_id = str(channel_id)
                origin_message_id = str(message_id)

            except Exception as e:
                await interaction.followup.send(f"❌ Error parsing embed: `{e}`", ephemeral=True)
                return

        # ⏰ Tijd moet zeker bestaan
        if not time:
            await interaction.followup.send("❌ No time specified and no valid embed found.", ephemeral=True)
            return

        if channel is None:
            default_channel_id = self._get_default_channel_id(interaction.guild.id)
            if default_channel_id:
                resolved = self.bot.get_channel(default_channel_id)
                if resolved is None:
                    try:
                        resolved = await self.bot.fetch_channel(default_channel_id)
                    except Exception:
                        resolved = None
                if isinstance(resolved, discord.TextChannel):
                    channel = resolved
            if channel is None:
                await interaction.followup.send(
                    "❌ No channel specified and no default channel set for reminders.",
                    ephemeral=True,
                )
                return

        # ⏳ Parse time string naar datetime.time
        time_obj = datetime.strptime(time, "%H:%M").time()

        # Normaliseer days naar weekday nummers (0=maandag, 6=zondag)
        raw_days = days_input if days_input is not None else days

        if not raw_days:
            days_list: List[str] = []
        elif isinstance(raw_days, str):
            # comma- of spatiegescheiden invoer → lijst
            parts = re.split(r",\s*|\s+", raw_days.strip())
            days_list = [p.strip() for p in parts if p.strip()]
        else:
            days_list = [str(d) for d in raw_days]
        
        # Convert day abbreviations to weekday numbers
        day_map = {
            "ma": "0", "maandag": "0", "monday": "0",
            "di": "1", "dinsdag": "1", "tuesday": "1",
            "wo": "2", "woe": "2", "woensdag": "2", "wednesday": "2",
            "do": "3", "donderdag": "3", "thursday": "3",
            "vr": "4", "vrijdag": "4", "friday": "4",
            "za": "5", "zaterdag": "5", "saturday": "5",
            "zo": "6", "zondag": "6", "sunday": "6",
        }
        normalized_days = []
        for day in days_list:
            day_lower = day.lower().strip()
            if day_lower in day_map:
                normalized_days.append(day_map[day_lower])
            elif day_lower.isdigit() and 0 <= int(day_lower) <= 6:
                normalized_days.append(day_lower)
            else:
                # Try to match partial strings
                matched = False
                for key, value in day_map.items():
                    if key.startswith(day_lower) or day_lower.startswith(key):
                        normalized_days.append(value)
                        matched = True
                        break
                if not matched:
                    logger.warning(f"⚠️ Onbekende dag: {day}, wordt overgeslagen")
        days_list = list(set(normalized_days))  # Remove duplicates

        origin_channel_id = int(origin_channel_id) if origin_channel_id else None
        origin_message_id = int(origin_message_id) if origin_message_id else None
        created_by = int(interaction.user.id)
        channel_id = int(channel.id)

        # Bepaal call_time en time:
        # - time = reminder tijd (T-60, wanneer reminder wordt verzonden)
        # - call_time = event tijd (T0, de daadwerkelijke tijd van het event)
        if event_time:
            # One-off: time is al reminder tijd (T-60), call_time = event tijd (T0)
            call_time_obj = event_time.time()
            # time_obj is al de reminder tijd (berekend in embed_watcher of hieronder)
        else:
            # Recurring: gebruiker geeft event tijd in, reminder moet 1 uur eerder komen
            # Bereken reminder tijd (1 uur voor event)
            reminder_offset = self._get_reminder_offset(interaction.guild.id)
            event_dt = datetime.combine(datetime.now(BRUSSELS_TZ).date(), time_obj)
            reminder_dt = event_dt - timedelta(minutes=reminder_offset)
            reminder_time_obj = reminder_dt.time()
            call_time_obj = time_obj  # Event tijd (wat gebruiker instelt)
            time_obj = reminder_time_obj  # Reminder tijd (1 uur eerder)

        if not self.db:
            await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        async with self.db.acquire() as conn:
            await conn.execute(
            """INSERT INTO reminders (guild_id, name, channel_id, time, call_time, days, message, created_by, origin_channel_id, origin_message_id, event_time)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
               RETURNING id""",
            guild_id,
            name,
            channel_id,
            time_obj,  # reminder tijd (T-60) as time object
            call_time_obj,  # event tijd (T0) as time object
            days_list if days_list else [],
            message,
            created_by,
            origin_channel_id,
            origin_message_id,
            event_time
        )
            rid_row = await conn.fetchrow("SELECT currval(pg_get_serial_sequence('reminders','id')) AS id")
            rid = rid_row["id"] if rid_row else None
            logger.info(f"🟢 Reminder created (ID={rid}): {name} @ {time_obj} days={days_list} channel={channel_id}")
        await self.send_log_embed(
            title="🟢 Reminder created",
            description=(
                f"ID: `{rid}`\n"
                f"Name: **{name}**\n"
                f"Channel: <#{channel_id}>\n"
                f"Time: `{time_obj.strftime('%H:%M')}`\n"
                f"Call time: `{call_time_obj.strftime('%H:%M')}`\n"
                f"Days: `{', '.join(days_list) if days_list else '—'}`"
            ),
            level="success",
            guild_id=interaction.guild.id,
        )

        debug_str = "\n".join(debug_info) if debug_info else "ℹ️ No extra info extracted from embed."
        await interaction.followup.send(
            f"✅ Reminder **'{name}'** added to {channel.mention}.\n{debug_str}",
            ephemeral=True
        )

    @app_commands.command(name="reminder_list", description="📋 View your active reminders")
    async def reminder_list(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not self._is_enabled(interaction.guild.id):
            await interaction.followup.send("⚠️ Reminders staan momenteel uit.", ephemeral=True)
            return
        if not await self._ensure_connection():
            await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
            return
        if not self.db:
            await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
            return
        user_id = interaction.user.id
        channel_id = getattr(interaction.channel, "id", 0)

        is_admin = await is_owner_or_admin_interaction(interaction)

        guild_id = interaction.guild.id
        if is_admin:
            query = """
                SELECT id, name, time, call_time, days, event_time, location, message, channel_id
                FROM reminders 
                WHERE guild_id = $1 
                ORDER BY COALESCE(call_time, time) ASC, name ASC;
            """
            params: List[Any] = [guild_id]
        else:
            query = """
                SELECT id, name, time, call_time, days, event_time, location, message, channel_id
                FROM reminders
                WHERE guild_id = $1 AND (created_by = $2 OR channel_id = $3)
                ORDER BY COALESCE(call_time, time) ASC, name ASC;
            """
            params = [guild_id, user_id, channel_id]

        try:
            if not self.db:
                await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
                return
            async with self.db.acquire() as conn:
                rows = await conn.fetch(query, *params)
                logger.info(f"🔍 Fetched {len(rows)} reminders ({'admin' if is_admin else 'user'})")

                if not rows:
                    embed = discord.Embed(
                        title="📋 Active Reminders",
                        description="No reminders found.",
                        color=discord.Color.orange()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Helper function to format days
                def format_days(days_db: Any) -> str:
                    """Convert day numbers/abbreviations to readable day names."""
                    if not days_db:
                        return "One-off"
                    if isinstance(days_db, str):
                        days_list = [days_db]
                    else:
                        days_list = list(days_db)
                    
                    day_names = {
                        "0": "Monday", "1": "Tuesday", "2": "Wednesday", "3": "Thursday",
                        "4": "Friday", "5": "Saturday", "6": "Sunday"
                    }
                    
                    # Map abbreviations to numbers first
                    day_map = {
                        "ma": "0", "maandag": "0", "monday": "0",
                        "di": "1", "dinsdag": "1", "tuesday": "1",
                        "wo": "2", "woe": "2", "woensdag": "2", "wednesday": "2",
                        "do": "3", "donderdag": "3", "thursday": "3",
                        "vr": "4", "vrijdag": "4", "friday": "4",
                        "za": "5", "zaterdag": "5", "saturday": "5",
                        "zo": "6", "zondag": "6", "sunday": "6"
                    }
                    
                    formatted_days = []
                    for day in days_list:
                        day_lower = day.lower().strip()
                        # Try to map abbreviation to number
                        if day_lower in day_map:
                            day_num = day_map[day_lower]
                        elif day_lower.isdigit() and 0 <= int(day_lower) <= 6:
                            day_num = day_lower
                        else:
                            continue
                        
                        if day_num in day_names:
                            formatted_days.append(day_names[day_num])
                    
                    if formatted_days:
                        return ", ".join(formatted_days)
                    return "One-off"

                # Create embed
                embed = discord.Embed(
                    title="📋 Active Reminders",
                    description=f"Found **{len(rows)}** reminder{'s' if len(rows) != 1 else ''}",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(BRUSSELS_TZ)
                )

                # Group reminders by type for better organization
                recurring_reminders = []
                one_off_reminders = []
                
                for row in rows:
                    is_one_off = not row["days"] or len(row["days"]) == 0
                    if is_one_off:
                        one_off_reminders.append(row)
                    else:
                        recurring_reminders.append(row)
                
                # Add recurring reminders first
                if recurring_reminders:
                    recurring_text = []
                    for row in recurring_reminders[:10]:  # Limit to 10 per section
                        # Use call_time (event time) if available, otherwise time (reminder time)
                        display_time = row["call_time"] if row["call_time"] else row["time"]
                        time_str = display_time.strftime("%H:%M") if display_time else "—"
                        
                        days_str = format_days(row["days"])
                        location_str = f" • 📍 {row['location']}" if row.get("location") else ""
                        
                        # Get channel mention
                        channel = self.bot.get_channel(row["channel_id"]) if row.get("channel_id") else None
                        if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                            channel_str = f" in {channel.mention}"
                        else:
                            channel_str = f" (Channel ID: {row['channel_id']})"
                        
                        recurring_text.append(
                            f"**{row['name']}**\n"
                            f"⏰ {time_str} • 📅 {days_str}{location_str}\n"
                            f"📺 {channel_str} • ID: `{row['id']}`"
                        )
                    
                    if len(recurring_reminders) > 10:
                        recurring_text.append(f"\n*...and {len(recurring_reminders) - 10} more recurring reminders*")
                    
                    embed.add_field(
                        name=f"🔄 Recurring ({len(recurring_reminders)})",
                        value="\n\n".join(recurring_text) if recurring_text else "None",
                        inline=False
                    )
                
                # Add one-off reminders
                if one_off_reminders:
                    one_off_text = []
                    for row in one_off_reminders[:10]:  # Limit to 10 per section
                        # Use call_time (event time) if available, otherwise time (reminder time)
                        display_time = row["call_time"] if row["call_time"] else row["time"]
                        time_str = display_time.strftime("%H:%M") if display_time else "—"
                        
                        # Format event_time if available
                        event_info = ""
                        if row.get("event_time"):
                            event_dt = row["event_time"]
                            if isinstance(event_dt, datetime):
                                event_dt = event_dt.astimezone(BRUSSELS_TZ)
                                event_info = f" • 📅 {event_dt.strftime('%A, %B %d, %Y')}"
                        
                        location_str = f" • 📍 {row['location']}" if row.get("location") else ""
                        
                        # Get channel mention
                        channel = self.bot.get_channel(row["channel_id"]) if row.get("channel_id") else None
                        if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                            channel_str = f" in {channel.mention}"
                        else:
                            channel_str = f" (Channel ID: {row['channel_id']})"
                        
                        one_off_text.append(
                            f"**{row['name']}**\n"
                            f"⏰ {time_str}{event_info}{location_str}\n"
                            f"📺 {channel_str} • ID: `{row['id']}`"
                        )
                    
                    if len(one_off_reminders) > 10:
                        one_off_text.append(f"\n*...and {len(one_off_reminders) - 10} more one-off reminders*")
                    
                    embed.add_field(
                        name=f"📌 One-off ({len(one_off_reminders)})",
                        value="\n\n".join(one_off_text) if one_off_text else "None",
                        inline=False
                    )

                embed.set_footer(text=f"Use /reminder_edit <id> to edit or /reminder_delete <id> to delete")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception("Error fetching reminders")
            await interaction.followup.send(f"⚠️ Error fetching reminders: `{e}`")

    @app_commands.command(name="reminder_delete", description="🗑️ Delete a reminder by ID")
    @app_commands.describe(reminder_id="Het ID van de reminder die je wil verwijderen")
    async def reminder_delete(self, interaction: discord.Interaction, reminder_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("❌ Dit commando werkt alleen in een server.", ephemeral=True)
            return
        if not self._is_enabled(interaction.guild.id):
            await interaction.followup.send("⚠️ Reminders staan momenteel uit.", ephemeral=True)
            return
        if not await self._ensure_connection():
            await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
            return

        if not self.db:
            await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM reminders WHERE id = $1 AND guild_id = $2", reminder_id, guild_id)
            
            if not row:
                await interaction.followup.send(f"❌ Geen reminder gevonden met ID `{reminder_id}`.")
                return

            await conn.execute("DELETE FROM reminders WHERE id = $1 AND guild_id = $2", reminder_id, guild_id)
        await interaction.followup.send(
            f"🗑️ Reminder **{row['name']}** (ID: `{reminder_id}`) was successfully deleted."
        )
    
    @app_commands.command(name="reminder_edit", description="Edit an existing reminder")
    @app_commands.describe(reminder_id="The ID of the reminder to edit")
    async def reminder_edit(self, interaction: discord.Interaction, reminder_id: int) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
            return
        if not self._is_enabled(interaction.guild.id):
            await interaction.response.send_message("⚠️ Reminders are currently disabled.", ephemeral=True)
            return
        if not await self._ensure_connection():
            await interaction.response.send_message("⛔ Database not connected. Please try again later.", ephemeral=True)
            return

        if not self.db:
            await interaction.response.send_message("⛔ Database not connected.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id
        is_admin = await is_owner_or_admin_interaction(interaction)

        # Fetch reminder and check ownership
        async with self.db.acquire() as conn:
            if is_admin:
                row = await conn.fetchrow(
                    "SELECT * FROM reminders WHERE id = $1 AND guild_id = $2",
                    reminder_id, guild_id
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM reminders WHERE id = $1 AND guild_id = $2 AND created_by = $3",
                    reminder_id, guild_id, user_id
                )

        if not row:
            await interaction.response.send_message(
                f"❌ Reminder with ID `{reminder_id}` not found or you don't have permission to edit it.",
                ephemeral=True
            )
            return

        # Prepare current values for modal
        # Use call_time (event tijd, T0) for display, not time (reminder tijd, T-60)
        current_name = row["name"] or ""
        
        # Safely extract time as HH:MM string
        current_time = ""
        try:
            call_time_val = row.get("call_time")
            if call_time_val:
                # Handle both time objects and strings
                if hasattr(call_time_val, 'strftime'):
                    current_time = call_time_val.strftime("%H:%M")
                elif isinstance(call_time_val, str):
                    # If it's already a string, try to parse and reformat
                    try:
                        parsed = datetime.strptime(call_time_val, "%H:%M:%S").time()
                        current_time = parsed.strftime("%H:%M")
                    except ValueError:
                        try:
                            parsed = datetime.strptime(call_time_val, "%H:%M").time()
                            current_time = parsed.strftime("%H:%M")
                        except ValueError:
                            current_time = call_time_val[:5] if len(call_time_val) >= 5 else call_time_val
                else:
                    current_time = str(call_time_val)[:5]
            elif row.get("event_time"):
                event_time_val = row["event_time"]
                if hasattr(event_time_val, 'time'):
                    current_time = event_time_val.time().strftime("%H:%M")
                elif hasattr(event_time_val, 'strftime'):
                    current_time = event_time_val.strftime("%H:%M")
            elif row.get("time"):
                # Fallback: if no call_time, use time (but this shouldn't happen for new reminders)
                time_val = row["time"]
                if hasattr(time_val, 'strftime'):
                    current_time = time_val.strftime("%H:%M")
                elif isinstance(time_val, str):
                    current_time = time_val[:5] if len(time_val) >= 5 else time_val
        except Exception as e:
            logger.warning(f"⚠️ Error formatting time for edit modal: {e}")
            current_time = ""
        
        # Ensure current_time is max 5 characters (HH:MM format) and is a valid string
        if not isinstance(current_time, str):
            current_time = str(current_time)[:5] if current_time else ""
        if len(current_time) > 5:
            current_time = current_time[:5]
        
        # Safely format all values for modal
        # Ensure current_name is a valid string (max 100 chars for Discord)
        if not isinstance(current_name, str):
            current_name = str(current_name) if current_name else ""
        # Sanitize: Discord modals don't accept newlines in TextInput default values
        current_name = current_name.replace('\n', ' ').replace('\r', ' ').strip()
        current_name = ' '.join(current_name.split())  # Collapse multiple spaces
        current_name = current_name[:100] if len(current_name) > 100 else current_name
        
        # Ensure current_days is a valid string
        current_days = ", ".join(row["days"]) if row["days"] else ""
        if not isinstance(current_days, str):
            current_days = ", ".join(map(str, row["days"])) if row["days"] else ""
        current_days = current_days[:50] if len(current_days) > 50 else current_days
        
        # Ensure current_message is a valid string
        # Extract footer from message if present (footer was appended with \n\n separator)
        current_message = row["message"] or ""
        if not isinstance(current_message, str):
            current_message = str(current_message) if current_message else ""
        
        # Try to extract footer from message (footer is appended with \n\n)
        # Look for the pattern: message ends with \n\n followed by footer-like text
        current_footer = ""
        if current_message and "\n\n" in current_message:
            # Split by double newline - last part might be footer
            parts = current_message.rsplit("\n\n", 1)
            if len(parts) == 2:
                # Check if the last part looks like a footer (short text, possibly at end)
                potential_footer = parts[1].strip()
                # If it's relatively short (likely footer) and the message part exists
                if len(potential_footer) < 200 and parts[0].strip():
                    current_message = parts[0].strip()
                    current_footer = potential_footer
        
        current_message = current_message[:1000] if len(current_message) > 1000 else current_message
        current_footer = current_footer[:500] if len(current_footer) > 500 else current_footer
        
        # Ensure current_channel_id is an integer
        current_channel_id = row["channel_id"]
        if not isinstance(current_channel_id, int):
            try:
                current_channel_id = int(current_channel_id)
            except (ValueError, TypeError):
                logger.error(f"❌ Invalid channel_id type: {type(current_channel_id)}")
                await interaction.response.send_message("❌ Invalid reminder data (channel_id).", ephemeral=True)
                return
        
        # Show edit modal
        modal = EditReminderModal(
            reminder_id=reminder_id,
            current_name=current_name,
            current_time=current_time,
            current_days=current_days,
            current_message=current_message,
            current_channel_id=current_channel_id,
            cog=self,
            guild_id=guild_id,
            is_admin=is_admin
        )
        await interaction.response.send_modal(modal)

    @reminder_delete.autocomplete("reminder_id")
    async def reminder_id_autocomplete(self, interaction: discord.Interaction, current: str) -> List[discord.app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        if not self._is_enabled(interaction.guild.id):
            return []
        if not await self._ensure_connection():
            return []
        if not self.db:
            return []
        guild_id = interaction.guild.id
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT id, name FROM reminders WHERE guild_id = $1 ORDER BY id DESC LIMIT 25", guild_id)
        return [
            app_commands.Choice(name=f"ID {row['id']} – {row['name'][:30]}", value=row["id"])
            for row in rows if current.lower() in str(row["id"]) or current.lower() in row["name"].lower()
        ]

    @reminder_edit.autocomplete("reminder_id")
    async def reminder_edit_autocomplete(self, interaction: discord.Interaction, current: str) -> List[discord.app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        if not self._is_enabled(interaction.guild.id):
            return []
        if not await self._ensure_connection():
            return []
        if not self.db:
            return []
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        is_admin = await is_owner_or_admin_interaction(interaction)
        
        async with self.db.acquire() as conn:
            if is_admin:
                rows = await conn.fetch("SELECT id, name FROM reminders WHERE guild_id = $1 ORDER BY id DESC LIMIT 25", guild_id)
            else:
                rows = await conn.fetch(
                    "SELECT id, name FROM reminders WHERE guild_id = $1 AND created_by = $2 ORDER BY id DESC LIMIT 25",
                    guild_id, user_id
                )
            return [
                app_commands.Choice(name=f"ID {row['id']} – {row['name'][:30]}", value=row["id"])
                for row in rows if current.lower() in str(row["id"]) or current.lower() in row["name"].lower()
            ]

    def _get_log_channel_id(self, guild_id: int) -> int:
        if self.settings:
            try:
                return int(self.settings.get("system", "log_channel_id", guild_id))
            except KeyError:
                pass
        return 0  # Moet geconfigureerd worden via /config system set_log_channel

    def _is_enabled(self, guild_id: int) -> bool:
        if self.settings:
            try:
                return bool(self.settings.get("reminders", "enabled", guild_id))
            except KeyError:
                pass
        return True

    def _get_default_channel_id(self, guild_id: int) -> Optional[int]:
        if self.settings:
            try:
                value = self.settings.get("reminders", "default_channel_id", guild_id)
                if value:
                    return int(value)
            except KeyError:
                pass
            except (TypeError, ValueError):
                logger.warning("⚠️ Reminders: default_channel_id ongeldig in settings.")
        return None

    def _allow_everyone_mentions(self, guild_id: int) -> bool:
        if self.settings:
            try:
                return bool(self.settings.get("reminders", "allow_everyone_mentions", guild_id))
            except KeyError:
                pass
        return False  # Moet geconfigureerd worden via /config reminders allow_everyone_mentions

    def _get_reminder_offset(self, guild_id: int) -> int:
        """Get reminder offset in minutes (default: 60 = 1 hour before event)."""
        if self.settings:
            try:
                value = self.settings.get("embedwatcher", "reminder_offset_minutes", guild_id)
                if value is not None:
                    return int(value)
            except (KeyError, TypeError, ValueError):
                pass
        return 60  # Default: 1 hour before event

    @tasks.loop(seconds=60)
    async def check_reminders(self) -> None:
        if not await self._ensure_connection():
            logger.debug("⛔ Database connection not ready, skipping reminder check.")
            return

        if not self.db or self.db.is_closing():
            logger.debug("⛔ Database pool not available or closing, skipping reminder check.")
            return

        now = datetime.now(BRUSSELS_TZ).replace(second=0, microsecond=0)
        current_time_str = now.strftime("%H:%M:%S")
        current_time_hhmm = now.strftime("%H:%M")  # For TIME column comparison
        current_day = str(now.weekday())
        current_date = now.date()
        
        # Calculate next day for midnight edge case (reminder at 23:xx for next day event at 00:xx)
        # If reminder is at 23:xx, it's for an event the next day
        next_day = str((now.weekday() + 1) % 7)  # Wrap around: 7 becomes 0 (Monday)
        next_date = (now + timedelta(days=1)).date()

        try:
            async with self.db.acquire() as conn:
                # Build day matching: support both numeric ("0", "1", "2") and text ("ma", "di", "woe", etc.)
                day_abbrevs = {
                    "0": ["0", "ma", "maandag", "monday"],
                    "1": ["1", "di", "dinsdag", "tuesday"],
                    "2": ["2", "wo", "woe", "woensdag", "wednesday"],
                    "3": ["3", "do", "donderdag", "thursday"],
                    "4": ["4", "vr", "vrijdag", "friday"],
                    "5": ["5", "za", "zaterdag", "saturday"],
                    "6": ["6", "zo", "zondag", "sunday"],
                }
                current_day_variants = day_abbrevs.get(current_day, [current_day])
                next_day_variants = day_abbrevs.get(next_day, [next_day])
                
                # Check if any day variant matches the days array
                # time and call_time are TIME columns, so we compare them directly
                # Convert current_time_hhmm to TIME for comparison
                current_time_obj = datetime.strptime(current_time_hhmm, "%H:%M").time()
                
                # Check if current time is 23:xx (for midnight edge case)
                is_late_night = current_time_obj.hour == 23
                
                rows = await conn.fetch(
                """
                SELECT id, guild_id, channel_id, name, message, location,
                       origin_channel_id, origin_message_id, event_time, days, call_time,
                       last_sent_at
                FROM reminders
                WHERE (
                    -- One-off at T−60: reminder komt 1 uur voor event (time kolom = reminder tijd)
                    -- Handle midnight edge case: reminder at 23:xx for event at 00:xx next day
                    (
                        event_time IS NOT NULL
                        AND time::time = $1::time
                        AND (
                            -- Normal case: reminder and event on same calendar day
                            ((event_time AT TIME ZONE 'Europe/Brussels') - INTERVAL '60 minutes')::date = $2
                            OR
                            -- Midnight edge case: reminder at 23:xx, event at 00:xx next day
                            ($5 = true AND (event_time AT TIME ZONE 'Europe/Brussels')::date = $6)
                        )
                    )
                    OR
                    -- One-off at T0: event tijd (call_time kolom = event tijd)
                    (
                        event_time IS NOT NULL
                        AND call_time::time = $4::time
                        AND (event_time AT TIME ZONE 'Europe/Brussels')::date = $2
                    )
                    OR
                    -- Recurring by days: time kolom = reminder tijd (T-60), moet matchen op reminder tijd
                    -- Check if current_day or any variant matches days array
                    -- Also handle midnight edge case: if reminder is at 23:xx, check if next day matches
                    (
                        event_time IS NULL 
                        AND time::time = $1::time
                        AND (
                            -- Normal case: current day matches
                            (
                                $3 = ANY(days)  -- Direct numeric match
                                OR EXISTS (
                                    SELECT 1 FROM unnest(days) AS day_val
                                    WHERE day_val::text IN ('ma', 'maandag', 'monday', 'di', 'dinsdag', 'tuesday', 
                                                            'wo', 'woe', 'woensdag', 'wednesday', 'do', 'donderdag', 'thursday',
                                                            'vr', 'vrijdag', 'friday', 'za', 'zaterdag', 'saturday',
                                                            'zo', 'zondag', 'sunday')
                                    AND (
                                        ($3 = '0' AND day_val::text IN ('ma', 'maandag', 'monday'))
                                        OR ($3 = '1' AND day_val::text IN ('di', 'dinsdag', 'tuesday'))
                                        OR ($3 = '2' AND day_val::text IN ('wo', 'woe', 'woensdag', 'wednesday'))
                                        OR ($3 = '3' AND day_val::text IN ('do', 'donderdag', 'thursday'))
                                        OR ($3 = '4' AND day_val::text IN ('vr', 'vrijdag', 'friday'))
                                        OR ($3 = '5' AND day_val::text IN ('za', 'zaterdag', 'saturday'))
                                        OR ($3 = '6' AND day_val::text IN ('zo', 'zondag', 'sunday'))
                                    )
                                )
                            )
                            OR
                            -- Midnight edge case: reminder at 23:xx, check if next day matches
                            -- Example: reminder at Tuesday 23:xx is for Wednesday 00:xx event
                            (
                                $5 = true
                                AND (
                                    $7 = ANY(days)  -- Direct numeric match for next day
                                    OR EXISTS (
                                        SELECT 1 FROM unnest(days) AS day_val
                                        WHERE day_val::text IN ('ma', 'maandag', 'monday', 'di', 'dinsdag', 'tuesday', 
                                                                'wo', 'woe', 'woensdag', 'wednesday', 'do', 'donderdag', 'thursday',
                                                                'vr', 'vrijdag', 'friday', 'za', 'zaterdag', 'saturday',
                                                                'zo', 'zondag', 'sunday')
                                        AND (
                                            ($7 = '0' AND day_val::text IN ('ma', 'maandag', 'monday'))
                                            OR ($7 = '1' AND day_val::text IN ('di', 'dinsdag', 'tuesday'))
                                            OR ($7 = '2' AND day_val::text IN ('wo', 'woe', 'woensdag', 'wednesday'))
                                            OR ($7 = '3' AND day_val::text IN ('do', 'donderdag', 'thursday'))
                                            OR ($7 = '4' AND day_val::text IN ('vr', 'vrijdag', 'friday'))
                                            OR ($7 = '5' AND day_val::text IN ('za', 'zaterdag', 'saturday'))
                                            OR ($7 = '6' AND day_val::text IN ('zo', 'zondag', 'sunday'))
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
                """,
                current_time_obj, current_date, current_day, current_time_obj, is_late_night, next_date, next_day
            )
        except (pg_exceptions.InterfaceError, pg_exceptions.ConnectionDoesNotExistError, ConnectionResetError) as conn_err:
            await self._handle_connection_lost(conn_err)
            try:
                await self.send_log_embed(
                    title="🚨 Reminder loop error",
                    description=f"Database connection lost: {conn_err}",
                    level="error",
                )
            except Exception:
                pass
            return
        except Exception as e:
            logger.exception("🚨 Reminder loop error while fetching data")
            try:
                await self.send_log_embed(
                    title="🚨 Reminder loop error",
                    description=str(e),
                    level="error",
                )
            except Exception:
                pass
            return

        try:
            if len(rows) > 0:
                logger.info(f"🔎 Checking reminders at {current_time_str} - found {len(rows)} reminder(s) to process: {[r['id'] for r in rows]}")
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
                if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                    logger.warning(f"⚠️ Channel {row['channel_id']} not found for reminder {row['id']}.")
                    await self.send_log_embed(
                        title="⚠️ Reminder channel not found",
                        description=(
                            f"ID: `{row['id']}`\n"
                            f"Name: **{row['name']}**\n"
                            f"Channel ID: `{row['channel_id']}`\n"
                            f"Channel not found or deleted"
                        ),
                        level="warning",
                        guild_id=row["guild_id"],
                    )
                    continue

                from discord import Embed
                dt = now
                embed = Embed(
                    title=f"⏰ Reminder: {row['name']}",
                    description=row['message'] or "-",
                    color=0x2ecc71
                )
                # Show date+time for one-off events; for recurring show only the configured time
                event_dt = row.get("event_time")
                if event_dt:
                    try:
                        event_dt = event_dt.astimezone(BRUSSELS_TZ)
                    except Exception:
                        pass
                    call_time_obj = row.get("call_time") or event_dt.time()
                    embed.add_field(name="📅 Date", value=event_dt.strftime("%A %d %B %Y"), inline=False)
                    embed.add_field(name="⏰ Time", value=call_time_obj.strftime("%H:%M"), inline=False)
                else:
                    # Recurring: show only reminder time (no date)
                    call_time_obj = row.get("call_time") or row.get("time")
                    if call_time_obj:
                        try:
                            time_str = call_time_obj.strftime("%H:%M")
                        except Exception:
                            time_str = str(call_time_obj)
                        embed.add_field(name="⏰ Time", value=time_str, inline=False)
                # Locatie
                if row.get("location") and row["location"] != "-":
                    embed.add_field(name="📍 Location", value=row["location"], inline=False)
                # Link naar origineel bericht
                if row.get("origin_channel_id") and row.get("origin_message_id"):
                    link = f"https://discord.com/channels/{row['guild_id']}/{row['origin_channel_id']}/{row['origin_message_id']}"
                    embed.add_field(name="🔗 Original", value=f"[Click here]({link})", inline=False)

                text_channel = cast(discord.TextChannel, channel)
                mention_enabled = self._allow_everyone_mentions(row["guild_id"])
                content = "@everyone" if mention_enabled else None
                
                try:
                    await text_channel.send(
                        content=content,
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(everyone=mention_enabled)
                    )
                    logger.info(f"📤 Reminder sent (ID={row['id']}) to channel {row['channel_id']}: {row['name']}")
                    # Format date/time for log
                    date_str = event_dt.strftime('%Y-%m-%d') if event_dt else 'N/A'
                    time_str = call_time_obj.strftime('%H:%M') if call_time_obj else 'N/A'
                    
                    await self.send_log_embed(
                        title="📤 Reminder sent",
                        description=(
                            f"ID: `{row['id']}`\n"
                            f"Name: **{row['name']}**\n"
                            f"Channel: <#{row['channel_id']}>\n"
                            f"Date: {date_str}\n"
                            f"Time (display): `{time_str}`"
                        ),
                        level="info",
                        guild_id=row["guild_id"],
                    )
                    # Update idempotency marker only on success
                    try:
                        async with self.db.acquire() as update_conn:
                            await update_conn.execute(
                                "UPDATE reminders SET last_sent_at = $1 WHERE id = $2 AND guild_id = $3",
                                now,
                                row["id"],
                                row["guild_id"],
                            )
                    except Exception:
                        logger.exception("⚠️ Could not update last_sent_at")
                except discord.Forbidden:
                    logger.warning(f"⚠️ Reminder {row['id']} could not be sent: no permissions in channel {row['channel_id']}")
                    await self.send_log_embed(
                        title="⚠️ Reminder send failed",
                        description=(
                            f"ID: `{row['id']}`\n"
                            f"Name: **{row['name']}**\n"
                            f"Channel: <#{row['channel_id']}>\n"
                            f"Error: No permissions to send in this channel"
                        ),
                        level="error",
                        guild_id=row["guild_id"],
                    )
                except discord.NotFound:
                    logger.warning(f"⚠️ Reminder {row['id']} could not be sent: channel {row['channel_id']} not found")
                    await self.send_log_embed(
                        title="⚠️ Reminder send failed",
                        description=(
                            f"ID: `{row['id']}`\n"
                            f"Name: **{row['name']}**\n"
                            f"Channel: <#{row['channel_id']}>\n"
                            f"Error: Channel not found (possibly deleted)"
                        ),
                        level="error",
                        guild_id=row["guild_id"],
                    )
                except Exception as send_error:
                    logger.exception(f"❌ Reminder {row['id']} could not be sent: {send_error}")
                    await self.send_log_embed(
                        title="❌ Reminder send failed",
                        description=(
                            f"ID: `{row['id']}`\n"
                            f"Name: **{row['name']}**\n"
                            f"Channel: <#{row['channel_id']}>\n"
                            f"Error: {str(send_error)[:200]}"
                        ),
                        level="error",
                        guild_id=row["guild_id"],
                    )
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
                        async with self.db.acquire() as delete_conn:
                            await delete_conn.execute("DELETE FROM reminders WHERE id = $1 AND guild_id = $2", row["id"], row["guild_id"])
                        logger.info(f"🗑️ Reminder {row['id']} (one-off) deleted after T0 send.")
                        await self.send_log_embed(
                            title="🗑️ Reminder deleted (one-off)",
                            description=(
                                f"ID: `{row['id']}`\n"
                                f"Name: **{row['name']}**\n"
                                f"Channel: <#{row['channel_id']}>\n"
                                f"Deleted after T0 at {now.strftime('%Y-%m-%d %H:%M')}"
                            ),
                            level="warning",
                            guild_id=row["guild_id"],
                        )

        except Exception as e:
            if isinstance(e, (pg_exceptions.InterfaceError, pg_exceptions.ConnectionDoesNotExistError, ConnectionResetError)):
                await self._handle_connection_lost(e)
            logger.exception("🚨 Reminder loop error tijdens verzenden")
            try:
                await self.send_log_embed(
                    title="🚨 Reminder loop error",
                    description=str(e),
                    level="error",
                )
            except Exception:
                pass


# Voor extern gebruik via FastAPI
async def get_reminders_for_user(conn: asyncpg.Connection, user_id: str, guild_id: Optional[int] = None):
    """
    Get reminders for a specific user.
    
    Args:
        conn: Database connection
        user_id: Discord user ID
        guild_id: Optional guild ID to filter by (for multi-guild support)
    
    Returns:
        List of reminder records
    """
    if guild_id:
        query = (
            """
            SELECT id, name, time, call_time, days, event_time, message, channel_id, created_by, location
            FROM reminders
            WHERE guild_id = $1 AND created_by = $2
            ORDER BY COALESCE(call_time, time) ASC
            """
        )
        return await conn.fetch(query, guild_id, user_id)
    else:
        # Legacy: no guild filtering (for backwards compatibility)
        query = (
            """
            SELECT id, name, time, call_time, days, event_time, message, channel_id, created_by, location
            FROM reminders
            WHERE created_by = $1
            ORDER BY COALESCE(call_time, time) ASC
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


class EditReminderModal(discord.ui.Modal, title="Edit Reminder"):
    def __init__(
        self,
        reminder_id: int,
        current_name: str,
        current_time: str,
        current_days: str,
        current_message: str,
        current_channel_id: int,
        cog: ReminderCog,
        guild_id: int,
        is_admin: bool
    ):
        super().__init__()
        self.reminder_id = reminder_id
        self.cog = cog
        self.guild_id = guild_id
        self.is_admin = is_admin

        # Ensure current_name is not None and is a valid string
        if current_name is None:
            current_name = ""
        if not isinstance(current_name, str):
            current_name = str(current_name)
        # Sanitize: Discord modals don't accept newlines in TextInput default values
        current_name = current_name.replace('\n', ' ').replace('\r', ' ').strip()
        current_name = ' '.join(current_name.split())  # Collapse multiple spaces
        # Discord modal validation: ensure default is a valid string (max 100 chars)
        current_name = current_name[:100] if len(current_name) > 100 else current_name
        
        self.name_input = discord.ui.TextInput(
            label="Name",
            placeholder="Reminder name",
            default=current_name,
            max_length=100,
            required=True
        )
        # Ensure current_time is valid for Discord modal (max 5 chars, HH:MM format)
        # Discord requires default to be a string, not None
        if not current_time or len(current_time) > 5 or not isinstance(current_time, str):
            current_time = ""  # Empty string is acceptable if placeholder is provided
        self.time_input = discord.ui.TextInput(
            label="Time (HH:MM)",
            placeholder="e.g., 19:30",
            default=current_time,
            max_length=5,
            required=True
        )
        # Ensure all defaults are valid strings
        if current_days is None:
            current_days = ""
        if not isinstance(current_days, str):
            current_days = str(current_days)
        current_days = current_days[:50] if len(current_days) > 50 else current_days
        
        if current_message is None:
            current_message = ""
        if not isinstance(current_message, str):
            current_message = str(current_message)
        current_message = current_message[:1000] if len(current_message) > 1000 else current_message
        
        self.days_input = discord.ui.TextInput(
            label="Days (comma-separated)",
            placeholder="e.g., ma,di,wo or leave empty",
            default=current_days,
            max_length=50,
            required=False
        )
        self.message_input = discord.ui.TextInput(
            label="Message",
            placeholder="Reminder message",
            default=current_message,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.channel_input = discord.ui.TextInput(
            label="Channel ID (optional)",
            placeholder=f"Current: {current_channel_id}",
            default="",
            max_length=20,
            required=False
        )

        self.add_item(self.name_input)
        self.add_item(self.time_input)
        self.add_item(self.days_input)
        self.add_item(self.message_input)
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not await self.cog._ensure_connection():
            await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
            return

        if not self.cog.db:
            await interaction.followup.send("⛔ Database not connected.", ephemeral=True)
            return

        # Validate and parse time
        time_str = self.time_input.value.strip()
        try:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            await interaction.followup.send("❌ Invalid time format. Use HH:MM (e.g., 19:30).", ephemeral=True)
            return

        # Parse days and normalize to weekday numbers
        days_str = self.days_input.value.strip()
        if not days_str:
            days_list: List[str] = []
        else:
            parts = re.split(r",\s*|\s+", days_str)
            raw_days = [p.strip() for p in parts if p.strip()]
            
            # Convert day abbreviations to weekday numbers
            day_map = {
                "ma": "0", "maandag": "0", "monday": "0",
                "di": "1", "dinsdag": "1", "tuesday": "1",
                "wo": "2", "woe": "2", "woensdag": "2", "wednesday": "2",
                "do": "3", "donderdag": "3", "thursday": "3",
                "vr": "4", "vrijdag": "4", "friday": "4",
                "za": "5", "zaterdag": "5", "saturday": "5",
                "zo": "6", "zondag": "6", "sunday": "6",
            }
            normalized_days = []
            for day in raw_days:
                day_lower = day.lower().strip()
                if day_lower in day_map:
                    normalized_days.append(day_map[day_lower])
                elif day_lower.isdigit() and 0 <= int(day_lower) <= 6:
                    normalized_days.append(day_lower)
                else:
                    # Try to match partial strings
                    matched = False
                    for key, value in day_map.items():
                        if key.startswith(day_lower) or day_lower.startswith(key):
                            normalized_days.append(value)
                            matched = True
                            break
                    if not matched:
                        logger.warning(f"⚠️ Onbekende dag: {day}, wordt overgeslagen")
            days_list = list(set(normalized_days))  # Remove duplicates

        # Fetch current reminder to preserve event_time and call_time logic
        async with self.cog.db.acquire() as conn:
            current_row = await conn.fetchrow(
                "SELECT * FROM reminders WHERE id = $1 AND guild_id = $2",
                self.reminder_id, self.guild_id
            )
            if not current_row:
                await interaction.followup.send("❌ Reminder not found.", ephemeral=True)
                return

            # Parse channel (optional)
            channel_id = None
            channel_input_str = self.channel_input.value.strip()
            if channel_input_str:
                try:
                    channel_id = int(channel_input_str)
                    # Validate channel exists
                    channel = self.cog.bot.get_channel(channel_id)
                    if not channel:
                        try:
                            channel = await self.cog.bot.fetch_channel(channel_id)
                        except Exception:
                            await interaction.followup.send(f"❌ Channel with ID `{channel_id}` not found.", ephemeral=True)
                            return
                    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                        await interaction.followup.send("❌ Channel must be a text channel or thread.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send("❌ Invalid channel ID format.", ephemeral=True)
                    return
            else:
                # Use existing channel_id if not provided
                channel_id = current_row.get("channel_id")

            # Determine call_time and time:
            # - time = reminder tijd (T-60, wanneer reminder wordt verzonden)
            # - call_time = event tijd (T0, de daadwerkelijke tijd van het event)
            # - time_obj is wat de gebruiker heeft ingevuld (event tijd, T0)
            event_time = current_row.get("event_time")
            if event_time:
                # One-off: time_obj is event tijd (T0), time kolom moet reminder tijd (T-60) worden
                call_time_obj = time_obj  # Event tijd (wat gebruiker instelt)
                reminder_offset = self.cog._get_reminder_offset(self.guild_id)
                event_dt = datetime.combine(datetime.now(BRUSSELS_TZ).date(), time_obj)
                reminder_dt = event_dt - timedelta(minutes=reminder_offset)
                reminder_time_obj = reminder_dt.time()
                time_obj = reminder_time_obj  # Reminder tijd (T-60)
            else:
                # Recurring: gebruiker geeft event tijd in, reminder moet 1 uur eerder komen
                reminder_offset = self.cog._get_reminder_offset(self.guild_id)
                event_dt = datetime.combine(datetime.now(BRUSSELS_TZ).date(), time_obj)
                reminder_dt = event_dt - timedelta(minutes=reminder_offset)
                reminder_time_obj = reminder_dt.time()
                call_time_obj = time_obj  # Event tijd (wat gebruiker instelt)
                time_obj = reminder_time_obj  # Reminder tijd (1 uur eerder)

            # Get message value (footer remains in message if it was there originally)
            final_message = self.message_input.value.strip() if self.message_input.value else None
            
            # Update reminder (time and call_time are TIME columns, so we pass time objects)
            if channel_id:
                await conn.execute(
                """
                UPDATE reminders
                SET name = $1, time = $2, call_time = $3, days = $4, message = $5, channel_id = $6
                WHERE id = $7 AND guild_id = $8
                """,
                self.name_input.value.strip(),
                time_obj,  # reminder tijd (T-60) as time object
                call_time_obj,  # event tijd (T0) as time object
                days_list if days_list else [],
                final_message,
                    channel_id,
                    self.reminder_id,
                    self.guild_id
                )
            else:
                await conn.execute(
                """
                UPDATE reminders
                SET name = $1, time = $2, call_time = $3, days = $4, message = $5
                WHERE id = $6 AND guild_id = $7
                """,
                self.name_input.value.strip(),
                time_obj,  # reminder tijd (T-60) as time object
                call_time_obj,  # event tijd (T0) as time object
                days_list if days_list else [],
                    final_message,
                    self.reminder_id,
                    self.guild_id
                )

        # Log the edit
        await self.cog.send_log_embed(
            title="🟡 Reminder edited",
            description=(
                f"ID: `{self.reminder_id}`\n"
                f"Name: **{self.name_input.value.strip()}**\n"
                f"Time: `{time_str}`\n"
                f"Days: `{', '.join(days_list) if days_list else '—'}`\n"
                f"Edited by: {interaction.user.mention}"
            ),
            level="info",
            guild_id=self.guild_id,
        )

        await interaction.followup.send(
            f"✅ Reminder **{self.name_input.value.strip()}** (ID: `{self.reminder_id}`) has been updated.",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ReminderCog(bot))
