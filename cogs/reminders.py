import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import asyncio
from datetime import datetime, time as dtime
import config


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

    @tasks.loop(minutes=1)
    async def load_reminders(self):
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%a").lower()[:2]

        reminders = await self.conn.fetch("SELECT * FROM reminders")
        for reminder in reminders:
            if current_day in reminder["days"] and current_time == reminder["time"]:
                channel = self.bot.get_channel(int(reminder["channel_id"]))
                if channel:
                    await channel.send(reminder["message"])

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

async def setup(bot):
    await bot.add_cog(ReminderCog(bot))