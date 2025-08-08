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
from utils.checks_interaction import is_owner_or_admin_interaction
from typing import Optional, List, Dict, Any
from config import GUILD_ID
from utils.logger import logger


class ReminderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn: Optional[asyncpg.Connection] = None
        self.bot.loop.create_task(self.setup())

    async def setup(self) -> None:
        await self.bot.wait_until_ready()
        try:
            self.conn = await asyncpg.connect(config.DATABASE_URL)
            logger.info("✅ Verbonden met database!")
        except Exception as e:
            logger.error(f"❌ Fout bij verbinden met database: {e}")
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
        logger.debug(f"Database connection aanwezig? {self.conn is not None}")
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
        user_id = interaction.user.id
        channel_id = interaction.channel.id
        is_admin = interaction.user.guild_permissions.administrator

        await interaction.response.defer(ephemeral=True)

        is_admin = await is_owner_or_admin_interaction(interaction)

        if is_admin:
            query = "SELECT id, name, time, days FROM reminders ORDER BY time;"
            params: List[Any] = []
        else:
            query = """
                SELECT id, name, time, days FROM reminders
                WHERE created_by = $1 OR channel_id = $2
                ORDER BY time;
            """
            params = [user_id, channel_id]

        try:
            rows = await self.conn.fetch(query, *params)
            logger.info(f"🔍 Fetched {len(rows)} reminders ({'admin' if is_admin else 'user'})")

            if not rows:
                await interaction.followup.send("❌ Geen reminders gevonden.")
                return

            msg_lines = [f"📋 **Actieve Reminders:**"]
            for row in rows:
                days_str = ", ".join(row["days"]) if row.get("days") else "-"
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

        tz = pytz.timezone("Europe/Brussels")
        now = datetime.now(tz).replace(second=0, microsecond=0)
        current_time_str = now.strftime("%H:%M:%S")
        current_day = str(now.weekday())
        current_date = now.date()

        logger.debug(f"🔁 Reminder check: {current_time_str} op dag {current_day}")

        try:
            rows = await self.conn.fetch("""
                SELECT id, channel_id, name, message, location,
                       origin_channel_id, origin_message_id, event_time, days
                FROM reminders
                WHERE time::text = $1 AND (
                    (event_time IS NOT NULL AND event_time::date = $2)
                    OR
                    ($3 = ANY(days))
                )
            """, current_time_str, current_date , current_day)

            for row in rows:
                channel = self.bot.get_channel(int(row["channel_id"]))
                if not channel:
                    logger.warning(f"⚠️ Kanaal {row['channel_id']} niet gevonden.")
                    continue

                from discord import Embed
                dt = now
                datum_str = dt.strftime("%A %d %B %Y")
                tijd_str = dt.strftime("%H:%M")

                embed = Embed(
                    title=f"⏰ Reminder: {row['name']}",
                    description=row['message'] or "-",
                    color=0x2ecc71
                )
                
                # Datum & Tijd van event
                event_dt = row['event_time']
                embed.add_field(name="📅 Date", value=event_dt.strftime("%A %d %B %Y"), inline=False)
                embed.add_field(name="⏰ Time", value=event_dt.strftime("%H:%M"), inline=False)
                
                # Locatie
                if row.get("location") and row["location"] != "-":
                    embed.add_field(name="📍 Location", value=row["location"], inline=False)
                
                # Link naar origineel bericht
                if row.get("origin_channel_id") and row.get("origin_message_id"):
                    link = f"https://discord.com/channels/{config.GUILD_ID}/{row['origin_channel_id']}/{row['origin_message_id']}"
                    embed.add_field(name="🔗 Origineel", value=f"[Klik hier]({link})", inline=False)
                
                # Verstuur met mention buiten embed
                await channel.send(
                    "@everyone",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(everyone=config.ENABLE_EVERYONE_MENTIONS)
                )
                # Als het een eenmalige reminder was (event_time bestaat), verwijder hem
                if row.get("event_time"):
                    await self.conn.execute("DELETE FROM reminders WHERE id = $1", row["id"])
                    logger.info(f"🗑️ Reminder {row['id']} (eenmalig) verwijderd na verzenden.")

        except Exception as e:
            logger.exception("🚨 Reminder loop error")

# Voor extern gebruik via FastAPI
async def get_reminders_for_user(conn: asyncpg.Connection, user_id: str):
    query = """
        SELECT id, name, time, days, message, channel_id, created_by
        FROM reminders
        WHERE created_by = $1 OR created_by = '717695552669745152'
        ORDER BY time
    """
    return await conn.fetch(query, user_id)


async def create_reminder(conn: asyncpg.Connection, data: Dict[str, Any]) -> None:
    await conn.execute(
        """
        INSERT INTO reminders (name, channel_id, time, days, message, created_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        data["name"],
        str(data["channel_id"]),
        data["time"],
        data["days"],
        data["message"],
        data["created_by"]
    )


async def update_reminder(conn: asyncpg.Connection, data: Dict[str, Any]) -> None:
    await conn.execute(
        """
        UPDATE reminders
        SET name = $1, time = $2, days = $3, message = $4
        WHERE id = $5 AND created_by = $6
        """,
        data["name"],
        data["time"],
        data["days"],
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


async def setup(bot):
    await bot.add_cog(ReminderCog(bot))