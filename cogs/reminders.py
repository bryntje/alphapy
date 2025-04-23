import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import asyncio
from datetime import datetime, time as dtime
import config
import pytz
import re
from datetime import timedelta


class ReminderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn: asyncpg.Connection = None
        self.bot.loop.create_task(self.setup())

    async def setup(self):
        await self.bot.wait_until_ready()
        try:
            self.conn = await asyncpg.connect(config.DATABASE_URL)
            print("✅ Verbonden met database!")
        except Exception as e:
            print("❌ Fout bij verbinden met database:", e)
        self.check_reminders.start()

    @app_commands.command(name="add_reminder", description="Plan een herhaalbare reminder in.")
    @app_commands.describe(
        name="Naam van de reminder",
        channel="Kanaal waar de reminder gestuurd moet worden",
        time="Tijdstip in HH:MM formaat",
        days="Dagen van de week (bv. ma,di,wo)",
        message="De remindertekst"
    )
    async def add_reminder(self, interaction: discord.Interaction, name: str, channel: discord.TextChannel, time: str, days: str, message: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        print("Database connection:", self.conn)
        if not self.conn:
            await interaction.followup.send("⛔ Database not connected. Try again later.", ephemeral=True)
            return
        # Convert string to datetime.time object
        time_obj = datetime.strptime(time, "%H:%M").time()

        await self.conn.execute(
            "INSERT INTO reminders (name, channel_id, time, days, message, created_by) VALUES ($1, $2, $3, $4, $5, $6)",
            name, str(channel.id), time_obj, days.split(","), message, str(interaction.user.id)
        )
        await interaction.followup.send(f"✅ Reminder '{name}' toegevoegd in {channel.mention} om {time} op {days}.", ephemeral=True)

    @tasks.loop(seconds=60)
    async def check_reminders(self):
        if not self.conn:
            print("⛔ Database connection not ready.")
            return

        # Mapping van NL naar EN dagafkortingen
        day_map = {
            "Mon": "ma", "Tue": "di", "Wed": "wo",
            "Thu": "do", "Fri": "vr", "Sat": "za", "Sun": "zo"
        }

        tz = pytz.timezone("Europe/Brussels")
        now = datetime.now(tz)
        current_time = now.time().replace(second=0, microsecond=0)
        current_day = day_map[now.strftime("%a")]


        query = """
            SELECT id, channel_id, name, message
            FROM reminders
            WHERE time = $1 AND $2 = ANY(days)
        """

        try:
            print(f"⏱️ Current time: {current_time}, Current day: {current_day}")
            print(f"🧠 Query: {query}")
            rows = await self.conn.fetch(query, current_time, current_day)
            print(f"📦 Fetched reminders: {rows}")
            for row in rows:
                channel = self.bot.get_channel(int(row["channel_id"]))
                if channel:
                    await channel.send(f"⏰ Reminder **{row['name']}**: {row['message']}")
                # (Optioneel) verwijder reminder of update status
                # await self.conn.execute("DELETE FROM reminders WHERE id = $1", row["id"])
        except Exception as e:
            print("🚨 Reminder loop error:", e)

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        ANNOUNCEMENTS_CHANNEL_ID = 1160511692824924216  # <<< vervang door jouw kanaal-ID

        if message.channel.id != ANNOUNCEMENTS_CHANNEL_ID:
            return

        if not message.embeds:
            return

        embed = message.embeds[0]
        parsed = self.parse_embed_for_reminder(embed)

        if parsed and parsed["reminder_time"]:
            await message.channel.send(
                f"⏰ Auto-reminder gevonden!\n"
                f"📌 **{parsed['title']}**\n"
                f"🗓️ {parsed['datetime'].strftime('%A %d %B %Y')} om {parsed['datetime'].strftime('%H:%M')}\n"
                f"🔔 Reminder wordt geplaatst om {parsed['reminder_time'].strftime('%H:%M')}."
            )

        await self.store_parsed_reminder(
            parsed=parsed,
            channel=message.channel,
            created_by=message.author.id if message.author else 0
)


    def parse_embed_for_reminder(self, embed):
        title = embed.title or ""
        desc = embed.description or ""
        full_text = f"{title}\n{desc}"
        for field in embed.fields:
            full_text += f"\n{field.name}: {field.value}"

        date_match = re.search(r"(\d{1,2}(st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4})", full_text)
        time_match = re.search(r"(\d{1,2}[:.]\d{2})", full_text)

        reminder_time = None
        datetime_obj = None

        if date_match and time_match:
            try:
                clean_date = date_match.group(1).replace('st', '').replace('nd', '').replace('rd', '').replace('th', '')
                time_str = time_match.group(1).replace('.', ':')
                datetime_obj = datetime.strptime(f"{clean_date} {time_str}", "%d %B %Y %H:%M")
                reminder_time = datetime_obj - timedelta(minutes=30)
            except Exception as e:
                print(f"[ReminderParse] Error parsing datetime: {e}")

        return {
            "title": title,
            "description": desc,
            "datetime": datetime_obj,
            "reminder_time": reminder_time
        }
    
    async def store_parsed_reminder(self, parsed: dict, channel: discord.TextChannel, created_by: int):
        if not self.conn:
            print("❌ No DB connection available for storing parsed reminder.")
            return

        # Tijd & dagvelden opsplitsen
        dt = parsed["datetime"]
        name = f"AutoReminder - {parsed['title'][:30]}"  # korte naam
        time_obj = dt.time()
        day_str = str(dt.weekday())  # maandag=0 → opslaan als string
        message = parsed['title'] + "\n\n" + (parsed['description'] or "")

        await self.conn.execute(
            "INSERT INTO reminders (name, channel_id, time, days, message, created_by) VALUES ($1, $2, $3, $4, $5, $6)",
            name,
            str(channel.id),
            time_obj,
            day_str,  # als je weekdagen als strings opslaat
            message,
            str(created_by)
        )

        print(f"✅ Reminder stored for {dt.strftime('%A %H:%M')} in channel {channel.name}")



async def setup(bot):
    await bot.add_cog(ReminderCog(bot))