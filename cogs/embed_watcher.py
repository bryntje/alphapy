import discord
from discord import app_commands
from discord.ext import commands
import re
from datetime import datetime, timedelta
import config
import asyncpg
from zoneinfo import ZoneInfo

def extract_datetime_from_text(text):
    date_match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", text)
    time_match = re.search(r"(\d{1,2}[:.]\d{2})", text)
    current_year = datetime.now().year

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
            return dt
        except Exception as e:
            print(f"⛔️ Date parse failed: {e}")

    date_match = re.search(r"(\d{1,2})(st|nd|rd|th)?\s+([A-Z][a-z]+)", text)
    if date_match and time_match:
        day = int(date_match.group(1))
        month_str = date_match.group(3)
        time_str = time_match.group(1).replace(".", ":")
        try:
            dt = datetime.strptime(f"{day} {month_str} {current_year} {time_str}", "%d %B %Y %H:%M")
            return dt
        except Exception as e:
            print(f"⛔️ Date parse failed: {e}")

    return None

class EmbedReminderWatcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = None

    async def setup_db(self):
        self.conn = await asyncpg.connect(config.DATABASE_URL)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != config.ANNOUNCEMENTS_CHANNEL_ID or not message.embeds:
            print("[📣] Kanaal ID:", message.channel.id)
            return

        embed = message.embeds[0]
        # ⛔️ Skip reminders die de bot zelf al gepost heeft (om loops te vermijden)
        if embed.footer and embed.footer.text == "auto-reminder":
            print("[🔁] Embed genegeerd (auto-reminder tag gevonden)")
            return

        parsed = self.parse_embed_for_reminder(embed)
        print("[🐛] Parsed result:", parsed)
        print("[🐛] DB connection aanwezig?", self.conn is not None)


        if parsed and parsed["reminder_time"]:
            log_channel = self.bot.get_channel(config.WATCHER_LOG_CHANNEL)
            if log_channel:
                await log_channel.send(
                    f"🔔 Auto-reminder detected:\n"
                    f"📌 **{parsed['title']}**\n"
                    f"📅 {parsed['datetime'].strftime('%A %d %B %Y')} om {parsed['datetime'].strftime('%H:%M')}\n"
                    f"⏰ Reminder zal triggeren om {parsed['reminder_time'].strftime('%H:%M')}."
                    f" 📍 Locatie: {parsed.get('location') or '—'}"
                )
            else:
                print("⚠️  WATCHER_LOG_CHANNEL niet gevonden of niet toegankelijk.")


            if self.conn:
                await self.store_parsed_reminder(parsed, int(message.channel.id), int(message.author.id))

    def parse_embed_for_reminder(self, embed):
        all_text = embed.description or ""
        for field in embed.fields:
            all_text += f"\n{field.name}\n{field.value}"

        lines = all_text.split('\n')
        date_line, time_line, location_line, days_line = self.extract_fields_from_lines(lines)

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

            # Fallback: try to parse datetime from the description when
            # no explicit date/time fields were found.
            if not dt:
                dt = extract_datetime_from_text(embed.description or "")
                if dt:
                    tz = ZoneInfo("Europe/Brussels")

            # Fallback: attempt to extract location from the description if no
            # location field exists.
            if not location_line and embed.description:
                loc_match = re.search(r"(?:location|locatie)[:\s]*([^\n]+)", embed.description, re.IGNORECASE)
                if loc_match:
                    location_line = loc_match.group(1).strip()

            days_str = self.parse_days(days_line, dt)

            if not dt or not days_str:
                print(f"⚠️ Vereist: Geldige tijd én datum of dagen. Gevonden: tijd={time_line}, datum={date_line}, dagen={days_line}")
                return None
            return {
                "datetime": dt,
                "reminder_time": dt - timedelta(minutes=60),
                "location": location_line or "-",
                "title": embed.title or "-",
                "description": embed.description or "-",
                "days": days_str.split(",") if days_str else []
            }
        except Exception as e:
            print(f"❌ Parse error: {e}")
            return None

    def extract_fields_from_lines(self, lines):
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

    def parse_datetime(self, date_line, time_line):
        if not time_line:
            print(f"❌ Geen geldige tijd gevonden in regel: {time_line}")
            return None, None

        time_match = re.search(r"^.*?(\d{1,2})[:.](\d{2})(?:\s*(CET|CEST))?.*$", time_line)
        if not time_match:
            return None, None

        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        timezone_str = time_match.group(3) or "CET"

        tz = ZoneInfo("Europe/Brussels")

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
                    year = datetime.now().year
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
                year = int(year) if year else datetime.now().year
                try:
                    month = datetime.strptime(month_str[:3], "%b").month
                except ValueError:
                    month = datetime.strptime(month_str, "%B").month
            dt = datetime(year, month, day, hour, minute, tzinfo=tz)
        else:   
            now = datetime.now(tz)
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return dt, tz

    def parse_days(self, days_line, dt):
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
            found_days = []
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



    async def store_parsed_reminder(self, parsed, channel, created_by, origin_channel_id=None, origin_message_id=None):
        dt = parsed["datetime"]
        channel = int(channel)
        created_by = int(created_by)
        origin_channel_id = int(origin_channel_id) if origin_channel_id is not None else None
        origin_message_id = int(origin_message_id) if origin_message_id is not None else None
        reminder_dt = parsed["reminder_time"].replace(tzinfo=None)
        time_obj = reminder_dt.time()  # optioneel voor UI
        days_str = ",".join(parsed["days"])
        name = f"AutoReminder - {parsed['title'][:30]}"
        message = f"{parsed['title']}\n\n{parsed['description']}"
        location = parsed.get("location", "-")

        try:
            await self.conn.execute(
                """
                INSERT INTO reminders (
                    name, channel_id, days, message, created_by, 
                    location, origin_channel_id, origin_message_id, 
                    event_time, time
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                name,
                channel,
                days_str,
                message,
                created_by,
                location,
                origin_channel_id,
                origin_message_id,
                reminder_dt,
                time_obj
            )

            log_channel = self.bot.get_channel(config.WATCHER_LOG_CHANNEL)
            if log_channel:
                await log_channel.send(
                    f"✅ Reminder opgeslagen in DB voor: **{name}**\n"
                    f"🕒 Tijdstip: {time_obj.strftime('%H:%M')} op dag {days_str}\n"
                    f"📍 Locatie: {location or '—'}"
                )
            else:
                print("⚠️ Kon logkanaal niet vinden voor confirmatie.")

        except Exception as e:
            print(f"[ERROR] Reminder insert failed: {e}")

    @app_commands.command(name="debug_parse_embed", description="Parse de laatste embed in het kanaal voor test.")
    async def debug_parse_embed(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
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


def parse_embed_for_reminder(embed: discord.Embed):
    """Convenience wrapper to parse a reminder embed outside of the cog."""
    parser = EmbedReminderWatcher(None)
    return parser.parse_embed_for_reminder(embed)

async def setup(bot):
    cog = EmbedReminderWatcher(bot)
    await cog.setup_db()  # hier maak je je eigen verbinding
    await bot.add_cog(cog)
