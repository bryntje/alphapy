import discord
from discord.ext import commands
import re
from datetime import datetime, timedelta
import config
import asyncpg

def extract_datetime_from_text(text):
    date_match = re.search(r"(\d{1,2})(st|nd|rd|th)?\s+([A-Z][a-z]+)", text)
    time_match = re.search(r"(\d{1,2}[:.]\d{2})", text)

    if date_match and time_match:
        day = int(date_match.group(1))
        month_str = date_match.group(3)
        time_str = time_match.group(1).replace(".", ":")
        current_year = datetime.now().year

        try:
            full_date_str = f"{day} {month_str} {current_year} {time_str}"
            dt = datetime.strptime(full_date_str, "%d %B %Y %H:%M")
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
        ANNOUNCEMENTS_CHANNEL_ID = 1160511692824924216  # <-- pas aan!

        if message.channel.id != ANNOUNCEMENTS_CHANNEL_ID or not message.embeds:
            return

        embed = message.embeds[0]
        parsed = self.parse_embed_for_reminder(embed)

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
                await self.store_parsed_reminder(parsed, message.channel, message.author.id)

    def parse_embed_for_reminder(embed):
        date_line = None
        time_line = None
        location_line = None

        for field in embed.description.split('\n'):
            if "Date:" in field:
                date_line = field
            elif "Time:" in field:
                time_line = field
            elif "Location:" in field:
                location_line = field

        if not date_line or not time_line:
            return None  # noodzakelijke info ontbreekt

        # Date: Wednesday, 3rd April 2025
        date_match = re.search(r"(\d{1,2})(?:st|nd|rd|th)? ([A-Za-z]+)(?: (\d{4}))?", date_line)
        time_match = re.search(r"(\d{1,2}[:.]\d{2})", time_line)

        if not date_match or not time_match:
            return None

        day, month, year = date_match.groups()
        year = year or str(datetime.now().year)
        full_str = f"{day} {month} {year} {time_match.group(1).replace('.', ':')}"

        try:
            dt = datetime.strptime(full_str, "%d %B %Y %H:%M")
            return {
                "datetime": dt,
                "reminder_time": dt.replace(minute=max(0, dt.minute - 60)),  # vb: 30 min op voorhand
                "location": location_line.replace("Location:", "").strip() if location_line else None
            }
        except Exception as e:
            print(f"❌ Parse error: {e}")
            return None



    async def store_parsed_reminder(self, parsed, channel, created_by):
        dt = parsed["datetime"]
        time_obj = dt.time()
        weekday_str = str(dt.weekday())
        name = f"AutoReminder - {parsed['title'][:30]}"
        message = f"{parsed['title']}\n\n{parsed['description']}"
        location = parsed.get("location", "-")
        print("[DEBUG] Attempting to store reminder:", name)
        print("DB conn:", self.conn)

        try:
            await self.conn.execute(
                "INSERT INTO reminders (name, channel_id, time, days, message, created_by, location) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                name,
                str(channel.id),
                time_obj,
                [weekday_str],
                message,
                str(created_by),
                location
            )
            print("✅ Reminder opgeslagen in DB")

        except Exception as e:
            print(f"[ERROR] Reminder insert failed: {e}")



async def setup(bot):
    cog = EmbedReminderWatcher(bot)
    await cog.setup_db()  # hier maak je je eigen verbinding
    await bot.add_cog(cog)
