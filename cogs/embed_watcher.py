import discord
from discord.ext import commands
import re
from datetime import datetime, timedelta

class EmbedReminderWatcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = None  # ← DB connectie later invullen als nodig

    @commands.Cog.listener()
    async def on_message(self, message):
        ANNOUNCEMENTS_CHANNEL_ID = 1160511692824924216  # <-- pas aan!

        if message.channel.id != ANNOUNCEMENTS_CHANNEL_ID or not message.embeds:
            return

        embed = message.embeds[0]
        parsed = self.parse_embed_for_reminder(embed)

        if parsed and parsed["reminder_time"]:
            await message.channel.send(
                f"🔔 Auto-reminder gedetecteerd:\n"
                f"📌 **{parsed['title']}**\n"
                f"🗓️ {parsed['datetime'].strftime('%A %d %B %Y')} om {parsed['datetime'].strftime('%H:%M')}\n"
                f"⏰ Reminder zal triggeren om {parsed['reminder_time'].strftime('%H:%M')}."
            )

            if self.conn:
                await self.store_parsed_reminder(parsed, message.channel, message.author.id)

    def parse_embed_for_reminder(self, embed):
        title = embed.title or ""
        desc = embed.description or ""
        full_text = title + "\n" + desc
        for field in embed.fields:
            full_text += f"\n{field.name}: {field.value}"

        date_match = re.search(r"(\d{1,2}(st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4})", full_text)
        time_match = re.search(r"(\d{1,2}[:.]\d{2})", full_text)

        if not date_match or not time_match:
            return None

        try:
            clean_date = date_match.group(1).replace('st','').replace('nd','').replace('rd','').replace('th','')
            time_str = time_match.group(1).replace('.', ':')
            dt = datetime.strptime(f"{clean_date} {time_str}", "%d %B %Y %H:%M")
            return {
                "title": title,
                "description": desc,
                "datetime": dt,
                "reminder_time": dt - timedelta(minutes=30)
            }
        except Exception as e:
            print(f"[Parse Error] {e}")
            return None

    async def store_parsed_reminder(self, parsed, channel, created_by):
        dt = parsed["datetime"]
        time_obj = dt.time()
        weekday_str = str(dt.weekday())
        name = f"AutoReminder - {parsed['title'][:30]}"
        message = f"{parsed['title']}\n\n{parsed['description']}"

        await self.conn.execute(
            "INSERT INTO reminders (name, channel_id, time, days, message, created_by) VALUES ($1, $2, $3, $4, $5, $6)",
            name,
            str(channel.id),
            time_obj,
            weekday_str,
            message,
            str(created_by)
        )
        print("✅ Reminder opgeslagen in DB")

async def setup(bot):
    await bot.add_cog(EmbedReminderWatcher(bot))
