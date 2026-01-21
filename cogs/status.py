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
from asyncpg import exceptions as pg_exceptions
import config
from utils.checks_interaction import is_owner_or_admin_interaction
from typing import Optional, Dict, Any

# Database pool for command_stats (shared across status commands)
_status_db_pool: Optional[asyncpg.Pool] = None

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

@app_commands.command(name="health", description="Show configuration and system status")
async def health_cmd(interaction: discord.Interaction):
    embed = await _build_health_embed(interaction)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="command_stats", description="Show command usage statistics (admin only)")
@app_commands.describe(
    days="Number of days to look back (default: 7)",
    limit="Maximum number of commands to show (default: 10)",
    guild_only="Show stats for this server only (default: True)"
)
async def command_stats_cmd(
    interaction: discord.Interaction,
    days: int = 7,
    limit: int = 10,
    guild_only: bool = True
):
    """Show command usage statistics in a rich embed."""
    # Check admin permissions
    if not await is_owner_or_admin_interaction(interaction):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command. Administrator access required.",
            ephemeral=True
        )
        return
    
    # If guild_only=False, only allow bot owners
    if not guild_only:
        if interaction.user.id not in config.OWNER_IDS:
            await interaction.response.send_message(
                "❌ Only bot owners can view stats for all servers. Use `guild_only: True` for server-specific stats.",
                ephemeral=True
            )
            return
    
    await interaction.response.defer(ephemeral=True)
    
    # Use connection pool instead of direct connection
    global _status_db_pool
    
    # Initialize pool if needed
    if _status_db_pool is None or _status_db_pool.is_closing():
        try:
            _status_db_pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=1,
                max_size=5,
                command_timeout=10.0
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to connect to database: {e}",
                ephemeral=True
            )
            return
    
    try:
        async with _status_db_pool.acquire() as conn:
            # Build query
            where_clause = "WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL"
            params: list[Any] = [str(days)]
            param_index = 2
            
            guild_id: Optional[int] = None
            if guild_only and interaction.guild:
                guild_id = interaction.guild.id
                where_clause += f" AND guild_id = ${param_index}"
                params.append(guild_id)
                param_index += 1
            
            # Execute query for top commands
            limit_param_index = param_index
            query = f"""
                SELECT command_name, COUNT(*) as usage_count
                FROM audit_logs
                {where_clause}
                GROUP BY command_name
                ORDER BY usage_count DESC
                LIMIT ${limit_param_index}
            """
            rows = await conn.fetch(query, *params, limit)
            
            # Get total commands executed in period (same where clause, no limit)
            total_query = f"""
                SELECT COUNT(*) as total
                FROM audit_logs
                {where_clause}
            """
            total_rows = await conn.fetch(total_query, *params)
            total_commands = total_rows[0]["total"] if total_rows else 0
            
            # Build embed
            embed = discord.Embed(
                title="📊 Command Usage Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now(BRUSSELS_TZ)
            )
            
            # Add period and scope info
            scope_text = f"This server ({interaction.guild.name})" if guild_only and interaction.guild else "All servers"
            embed.add_field(
                name="📅 Period",
                value=f"Last {days} day{'s' if days != 1 else ''}",
                inline=True
            )
            embed.add_field(
                name="🌐 Scope",
                value=scope_text,
                inline=True
            )
            embed.add_field(
                name="📈 Total Commands",
                value=f"{total_commands:,}",
                inline=True
            )
            
            # Add top commands
            if rows:
                commands_list = []
                for idx, row in enumerate(rows, 1):
                    command_name = row["command_name"]
                    usage_count = row["usage_count"]
                    commands_list.append(f"`{idx}.` **{command_name}** — {usage_count:,} uses")
                
                commands_text = "\n".join(commands_list)
                # Discord embed field value limit is 1024 characters
                if len(commands_text) > 1024:
                    commands_text = commands_text[:1021] + "..."
                
                embed.add_field(
                    name=f"🏆 Top {len(rows)} Commands",
                    value=commands_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="🏆 Top Commands",
                    value="No commands executed in this period.",
                    inline=False
                )
            
            embed.set_footer(text=f"v{__version__} — {CODENAME}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
    except pg_exceptions.UndefinedTableError:
        await interaction.followup.send(
            "❌ Command analytics not available. The `audit_logs` table has not been initialized yet.",
            ephemeral=True
        )
    except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
        # Connection error - reset pool and try to reconnect next time
        if _status_db_pool:
            try:
                await _status_db_pool.close()
            except Exception:
                pass
            _status_db_pool = None
        await interaction.followup.send(
            f"❌ Database connection error. Please try again in a moment.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Failed to retrieve command statistics: {e}",
            ephemeral=True
        )

# ------------------ SETUP FUNCTION ------------------ #

async def setup(bot: commands.Bot):
    bot.tree.add_command(gptstatus)
    bot.tree.add_command(version_cmd)
    bot.tree.add_command(release_cmd)
    bot.tree.add_command(health_cmd)
    bot.tree.add_command(command_stats_cmd)

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
    # Default model depends on provider (grok-3 for Grok, gpt-3.5-turbo for OpenAI)
    try:
        import config
        default_model = "grok-3" if getattr(config, "LLM_PROVIDER", "grok").strip().lower() == "grok" else "gpt-3.5-turbo"
    except:
        default_model = "grok-3"
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
    # Use existing pool if available, otherwise quick direct connection check
    if _status_db_pool and not _status_db_pool.is_closing():
        try:
            async with _status_db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            db_ok = "🛑"
    else:
        # Fallback: quick direct connection check (acceptable for health check)
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
