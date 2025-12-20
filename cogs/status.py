import discord
import aiohttp
import time
from datetime import datetime, timezone
from utils.timezone import BRUSSELS_TZ
from utils.logger import get_gpt_status_logs
from discord import app_commands
from discord.ext import commands
from version import __version__, CODENAME
import os
import asyncio
import asyncpg
import config

BOOT_TIME = datetime.now(BRUSSELS_TZ)

# ------------------ SLASH COMMAND ------------------ #

@app_commands.command(name="gptstatus", description="Check the status of the GPT API.")
async def gptstatus(interaction: discord.Interaction):
    embed = await get_gptstatus_embed()
    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="version", description="Show bot version")
async def version_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Innersync • Alphapy version: v{__version__} — {CODENAME}", ephemeral=True
    )

@app_commands.command(name="release", description="Show release notes for the current version")
async def release_cmd(interaction: discord.Interaction):
    try:
        base = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base, "changelog.md")
        notes = await _read_release_notes(path, __version__)
        if not notes:
            await interaction.response.send_message(f"No notes found for v{__version__}.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Release notes v{__version__}", description=notes, color=discord.Color.blue())
        embed.set_footer(text=f"{CODENAME}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to read release notes: {e}", ephemeral=True)

@app_commands.command(name="health", description="Toon configuratie en systeemstatus")
async def health_cmd(interaction: discord.Interaction):
    embed = await _build_health_embed(interaction)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ------------------ SETUP FUNCTION ------------------ #

async def setup(bot: commands.Bot):
    bot.tree.add_command(gptstatus)
    bot.tree.add_command(version_cmd)
    bot.tree.add_command(release_cmd)
    bot.tree.add_command(health_cmd)

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
    # Default model depends on provider (grok-beta for Grok, gpt-3.5-turbo for OpenAI)
    try:
        import config
        default_model = "grok-beta" if getattr(config, "LLM_PROVIDER", "grok").strip().lower() == "grok" else "gpt-3.5-turbo"
    except:
        default_model = "grok-beta"
    model = logs.current_model or default_model
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
    embed.add_field(name="🔹 Uptime", value=_format_uptime(BOOT_TIME), inline=True)
    embed.set_footer(text=f"📦 GPT Status • v{__version__} — {CODENAME} • Updated just now")

    return embed


async def _build_health_embed(interaction: discord.Interaction) -> discord.Embed:
    bot = interaction.client
    settings = getattr(bot, "settings", None)

    reminders_enabled = invites_enabled = gdpr_enabled = "?"
    if settings:
        try:
            reminders_enabled = "✅" if settings.get("reminders", "enabled") else "🛑"
            invites_enabled = "✅" if settings.get("invites", "enabled") else "🛑"
            gdpr_enabled = "✅" if settings.get("gdpr", "enabled") else "🛑"
        except KeyError:
            pass

    db_ok = "✅"
    try:
        conn = await asyncio.wait_for(asyncpg.connect(config.DATABASE_URL), timeout=3)
    except Exception:
        db_ok = "🛑"
    else:
        await conn.close()

    embed = discord.Embed(title="🩺 Bot Health", color=discord.Color.green())
    embed.add_field(name="Database", value=db_ok, inline=True)
    embed.add_field(name="Reminders", value=reminders_enabled, inline=True)
    embed.add_field(name="Invites", value=invites_enabled, inline=True)
    embed.add_field(name="GDPR", value=gdpr_enabled, inline=True)
    embed.add_field(name="Uptime", value=_format_uptime(BOOT_TIME), inline=True)
    return embed

async def _read_release_notes(changelog_path: str, version: str) -> str:
    try:
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, lambda: open(changelog_path, "r", encoding="utf-8").read())
        # very simple parse: find header '## [version]' and capture until next '##'
        start_marker = f"## [{version}]"
        if start_marker not in content:
            return ""
        start = content.index(start_marker) + len(start_marker)
        rest = content[start:]
        end_idx = rest.find("\n## ")
        section = rest[:end_idx] if end_idx != -1 else rest
        return section.strip()
    except Exception:
        return ""

def _format_uptime(start_dt: datetime) -> str:
    delta = datetime.now(BRUSSELS_TZ) - start_dt
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)

# ------------------ LOGGING MOCKS ------------------ #

def log_gpt_success(user_id=None, tokens_used=0, latency_ms=0, guild_id=None, model=None):
    print(f"✅ GPT success by {user_id} – {tokens_used} tokens, {latency_ms}ms latency")

def log_gpt_error(error_type="unknown", user_id=None, guild_id=None):
    print(f"❌ GPT error: {error_type} by {user_id}")
