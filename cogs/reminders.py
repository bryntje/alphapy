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

    @app_commands.command(name="reminder_list", description="📋 Bekijk je actieve reminders")
    async def reminder_list(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        channel_id = str(interaction.channel.id)

        await interaction.response.defer(ephemeral=True)

        query = """
            SELECT id, name, time, days FROM reminders
            WHERE created_by = $1 OR channel_id = $2
            ORDER BY time;
        """
        try:
            rows = await self.conn.fetch(query, user_id, channel_id)

            if not rows:
                await interaction.followup.send("❌ Geen reminders gevonden.")
                return

            msg_lines = [f"📋 **Actieve Reminders:**"]
            for row in rows:
                days_str = ", ".join(row["days"])
                msg_lines.append(
                    f"🔹 **{row['name']}** — ⏰ {row['time']} op `{days_str}` (ID: {row['id']})"
                )

            await interaction.followup.send("\n".join(msg_lines))
        except Exception as e:
            await interaction.followup.send(f"⚠️ Fout bij ophalen reminders: {e}")


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
            rows = await self.conn.fetch(query, current_time, current_day)
            for row in rows:
                channel = self.bot.get_channel(int(row["channel_id"]))
                if channel:
                    await channel.send(f"⏰ Reminder **{row['name']}**: {row['message']}")
                # (Optioneel) verwijder reminder of update status
                # await self.conn.execute("DELETE FROM reminders WHERE id = $1", row["id"])
        except Exception as e:
            print("🚨 Reminder loop error:", e)


async def setup(bot):
    await bot.add_cog(ReminderCog(bot))