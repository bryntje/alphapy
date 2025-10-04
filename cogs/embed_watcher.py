import discord
from discord import app_commands
from discord.ext import commands
import re
from datetime import datetime, timedelta
import config
import asyncpg
from typing import Optional, Tuple, List, cast
from utils.logger import logger
from utils.timezone import BRUSSELS_TZ


# All logging timestamps in this module use Brussels time for clarity.

def extract_datetime_from_text(text: str) -> Optional[datetime]:
    """Parse a free-text date/time, trying numeric and natural language formats."""
    # Try numeric date like 12/05/2025 or 12-05-25
    date_match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", text)
    time_match = re.search(r"(\d{1,2}[:.]\d{2})", text)
    current_year = datetime.now(BRUSSELS_TZ).year

    if date_match and time_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = date_match.group(3)
        if year:
            year = int(year) if len(year) == 4 else 2000 + int(year)
        else:
            year = current_year
        time_str = time_match.group(1).replace(".", ":")
        try:
            dt = datetime.strptime(f"{day}/{month}/{year} {time_str}", "%d/%m/%Y %H:%M")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BRUSSELS_TZ)
            return dt
        except Exception as e:
            logger.warning(f"⛔️ Date parse failed: {e}")

    # Try natural language date like 12th May
    date_match = re.search(r"(\d{1,2})(st|nd|rd|th)?\s+([A-Z][a-z]+)", text)
    if date_match and time_match:
        day = int(date_match.group(1))
        month_str = date_match.group(3)
        time_str = time_match.group(1).replace(".", ":")
        try:
            dt = datetime.strptime(f"{day} {month_str} {current_year} {time_str}", "%d %B %Y %H:%M")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BRUSSELS_TZ)
            return dt
        except Exception as e:
            logger.warning(f"⛔️ Date parse failed: {e}")
    return None


class EmbedReminderWatcher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn: Optional[asyncpg.Connection] = None
        self.settings = getattr(bot, "settings", None)

    async def setup_db(self) -> None:
        self.conn = await asyncpg.connect(config.DATABASE_URL)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == getattr(self.bot.user, 'id', None):
            return  # Skip messages from the bot itself
        announcements_channel_id = self._get_announcements_channel_id()
        if message.channel.id != announcements_channel_id or not message.embeds:
            logger.debug(f"[📣] Kanal ID: {message.channel.id} - embeds: {bool(message.embeds)}")
            return

        embed = message.embeds[0]
        # ⛔️ Skip reminders die de bot zelf al gepost heeft (om loops te vermijden)
        if embed.footer and embed.footer.text == "auto-reminder":
            logger.debug("[🔁] Embed genegeerd (auto-reminder tag gevonden)")
            return

        parsed = self.parse_embed_for_reminder(embed)
        logger.debug(f"[🐛] Parsed result: {parsed}")
        logger.debug(f"[🐛] DB connection aanwezig? {self.conn is not None}")

        if parsed and parsed["reminder_time"]:
            log_channel_id = self._get_log_channel_id()
            log_channel = self.bot.get_channel(log_channel_id)
            if isinstance(log_channel, (discord.TextChannel, discord.Thread)):
                await log_channel.send(
                    f"🔔 Auto-reminder detected:\n"
                    f"📌 **{parsed['title']}**\n"
                    f"📅 {parsed['datetime'].strftime('%A %d %B %Y')} om {parsed['datetime'].strftime('%H:%M')}\n"
                    f"⏰ Reminder zal triggeren om {parsed['reminder_time'].strftime('%H:%M')}."
                    f" 📍 Locatie: {parsed.get('location') or '—'}"
                )
            else:
                logger.warning("⚠️  Logkanaal niet gevonden of niet toegankelijk.")

            if self.conn:
                await self.store_parsed_reminder(parsed, int(message.channel.id), int(message.author.id))

    def parse_embed_for_reminder(self, embed: discord.Embed) -> Optional[dict]:
        all_text = embed.description or ""
        for field in embed.fields:
            all_text += f"\n{field.name}\n{field.value}"

        lines = all_text.split('\n')
        date_line, time_line, location_line, days_line = self.extract_fields_from_lines(lines)

        # Fallback: if the "Time" line includes a concrete date, extract it so
        # one-off messages such as "Wednesday, October 01/10/25 – 19:30" are
        # recognised as dated events instead of recurring reminders.
        inferred_date = None
        if not date_line and time_line:
            inferred_date = self.infer_date_from_time_line(time_line)
            if inferred_date:
                date_line = inferred_date

        # Fallbacks for time and days if not present in structured lines
        if not time_line:
            time_fallback = re.search(r"\b(\d{1,2}[:.]\d{2})\s*(?:CET|CEST)?", embed.description or "")
            if not time_fallback:
                time_fallback = re.search(r"\b(\d{1,2}[:.]\d{2})\s*(?:CET|CEST)?", all_text)
            if time_fallback:
                time_line = time_fallback.group(0)

        if not days_line and embed.description:
            day_fallback = re.search(r"\b(?:every|elke)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", embed.description, re.IGNORECASE)
            if day_fallback:
                days_line = day_fallback.group(1)

        try:
            dt, tz = self.parse_datetime(date_line, time_line)

            # Track whether we found a concrete calendar date
            had_explicit_date = bool(date_line)
            dt_from_description = False

            # Fallback: try to parse datetime from the description when
            # no explicit date/time fields were found.
            if not dt:
                parsed_from_description = extract_datetime_from_text(embed.description or "")
                if parsed_from_description:
                    dt = parsed_from_description
                    tz = BRUSSELS_TZ
                    dt_from_description = True

            # Fallback: attempt to extract location from the description if no
            # location field exists.
            if not location_line and embed.description:
                loc_match = re.search(r"(?:location|locatie)[:\s]*([^\n]+)", embed.description, re.IGNORECASE)
                if loc_match:
                    location_line = loc_match.group(1).strip()

            if not dt:
                logger.warning("⚠️ Geen geldige datum gevonden en geen tijd/datum in description. Reminder wordt niet gemaakt.")
                return None

            offset_minutes = self._get_reminder_offset()
            reminder_time = dt - timedelta(minutes=offset_minutes)

            # Decide recurrence: only use parse_days when explicitly provided.
            # If we have a concrete date (explicit date or parsed from description),
            # treat it as a one-off (days = []). Otherwise, require explicit days.
            if days_line:
                days_str = self.parse_days(days_line, reminder_time)
                days_list = days_str.split(",") if days_str else []
            else:
                if had_explicit_date or dt_from_description:
                    days_list = []  # one-off event
                else:
                    logger.warning("⚠️ Geen datum en geen dagen opgegeven → geen reminder aangemaakt.")
                    return None

            # Log the parsed datetime and days list for debugging purposes.
            print(
                f"🕑 Parsed datetime: {dt.astimezone(BRUSSELS_TZ)} "
                f"(weekday {dt.weekday()}) → days {days_list}"
            )

            # At this point we have a valid datetime; days_list may be empty for one-off
            return {
                "datetime": dt,
                "reminder_time": reminder_time,
                "location": location_line or "-",
                "title": embed.title or "-",
                "description": embed.description or "-",
                "days": days_list,
            }
        except Exception as e:
            logger.exception(f"❌ Parse error: {e}")
            return None

    def extract_fields_from_lines(self, lines: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        date_line = time_line = location_line = days_line = None
        for line in lines:
            lower = line.lower()
            if "date:" in lower:
                date_line = line.split(":", 1)[1].strip()
            elif "time:" in lower:
                time_line = line.split(":", 1)[1].strip()
            elif "location:" in lower or "locatie:" in lower:
                location_line = line.split(":", 1)[1].strip()
            elif "days:" in lower:
                days_line = line.split(":", 1)[1].strip()
        return date_line, time_line, location_line, days_line

    def parse_datetime(self, date_line: Optional[str], time_line: Optional[str]) -> Tuple[Optional[datetime], Optional[object]]:
        if not time_line:
            logger.warning(f"❌ Geen geldige tijd gevonden in regel: {time_line}")
            return None, None

        time_match = re.search(r"^.*?(\d{1,2})[:.](\d{2})(?:\s*(CET|CEST))?.*$", time_line)
        if not time_match:
            return None, None

        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        _timezone_str = time_match.group(3) or "CET"

        tz = BRUSSELS_TZ

        if date_line:
            date_line = date_line.strip()
            numeric = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", date_line)
            if numeric:
                day = int(numeric.group(1))
                month = int(numeric.group(2))
                year = numeric.group(3)
                if year:
                    year = int(year) if len(year) == 4 else 2000 + int(year)
                else:
                    year = datetime.now(BRUSSELS_TZ).year
            else:
                date_match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?", date_line)
                if not date_match:
                    alt_match = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", date_line)
                    if not alt_match:
                        return None, None
                    month_str, day, year = alt_match.groups()
                else:
                    day, month_str, year = date_match.groups()
                day = int(day)
                year = int(year) if year else datetime.now(BRUSSELS_TZ).year
                try:
                    month = datetime.strptime(month_str[:3], "%b").month
                except ValueError:
                    month = datetime.strptime(month_str, "%B").month
            dt = datetime(year, month, day, hour, minute, tzinfo=tz)
        else:   
            now = datetime.now(BRUSSELS_TZ)
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return dt, tz

    def infer_date_from_time_line(self, time_line: str) -> Optional[str]:
        numeric = re.search(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", time_line)
        if numeric:
            return numeric.group(1)

        month_day = re.search(
            r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:[,\s]+(\d{4}))?",
            time_line
        )
        if month_day:
            month, day, year = month_day.groups()
            parts = [day, month]
            if year:
                parts.append(year)
            return " ".join(parts)

        day_month = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:[,\s]+(\d{4}))?",
            time_line
        )
        if day_month:
            day, month, year = day_month.groups()
            parts = [day, month]
            if year:
                parts.append(year)
            return " ".join(parts)

        return None

    def parse_days(self, days_line: Optional[str], dt: datetime) -> str:
        if not days_line:
            return str(dt.weekday())

        days_val = days_line.lower()
        days_val = re.sub(r"daily\s*:\s*", "", days_val).strip()

        if any(word in days_val for word in ["daily", "dagelijks"]):
            return "0,1,2,3,4,5,6"
        elif "weekdays" in days_val:
            return "0,1,2,3,4"
        elif "weekends" in days_val:
            return "5,6"
        else:
            day_map = {
                "monday": "0", "maandag": "0",
                "tuesday": "1", "dinsdag": "1",
                "wednesday": "2", "woensdag": "2",
                "thursday": "3", "donderdag": "3",
                "friday": "4", "vrijdag": "4",
                "saturday": "5", "zaterdag": "5",
                "sunday": "6", "zondag": "6"
            }
            found_days: List[str] = []
            for word in re.split(r",\s*|\s+", days_val):
                word = word.strip().lower()
                word = re.sub(r"[^\w]", "", word)
                if word in day_map:
                    found_days.append(day_map[word])
            print(f"🔍 Check woord: '{word}' → match? {word in day_map}")
            print(f"✅ Found days list: {found_days}")
            if found_days:
                return ",".join(sorted(set(found_days)))
        # fallback to the weekday of the provided datetime
        print(f"⚠️ Fallback triggered in parse_days — geen geldige days_line: '{days_line}' → weekday van dt: {dt.strftime('%A')} ({dt.weekday()})")
        return str(dt.weekday())

    async def store_parsed_reminder(self, parsed: dict, channel: int, created_by: int, origin_channel_id: Optional[int]=None, origin_message_id: Optional[int]=None) -> None:
        dt = parsed["datetime"]
        channel = int(channel)
        created_by = int(created_by)
        origin_channel_id = int(origin_channel_id) if origin_channel_id is not None else None
        origin_message_id = int(origin_message_id) if origin_message_id is not None else None
        reminder_dt = parsed["reminder_time"].astimezone(BRUSSELS_TZ)
        event_dt = parsed["datetime"].astimezone(BRUSSELS_TZ)
        trigger_time = reminder_dt.time()
        call_time_obj = event_dt.time()
        days_arr = parsed["days"]
        if isinstance(days_arr, str):
            days_arr = [d.strip() for d in days_arr.split(",") if d.strip()]
        print(f"[DEBUG] Final days_arr voor DB-insert: {days_arr} ({type(days_arr)})")
        name = f"AutoReminder - {parsed['title'][:30]}"
        message = f"{parsed['title']}\n\n{parsed['description']}"
        location = parsed.get("location", "-")

        try:
            if not self.conn:
                raise RuntimeError("Databaseverbinding niet beschikbaar voor store_parsed_reminder")
            await self.conn.execute(
                """
                INSERT INTO reminders (
                    name, channel_id, days, message, created_by, 
                    location, origin_channel_id, origin_message_id, 
                    event_time, time, call_time
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                name,
                channel,
                days_arr,  # geef als array door
                message,
                created_by,
                location,
                origin_channel_id,
                origin_message_id,
                event_dt,
                trigger_time,
                call_time_obj
            )

            log_channel_id = self._get_log_channel_id()
            log_channel = self.bot.get_channel(log_channel_id)
            logger.debug(f"[🪵] Log channel: {log_channel}")
            if isinstance(log_channel, (discord.TextChannel, discord.Thread)):
                await log_channel.send(
                    f"✅ Reminder opgeslagen in DB voor: **{name}**\n"
                    f"🕒 Tijdstip: {trigger_time.strftime('%H:%M')} op dag {','.join(days_arr)}\n"
                    f"📍 Locatie: {location or '—'}"
                )
            else:
                logger.warning("⚠️ Kon logkanaal niet vinden voor confirmatie.")

        except Exception as e:
            logger.exception(f"[ERROR] Reminder insert failed: {e}")

    @app_commands.command(name="debug_parse_embed", description="Parse de laatste embed in het kanaal voor test.")
    async def debug_parse_embed(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send("⚠️ Dit commando werkt enkel in tekstkanalen.")
            return
        messages = [m async for m in interaction.channel.history(limit=10)]

        for msg in messages:
            if msg.embeds:
                embed = msg.embeds[0]
                parsed = self.parse_embed_for_reminder(embed)
                if parsed:
                    response = (
                        f"🧠 **Parsed data:**\n"
                        f"📅 Datum: `{parsed['datetime']}`\n"
                        f"⏰ Reminder Time: `{parsed['reminder_time']}`\n"
                        f"📍 Locatie: `{parsed.get('location', '-')}`"
                    )
                    await interaction.followup.send(response)
                else:
                    await interaction.followup.send("❌ Kon embed niet parsen.")
                return

        await interaction.followup.send("⚠️ Geen embed gevonden in de laatste 10 berichten.")


    def _get_announcements_channel_id(self) -> int:
        if self.settings:
            try:
                return int(self.settings.get("embedwatcher", "announcements_channel_id"))
            except KeyError:
                pass
        return getattr(config, "ANNOUNCEMENTS_CHANNEL_ID", 0)

    def _get_log_channel_id(self) -> int:
        if self.settings:
            try:
                return int(self.settings.get("system", "log_channel_id"))
            except KeyError:
                pass
        return getattr(config, "WATCHER_LOG_CHANNEL", 0)

    def _get_reminder_offset(self) -> int:
        if self.settings:
            try:
                return int(self.settings.get("embedwatcher", "reminder_offset_minutes"))
            except KeyError:
                pass
        return 60


def parse_embed_for_reminder(embed: discord.Embed):
    """Convenience wrapper to parse a reminder embed outside of the cog."""
    parser = EmbedReminderWatcher(cast(commands.Bot, None))
    return parser.parse_embed_for_reminder(embed)

async def setup(bot):
    cog = EmbedReminderWatcher(bot)
    await cog.setup_db()  # hier maak je je eigen verbinding
    await bot.add_cog(cog)
