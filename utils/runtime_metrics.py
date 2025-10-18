import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from discord.ext import commands


@dataclass
class GuildSnapshot:
    id: int
    name: str
    member_count: Optional[int]
    owner_id: Optional[int]


@dataclass
class CommandSnapshot:
    qualified_name: str
    description: Optional[str]
    type: str


@dataclass
class BotSnapshot:
    online: bool
    latency_ms: Optional[float]
    uptime_seconds: Optional[int]
    uptime_human: Optional[str]
    guilds: List[GuildSnapshot]
    commands_loaded: int
    commands: List[CommandSnapshot]


def _format_duration(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: List[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


async def _snapshot_bot(bot: "commands.Bot") -> BotSnapshot:
    guilds: List[GuildSnapshot] = []
    for guild in bot.guilds:
        guilds.append(
            GuildSnapshot(
                id=guild.id,
                name=guild.name,
                member_count=getattr(guild, "member_count", None),
                owner_id=getattr(guild, "owner_id", None),
            )
        )

    start_ts = getattr(bot, "start_time", None)
    uptime_seconds: Optional[int] = None
    uptime_human: Optional[str] = None
    if isinstance(start_ts, (int, float)):
        uptime_delta = datetime.now(timezone.utc) - datetime.fromtimestamp(start_ts, tz=timezone.utc)
        uptime_seconds = int(uptime_delta.total_seconds())
        uptime_human = _format_duration(uptime_delta)

    latency_raw = getattr(bot, "latency", None)
    latency_ms = round(latency_raw * 1000, 2) if isinstance(latency_raw, (int, float)) else None

    commands_loaded = 0
    commands: List[CommandSnapshot] = []
    if hasattr(bot, "tree"):
        for cmd in bot.tree.walk_commands():
            commands_loaded += 1
            qualified_name = getattr(cmd, "qualified_name", getattr(cmd, "name", ""))
            description = getattr(cmd, "description", None)
            cmd_type = cmd.__class__.__name__
            commands.append(
                CommandSnapshot(
                    qualified_name=qualified_name or "",
                    description=description,
                    type=cmd_type,
                )
            )
            if len(commands) >= 50:
                break

    return BotSnapshot(
        online=bot.is_ready(),
        latency_ms=latency_ms,
        uptime_seconds=uptime_seconds,
        uptime_human=uptime_human,
        guilds=guilds,
        commands_loaded=commands_loaded,
        commands=commands,
    )


async def get_bot_snapshot(timeout: float = 2.0) -> Optional[BotSnapshot]:
    """
    Collect a live snapshot of the Discord bot. Returns None when the bot is not running.
    """
    from gpt.helpers import bot_instance  # Imported lazily to avoid circular on startup

    if bot_instance is None:
        return None

    loop = bot_instance.loop

    async def runner() -> BotSnapshot:
        return await _snapshot_bot(bot_instance)

    try:
        future = asyncio.run_coroutine_threadsafe(runner(), loop)
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None


def serialize_snapshot(snapshot: Optional[BotSnapshot]) -> Dict[str, Any]:
    if snapshot is None:
        return {
            "online": False,
            "latency_ms": None,
            "uptime_seconds": None,
            "uptime_human": None,
            "commands_loaded": 0,
            "guilds": [],
            "commands": [],
        }
    return {
        "online": snapshot.online,
        "latency_ms": snapshot.latency_ms,
        "uptime_seconds": snapshot.uptime_seconds,
        "uptime_human": snapshot.uptime_human,
        "commands_loaded": snapshot.commands_loaded,
        "guilds": [
            {
                "id": guild.id,
                "name": guild.name,
                "member_count": guild.member_count,
                "owner_id": guild.owner_id,
            }
            for guild in snapshot.guilds
        ],
        "commands": [
            {
                "qualified_name": cmd.qualified_name,
                "description": cmd.description,
                "type": cmd.type,
            }
            for cmd in snapshot.commands
        ],
    }


__all__ = ["get_bot_snapshot", "serialize_snapshot", "BotSnapshot", "GuildSnapshot", "CommandSnapshot"]
