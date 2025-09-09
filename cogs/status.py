import discord
import aiohttp
import time
from datetime import datetime, timezone
from utils.timezone import BRUSSELS_TZ
from utils.logger import get_gpt_status_logs
from discord import app_commands
from discord.ext import commands

# ------------------ SLASH COMMAND ------------------ #

@app_commands.command(name="gptstatus", description="Check the status of the GPT API.")
async def gptstatus(interaction: discord.Interaction):
    embed = await get_gptstatus_embed()
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ------------------ SETUP FUNCTION ------------------ #

async def setup(bot: commands.Bot):
    bot.tree.add_command(gptstatus)

# ------------------ HELPER FUNCTIONS ------------------ #

STATUS_URL = "https://status.openai.com/api/v2/status.json"

async def fetch_openai_status():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(STATUS_URL) as resp:
                data = await resp.json()
                return data.get("status", {}).get("description", "Unknown")
    except Exception:
        return "Unavailable"

def format_timedelta(ts):
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(BRUSSELS_TZ) - ts
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes} min ago" if minutes < 60 else f"{delta.seconds // 3600} hr ago"

async def get_gptstatus_embed():
    logs = get_gpt_status_logs()

    last_success = logs.last_success_time or "-"
    last_error = logs.last_error_type or "None"
    latency = logs.average_latency_ms or 0
    token_usage = logs.total_tokens_today or 0
    rate_limit_reset = logs.rate_limit_reset or "~"
    model = logs.current_model or "gpt-3.5-turbo"
    user = logs.last_user or "-"
    success_count = logs.success_count or 0
    error_count = logs.error_count or 0

    status = await fetch_openai_status()

    embed = discord.Embed(
        title="🧠 GPT API Status",
        color=discord.Color.teal()
    )
    embed.add_field(name="🔹 Operational", value=f"{'✅ Yes' if 'Operational' in status else '⚠️ ' + status}", inline=False)
    embed.add_field(name="🔹 Last successful reply", value=format_timedelta(last_success) if isinstance(last_success, datetime) else last_success, inline=True)
    embed.add_field(name="🔹 Last error", value=last_error, inline=True)
    embed.add_field(name="🔹 Current model", value=f"`{model}`", inline=True)
    embed.add_field(name="🔹 Prompt tokens used today", value=f"{token_usage:,}", inline=True)
    embed.add_field(name="🔹 Rate limit window", value=f"Reset in {rate_limit_reset}", inline=True)
    embed.add_field(name="🔹 Logged interactions", value=f"✅ {success_count} / ❌ {error_count}", inline=True)
    embed.add_field(name="🔹 Last user to trigger GPT", value=f"<@{user}>", inline=True)
    embed.add_field(name="🔹 Latency (avg)", value=f"{latency}ms", inline=True)
    embed.set_footer(text="📦 GPT Status • Updated just now")

    return embed

# ------------------ LOGGING MOCKS ------------------ #

def log_gpt_success(user_id=None, tokens_used=0, latency_ms=0):
    print(f"✅ GPT success by {user_id} – {tokens_used} tokens, {latency_ms}ms latency")

def log_gpt_error(error_type="unknown", user_id=None):
    print(f"❌ GPT error: {error_type} by {user_id}")
