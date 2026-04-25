import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord.ext import commands


@dataclass
class GuildSnapshot:
    id: int
    name: str
    member_count: int | None
    owner_id: int | None


@dataclass
class CommandSnapshot:
    qualified_name: str
    description: str | None
    type: str


@dataclass
class BotSnapshot:
    online: bool
    latency_ms: float | None
    uptime_seconds: int | None
    uptime_human: str | None
    guilds: list[GuildSnapshot]
    commands_loaded: int
    commands: list[CommandSnapshot]


def _format_duration(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


async def _snapshot_bot(bot: "commands.Bot") -> BotSnapshot:
    guilds: list[GuildSnapshot] = []
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
    uptime_seconds: int | None = None
    uptime_human: str | None = None
    if isinstance(start_ts, (int, float)):
        uptime_delta = datetime.now(UTC) - datetime.fromtimestamp(start_ts, tz=UTC)
        uptime_seconds = int(uptime_delta.total_seconds())
        uptime_human = _format_duration(uptime_delta)

    latency_raw = getattr(bot, "latency", None)
    latency_ms = round(latency_raw * 1000, 2) if isinstance(latency_raw, (int, float)) else None

    commands_loaded = 0
    commands: list[CommandSnapshot] = []
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


async def get_bot_snapshot(timeout: float = 2.0) -> BotSnapshot | None:
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
    except TimeoutError:
        return None
    except Exception:
        return None


def serialize_snapshot(snapshot: BotSnapshot | None) -> dict[str, Any]:
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
