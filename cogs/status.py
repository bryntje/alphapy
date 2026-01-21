import discord
import aiohttp
import time
from datetime import datetime, timezone
from utils.timezone import BRUSSELS_TZ
from utils.logger import get_gpt_status_logs, logger
from discord import app_commands
from discord.ext import commands
from version import __version__, CODENAME
import os
import asyncio
import asyncpg
from asyncpg import exceptions as pg_exceptions
import config
from utils.checks_interaction import is_owner_or_admin_interaction
from utils.command_metadata import (
    get_category_for_cog,
    is_admin_command,
    find_enable_disable_pair,
    format_command_pair,
    HIDDEN_COMMANDS,
)
from typing import Optional, Dict, Any, List, cast

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

@app_commands.command(name="commands", description="List all available bot commands")
@app_commands.describe(
    include_admin="Include admin-only commands (default: False)",
    public="Post in channel instead of ephemeral (default: False)"
)
async def commands_list_cmd(
    interaction: discord.Interaction,
    include_admin: bool = False,
    public: bool = False
):
    """List all available bot commands in a nicely formatted embed."""
    await interaction.response.defer(ephemeral=not public)
    
    try:
        
        # Build a mapping of commands to their cogs
        command_to_cog = {}
        
        # Method 1: Walk through all cogs and their commands
        bot = cast(commands.Bot, interaction.client)
        for cog_name, cog in bot.cogs.items():
            # Get all app commands from this cog
            for attr_name in dir(cog):
                attr = getattr(cog, attr_name, None)
                if isinstance(attr, app_commands.Command):
                    command_to_cog[attr.name] = cog_name
                elif isinstance(attr, app_commands.Group):
                    # Also check subcommands in groups
                    for subcommand in attr.walk_commands():
                        if isinstance(subcommand, app_commands.Command):
                            command_to_cog[subcommand.name] = cog_name
        
        # Method 2: Walk through command tree and find cog via binding
        for command in bot.tree.walk_commands():
            if isinstance(command, app_commands.Command) and command.name not in command_to_cog:
                # Try to find the cog by checking command binding
                cog_name = None
                
                # Check if command has a direct cog reference
                if hasattr(command, 'binding') and command.binding:  # type: ignore
                    cog_name = command.binding.__class__.__name__  # type: ignore
                elif hasattr(command, 'cog') and command.cog:  # type: ignore
                    cog_name = command.cog.__class__.__name__  # type: ignore
                else:
                    # Check parent group for cog reference
                    if hasattr(command, 'parent') and command.parent:
                        parent = command.parent
                        if hasattr(parent, 'binding') and parent.binding:  # type: ignore
                            cog_name = parent.binding.__class__.__name__  # type: ignore
                        elif hasattr(parent, 'cog') and parent.cog:  # type: ignore
                            cog_name = parent.cog.__class__.__name__  # type: ignore
                
                if cog_name:
                    command_to_cog[command.name] = cog_name
        
        # Collect all commands grouped by category
        commands_by_category: Dict[str, List[Dict[str, Any]]] = {}
        admin_commands_by_category: Dict[str, List[Dict[str, Any]]] = {}
        
        # Walk through all commands in the tree (bot is already cast to commands.Bot above)
        for command in bot.tree.walk_commands():
            if isinstance(command, app_commands.Command):
                # Skip command groups (they're not executable commands)
                if isinstance(command, app_commands.Group):
                    continue
                
                # Skip hidden commands
                if command.name in HIDDEN_COMMANDS:
                    continue
                
                # Get full command path (including parent groups)
                full_path = command.name
                if hasattr(command, 'parent') and command.parent:
                    parent = command.parent
                    path_parts = [command.name]
                    while parent:
                        if hasattr(parent, 'name'):
                            path_parts.insert(0, parent.name)
                        # Get next parent
                        parent = getattr(parent, 'parent', None)
                    full_path = ' '.join(path_parts)
                
                # Skip if full path is hidden
                if full_path in HIDDEN_COMMANDS:
                    continue
                
                # Check if command is admin-only using centralized function
                default_perms = getattr(command, 'default_permissions', None)
                is_admin = is_admin_command(
                    command_name=command.name,
                    full_path=full_path,
                    has_checks=bool(command.checks),
                    default_permissions=default_perms,
                    description=command.description
                )
                
                # Get category name using centralized function
                cog_name = command_to_cog.get(command.name, "Other")
                category = get_category_for_cog(cog_name)
                
                cmd_info = {
                    "name": command.name,
                    "full_path": full_path,
                    "description": command.description or "No description",
                    "is_admin": is_admin
                }
                
                # Add to appropriate category
                if is_admin:
                    if category not in admin_commands_by_category:
                        admin_commands_by_category[category] = []
                    admin_commands_by_category[category].append(cmd_info)
                else:
                    if category not in commands_by_category:
                        commands_by_category[category] = []
                    commands_by_category[category].append(cmd_info)
        
        # Sort commands within each category
        for category in commands_by_category:
            commands_by_category[category].sort(key=lambda x: x["name"])
        for category in admin_commands_by_category:
            admin_commands_by_category[category].sort(key=lambda x: x["name"])
        
        # Build embed
        embed = discord.Embed(
            title="📋 Available Commands",
            color=discord.Color.blue(),
            timestamp=datetime.now(BRUSSELS_TZ)
        )
        
        # Add public commands by category
        if commands_by_category:
            # Sort categories alphabetically
            sorted_categories = sorted(commands_by_category.keys())
            
            for category in sorted_categories:
                commands_list = commands_by_category[category]
                
                # Group enable/disable commands together using centralized function
                formatted_lines = []
                processed_commands = set()
                
                for cmd in commands_list:
                    cmd_name = cmd['name']
                    full_path = cmd.get('full_path', cmd_name)
                    
                    if cmd_name in processed_commands:
                        continue
                    
                    # Try to find enable/disable pair using centralized function
                    pair_cmd = find_enable_disable_pair(full_path, commands_list)
                    
                    if pair_cmd and pair_cmd['name'] not in processed_commands:
                        # Format as pair using centralized function
                        enable_cmd = cmd if full_path.endswith(' enable') or cmd_name == 'enable' else pair_cmd
                        disable_cmd = pair_cmd if enable_cmd == cmd else cmd
                        formatted_lines.append(format_command_pair(enable_cmd, disable_cmd))
                        processed_commands.add(cmd_name)
                        processed_commands.add(pair_cmd['name'])
                        continue
                    
                    # Regular command (not enable/disable pair)
                    cmd_display = f"/{full_path.replace(' ', ' ')}" if ' ' in full_path else f"/{cmd_name}"
                    formatted_lines.append(f"`{cmd_display}` — {cmd['description'][:70]}")
                    processed_commands.add(cmd_name)
                
                commands_text = "\n".join(formatted_lines)
                
                # Discord embed field value limit is 1024 characters
                if len(commands_text) > 1024:
                    # Split into multiple fields if needed
                    chunks = []
                    current_chunk = ""
                    for line in commands_text.split("\n"):
                        if len(current_chunk) + len(line) + 1 > 1024:
                            chunks.append(current_chunk)
                            current_chunk = line + "\n"
                        else:
                            current_chunk += line + "\n"
                    if current_chunk:
                        chunks.append(current_chunk)
                    
                    for idx, chunk in enumerate(chunks[:3]):  # Max 3 chunks per category
                        field_name = category if idx == 0 else f"{category} (continued)"
                        embed.add_field(
                            name=field_name,
                            value=chunk[:1024],
                            inline=False
                        )
                else:
                    embed.add_field(
                        name=category,
                        value=commands_text,
                        inline=False
                    )
        else:
            embed.add_field(
                name="📦 Commands",
                value="No public commands found.",
                inline=False
            )
        
        # Add admin commands by category if requested
        if include_admin and admin_commands_by_category:
            sorted_admin_categories = sorted(admin_commands_by_category.keys())
            
            for category in sorted_admin_categories:
                commands_list = admin_commands_by_category[category]
                
                # Group enable/disable commands together using centralized function
                formatted_lines = []
                processed_commands = set()
                
                for cmd in commands_list:
                    cmd_name = cmd['name']
                    full_path = cmd.get('full_path', cmd_name)
                    
                    if cmd_name in processed_commands:
                        continue
                    
                    # Try to find enable/disable pair using centralized function
                    pair_cmd = find_enable_disable_pair(full_path, commands_list)
                    
                    if pair_cmd and pair_cmd['name'] not in processed_commands:
                        # Format as pair using centralized function
                        enable_cmd = cmd if full_path.endswith(' enable') or cmd_name == 'enable' else pair_cmd
                        disable_cmd = pair_cmd if enable_cmd == cmd else cmd
                        formatted_lines.append(format_command_pair(enable_cmd, disable_cmd))
                        processed_commands.add(cmd_name)
                        processed_commands.add(pair_cmd['name'])
                        continue
                    
                    # Regular command (not enable/disable pair)
                    cmd_display = f"/{full_path.replace(' ', ' ')}" if ' ' in full_path else f"/{cmd_name}"
                    formatted_lines.append(f"`{cmd_display}` — {cmd['description'][:70]}")
                    processed_commands.add(cmd_name)
                
                admin_text = "\n".join(formatted_lines)
                
                if len(admin_text) > 1024:
                    admin_chunks = []
                    current_chunk = ""
                    for line in admin_text.split("\n"):
                        if len(current_chunk) + len(line) + 1 > 1024:
                            admin_chunks.append(current_chunk)
                            current_chunk = line + "\n"
                        else:
                            current_chunk += line + "\n"
                    if current_chunk:
                        admin_chunks.append(current_chunk)
                    
                    for idx, chunk in enumerate(admin_chunks[:3]):
                        field_name = f"🔐 {category}" if idx == 0 else f"🔐 {category} (continued)"
                        embed.add_field(
                            name=field_name,
                            value=chunk[:1024],
                            inline=False
                        )
                else:
                    embed.add_field(
                        name=f"🔐 {category}",
                        value=admin_text,
                        inline=False
                    )
        
        # Add summary
        total_public = sum(len(cmds) for cmds in commands_by_category.values())
        total_admin = sum(len(cmds) for cmds in admin_commands_by_category.values()) if include_admin else 0
        total_categories = len(commands_by_category)
        if include_admin:
            total_categories += len(admin_commands_by_category)
        
        summary = f"**{total_public}** public command{'s' if total_public != 1 else ''} in **{len(commands_by_category)}** categor{'ies' if len(commands_by_category) != 1 else 'y'}"
        if include_admin:
            summary += f"\n**{total_admin}** admin command{'s' if total_admin != 1 else ''} in **{len(admin_commands_by_category)}** categor{'ies' if len(admin_commands_by_category) != 1 else 'y'}"
        
        embed.add_field(
            name="📊 Summary",
            value=summary,
            inline=False
        )
        
        embed.set_footer(text=f"v{__version__} — {CODENAME}")
        
        await interaction.followup.send(embed=embed, ephemeral=not public)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Failed to retrieve commands list: {e}",
            ephemeral=not public
        )

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
    bot.tree.add_command(commands_list_cmd)
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
