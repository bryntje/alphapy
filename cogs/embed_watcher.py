import discord
from discord import app_commands
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
        print("[🐍] Message ontvangen:", message.content)
        ANNOUNCEMENTS_CHANNEL_ID = 1160511692824924216  # <-- pas aan!

        if message.channel.id != ANNOUNCEMENTS_CHANNEL_ID or not message.embeds:
            print("[📣] Kanaal ID:", message.channel.id)
            return

        embed = message.embeds[0]
        parsed = self.parse_embed_for_reminder(embed)
        print("[🔍] Parsed:", parsed)

        if parsed and parsed["reminder_time"]:
            log_channel = self.bot.get_channel(config.WATCHER_LOG_CHANNEL)
            print("[🪵] Log channel:", log_channel)
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

    def parse_embed_for_reminder(self, embed):
        import re
        from datetime import datetime, timedelta

        date_line = None
        time_line = None
        location_line = None

        # Eerst proberen uit embed.fields te halen
        all_text = embed.description or ""
        for field in embed.fields:
            all_text += f"\n{field.name}\n{field.value}"

        for line in all_text.split('\n'):
            if "date:" in line.lower():
                date_line = line
            elif "time:" in line.lower():
                time_line = line
            elif "location:" in line.lower():
                location_line = line

        # Als fields niet bestaan, fallback naar description (legacy)
        if not date_line or not time_line:
            for line in embed.description.split('\n'):
                if line.lower().startswith("date:"):
                    date_line = line.split(":", 1)[1].strip()
                elif line.lower().startswith("time:"):
                    time_line = line.split(":", 1)[1].strip()
                elif line.lower().startswith("location:"):
                    location_line = line.split(":", 1)[1].strip()

        if not date_line or not time_line:
            print("⚠️ Date of time niet gevonden in embed.")
            return None

        try:
            # Parse date & time
            date_match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?", date_line)
            time_match = re.search(r"(\d{1,2})[:.](\d{2})", time_line)

            if not date_match or not time_match:
                print("⚠️ Date of time match mislukt.")
                return None

            day, month_str, year = date_match.groups()
            day = int(day)
            year = int(year) if year else datetime.now().year

            # Maand converteren
            try:
                month = datetime.strptime(month_str[:3], "%b").month
            except ValueError:
                month = datetime.strptime(month_str, "%B").month

            hour = int(time_match.group(1))
            minute = int(time_match.group(2))

            dt = datetime(year, month, day, hour, minute)

            return {
                "datetime": dt,
                "reminder_time": dt - timedelta(minutes=30),  # 30 min op voorhand
                "location": location_line or "-"
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
            log_channel = self.bot.get_channel(config.WATCHER_LOG_CHANNEL)
            print("[🪵] Log channel:", log_channel)
            if log_channel:
                await log_channel.send(
                    f"✅ Reminder opgeslagen in DB voor: **{name}**\n"
                    f"🕒 Tijdstip: {time_obj.strftime('%H:%M')} op dag {weekday_str}\n"
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

async def setup(bot):
    cog = EmbedReminderWatcher(bot)
    await cog.setup_db()  # hier maak je je eigen verbinding
    await bot.add_cog(cog)
