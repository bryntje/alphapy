import asyncio
import logging
import math
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union, Literal, AsyncGenerator

import asyncpg
from asyncpg import exceptions as pg_exceptions
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from cogs.reminders import (
    create_reminder,
    delete_reminder,
    get_reminders_for_user,
    update_reminder,
)
from utils.logger import get_gpt_status_logs
from utils.runtime_metrics import get_bot_snapshot, serialize_snapshot
from utils.timezone import BRUSSELS_TZ
from utils.supabase_auth import verify_supabase_token
from utils.supabase_client import _supabase_post, SupabaseConfigurationError
from webhooks.supabase import router as supabase_webhook_router
from version import CODENAME, __version__

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


async def verify_api_key(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> None:
    """Guard routes with a Supabase JWT or optional API key."""
    claims: Optional[Dict[str, Any]] = None

    if authorization:
        try:
            claims = verify_supabase_token(authorization)
        except HTTPException:
            # Invalid JWT; fall back to API key check if configured.
            claims = None

    if claims:
        request.state.supabase_claims = claims
        return

    configured_key = getattr(config, "API_KEY", None)
    if configured_key:
        if x_api_key != configured_key:
            raise HTTPException(status_code=401, detail="Unauthorized")
        request.state.supabase_claims = None
        return

    # No Supabase claims and no API key configured — allow anonymous access.
    request.state.supabase_claims = None


async def get_authenticated_user_id(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
) -> str:
    """Extract authenticated user ID from JWT or headers."""
    claims = getattr(request.state, "supabase_claims", None)

    if not claims and authorization:
        try:
            claims = verify_supabase_token(authorization)
        except HTTPException:
            claims = None

    if claims and "sub" in claims:
        return str(claims["sub"])

    if x_user_id:
        return x_user_id

    raise HTTPException(status_code=401, detail="Missing authentication context")


# ---------------------------------------------------------------------------
# FastAPI app bootstrap
# ---------------------------------------------------------------------------

db_pool: Optional[asyncpg.Pool] = None
router = APIRouter(prefix="/api", dependencies=[Depends(verify_api_key)])

# Telemetry retry queue
_telemetry_queue: List[Dict[str, Any]] = []
MAX_TELEMETRY_QUEUE_SIZE = 100
MAX_TELEMETRY_RETRIES = 5


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global db_pool
    db_pool = await asyncpg.create_pool(config.DATABASE_URL)
    print("✅ DB pool created")
    
    # Start background telemetry ingest task
    ingest_interval = getattr(config, "TELEMETRY_INGEST_INTERVAL", 45)
    ingest_task = asyncio.create_task(_telemetry_ingest_loop(ingest_interval))
    
    try:
        yield
    finally:
        # Cancel and wait for the background task to finish
        ingest_task.cancel()
        try:
            await ingest_task
        except asyncio.CancelledError:
            pass
        
        if db_pool:
            await db_pool.close()
        print("🔌 DB pool closed")


app = FastAPI(lifespan=lifespan)
app.include_router(supabase_webhook_router)

# CORS settings
_allowed_origins = getattr(config, "ALLOWED_ORIGINS", [])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins else ["*"],
    allow_credentials=bool(_allowed_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Simple status endpoints (kept for backwards compat)
# ---------------------------------------------------------------------------

startup_time = time.time()


class HealthStatus(BaseModel):
    service: str
    version: str
    uptime_seconds: int
    db_status: str
    timestamp: str


@app.get("/api/health", response_model=HealthStatus, include_in_schema=False)
async def health_check() -> HealthStatus:
    uptime_seconds = int(time.time() - startup_time)
    db_status = "not_initialized"

    if db_pool:
        try:
            async with db_pool.acquire() as connection:
                await connection.execute("SELECT 1")
            db_status = "ok"
        except Exception as error:
            db_status = f"error:{error.__class__.__name__}"

    return HealthStatus(
        service=config.SERVICE_NAME,
        version=__version__,
        uptime_seconds=uptime_seconds,
        db_status=db_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/status")
def get_status():
    return {
        "online": True,
        "latency": 0,
        "uptime": f"{int((time.time() - startup_time) // 60)} min",
    }


@app.get("/top-commands")
def get_top_commands():
    # Static placeholder for now; replace when usage analytics are wired in.
    return {"create_caption": 182, "help": 39}


# ---------------------------------------------------------------------------
# Helper utilities for dashboard payloads
# ---------------------------------------------------------------------------


def _datetime_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRUSSELS_TZ).isoformat()


class GuildInfo(BaseModel):
    id: int
    name: str
    member_count: Optional[int]
    owner_id: Optional[int]


class CommandInfo(BaseModel):
    qualified_name: str
    description: Optional[str]
    type: str


class BotMetrics(BaseModel):
    online: bool
    latency_ms: Optional[float]
    uptime_seconds: Optional[int]
    uptime_human: Optional[str]
    commands_loaded: int
    version: str
    codename: str
    guilds: List[GuildInfo]
    commands: List[CommandInfo]


class GPTLogEvent(BaseModel):
    timestamp: Optional[str]
    user_id: Optional[int]
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    error_type: Optional[str] = None


class GPTMetrics(BaseModel):
    last_success_time: Optional[str]
    last_error_type: Optional[str]
    average_latency_ms: int
    total_tokens_today: int
    rate_limit_reset: Optional[str]
    current_model: str
    last_user_id: Optional[int]
    success_count: int
    error_count: int
    last_success_latency_ms: Optional[int]
    recent_successes: List[GPTLogEvent]
    recent_errors: List[GPTLogEvent]


class UpcomingReminder(BaseModel):
    id: int
    name: str
    channel_id: int
    scheduled_time: Optional[str]
    is_recurring: bool


class ReminderStats(BaseModel):
    total: int
    recurring: int
    one_off: int
    next_event_time: Optional[str]
    per_channel: Dict[str, int]
    upcoming: List[UpcomingReminder]


class TicketListItem(BaseModel):
    id: int
    username: Optional[str]
    status: Optional[str]
    channel_id: Optional[int]
    created_at: Optional[str]


class TicketStats(BaseModel):
    total: int
    per_status: Dict[str, int]
    open_count: int
    last_ticket_created_at: Optional[str]
    average_close_seconds: Optional[int]
    average_close_human: Optional[str]
    open_items: List[TicketListItem]


class SettingOverride(BaseModel):
    scope: str
    key: str
    value: str


class InfrastructureMetrics(BaseModel):
    database_up: bool
    pool_size: Optional[int]
    checked_at: str


class DashboardMetrics(BaseModel):
    bot: BotMetrics
    gpt: GPTMetrics
    reminders: ReminderStats
    tickets: TicketStats
    settings_overrides: List[SettingOverride]
    infrastructure: InfrastructureMetrics


def _serialize_gpt_events(raw_events) -> List[GPTLogEvent]:
    events: List[GPTLogEvent] = []
    for evt in raw_events:
        events.append(
            GPTLogEvent(
                timestamp=_datetime_to_iso(evt.get("timestamp")),
                user_id=evt.get("user_id"),
                tokens_used=evt.get("tokens_used"),
                latency_ms=evt.get("latency_ms"),
                error_type=evt.get("error_type"),
            )
        )
    return events


def _collect_gpt_metrics() -> GPTMetrics:
    logs = get_gpt_status_logs()
    return GPTMetrics(
        last_success_time=_datetime_to_iso(logs.last_success_time),
        last_error_type=logs.last_error_type,
        average_latency_ms=int(logs.average_latency_ms or 0),
        total_tokens_today=int(logs.total_tokens_today or 0),
        rate_limit_reset=logs.rate_limit_reset,
        current_model=logs.current_model,
        last_user_id=logs.last_user,
        success_count=int(logs.success_count or 0),
        error_count=int(logs.error_count or 0),
        last_success_latency_ms=logs.last_success_latency_ms,
        recent_successes=_serialize_gpt_events(logs.success_events),
        recent_errors=_serialize_gpt_events(logs.error_events),
    )


async def _fetch_reminder_stats(guild_id: Optional[int] = None) -> ReminderStats:
    """Fetch reminder statistics for dashboard."""
    default = ReminderStats(
        total=0,
        recurring=0,
        one_off=0,
        next_event_time=None,
        per_channel={},
        upcoming=[],
    )
    global db_pool
    if db_pool is None:
        return default
    try:
        async with db_pool.acquire() as conn:
            where_clause = "WHERE guild_id = $1" if guild_id is not None else ""
            params = [guild_id] if guild_id is not None else []
            counts_row = await conn.fetchrow(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE COALESCE(array_length(days, 1), 0) > 0) AS recurring,
                    COUNT(*) FILTER (WHERE COALESCE(array_length(days, 1), 0) = 0) AS one_off
                FROM reminders
                {where_clause};
                """,
                *params
            )
            next_event_query = """
                SELECT event_time
                FROM reminders
                WHERE event_time IS NOT NULL AND event_time >= NOW()
                """
            if guild_id is not None:
                next_event_query += " AND guild_id = $1"
                next_event_params = [guild_id]
            else:
                next_event_params = []
            next_event_query += " ORDER BY event_time ASC LIMIT 1;"

            next_event_row = await conn.fetchrow(next_event_query, *next_event_params)
            per_channel_query = "SELECT channel_id, COUNT(*) AS c FROM reminders"
            upcoming_query = """
                SELECT id, name, channel_id, event_time
                FROM reminders
                WHERE event_time IS NOT NULL AND event_time >= NOW()
                """

            if guild_id is not None:
                per_channel_query += " WHERE guild_id = $1 GROUP BY channel_id;"
                per_channel_params = [guild_id]
                upcoming_query += " AND guild_id = $1 ORDER BY event_time ASC LIMIT 3;"
                upcoming_params = [guild_id]
            else:
                per_channel_query += " GROUP BY channel_id;"
                per_channel_params = []
                upcoming_query += " ORDER BY event_time ASC LIMIT 3;"
                upcoming_params = []

            per_channel_rows = await conn.fetch(per_channel_query, *per_channel_params)
            upcoming_rows = await conn.fetch(upcoming_query, *upcoming_params)
    except pg_exceptions.UndefinedTableError:
        return default
    except Exception as exc:
        print("[WARN] reminder stats failed:", exc)
        return default

    if counts_row is None:
        return default

    per_channel = {
        str(row["channel_id"]): int(row["c"] or 0)
        for row in per_channel_rows or []
    }

    upcoming = [
        UpcomingReminder(
            id=int(row["id"]),
            name=row["name"],
            channel_id=int(row["channel_id"]),
            scheduled_time=_datetime_to_iso(row["event_time"]),
            is_recurring=False,
        )
        for row in upcoming_rows or []
    ]

    next_event_iso = (
        _datetime_to_iso(next_event_row["event_time"])
        if next_event_row and next_event_row["event_time"]
        else None
    )

    return ReminderStats(
        total=int(counts_row["total"] or 0),
        recurring=int(counts_row["recurring"] or 0),
        one_off=int(counts_row["one_off"] or 0),
        next_event_time=next_event_iso,
        per_channel=per_channel,
        upcoming=upcoming,
    )


def _format_duration_seconds(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: List[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return " ".join(parts)


async def _fetch_ticket_stats(guild_id: Optional[int] = None) -> TicketStats:
    """Fetch ticket statistics for dashboard."""
    default = TicketStats(
        total=0,
        per_status={},
        open_count=0,
        last_ticket_created_at=None,
        average_close_seconds=None,
        average_close_human=None,
        open_items=[],
    )
    global db_pool
    if db_pool is None:
        return default
    try:
        async with db_pool.acquire() as conn:
            where_clause = "WHERE guild_id = $1" if guild_id is not None else ""
            params = [guild_id] if guild_id is not None else []

            status_rows = await conn.fetch(
                f"SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS c FROM support_tickets {where_clause} GROUP BY status;",
                *params
            )

            last_query = f"SELECT created_at FROM support_tickets {where_clause} ORDER BY created_at DESC LIMIT 1;"
            last_row = await conn.fetchrow(last_query, *params)

            avg_where = where_clause + (" AND " if where_clause else " WHERE ") + "status = 'closed' AND updated_at IS NOT NULL"
            avg_row = await conn.fetchrow(
                f"SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) AS avg_s FROM support_tickets {avg_where};",
                *params
            )

            open_where = where_clause + (" AND " if where_clause else " WHERE ") + "status IS DISTINCT FROM 'closed'"
            open_rows = await conn.fetch(
                f"""
                SELECT id, username, status, channel_id, created_at
                FROM support_tickets
                {open_where}
                ORDER BY created_at ASC
                LIMIT 10;
                """,
                *params
            )
    except pg_exceptions.UndefinedTableError:
        return default
    except Exception as exc:
        print("[WARN] ticket stats failed:", exc)
        return default

    per_status = {str(row["status"]): int(row["c"] or 0) for row in status_rows}
    total = sum(per_status.values())
    open_count = per_status.get("open", 0)
    last_created_iso = (
        _datetime_to_iso(last_row["created_at"])
        if last_row and last_row["created_at"]
        else None
    )

    avg_seconds = None
    avg_human = None
    if avg_row and avg_row["avg_s"] is not None:
        try:
            avg_seconds = int(float(avg_row["avg_s"]))
        except (TypeError, ValueError):
            avg_seconds = None
        if avg_seconds is not None:
            avg_human = _format_duration_seconds(avg_seconds)

    open_items = [
        TicketListItem(
            id=int(row["id"]),
            username=row["username"],
            status=row["status"],
            channel_id=int(row["channel_id"]) if row["channel_id"] else None,
            created_at=_datetime_to_iso(row["created_at"]),
        )
        for row in open_rows or []
    ]

    return TicketStats(
        total=total,
        per_status=per_status,
        open_count=open_count,
        last_ticket_created_at=last_created_iso,
        average_close_seconds=avg_seconds,
        average_close_human=avg_human,
        open_items=open_items,
    )


async def _fetch_settings_overrides(guild_id: Optional[int] = None) -> List[SettingOverride]:
    """Fetch settings overrides for dashboard."""
    global db_pool
    if db_pool is None:
        return []
    try:
        async with db_pool.acquire() as conn:
            if guild_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT scope, key, value
                    FROM bot_settings
                    WHERE guild_id = $1
                    ORDER BY scope, key;
                    """,
                    guild_id
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT scope, key, value
                    FROM bot_settings
                    ORDER BY scope, key;
                    """
                )
    except pg_exceptions.UndefinedTableError:
        return []
    except Exception as exc:
        print("[WARN] settings overrides fetch failed:", exc)
        return []

    return [
        SettingOverride(scope=row["scope"], key=row["key"], value=str(row["value"]))
        for row in rows or []
    ]


async def _collect_infrastructure_metrics() -> InfrastructureMetrics:
    """Collect infrastructure metrics for dashboard."""
    checked_at = _datetime_to_iso(datetime.now(timezone.utc)) or ""
    global db_pool
    if db_pool is None:
        return InfrastructureMetrics(database_up=False, pool_size=None, checked_at=checked_at)

    database_up = False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("SELECT 1;")
            database_up = True
    except Exception as exc:
        print("[WARN] db health check failed:", exc)

    pool_size: Optional[int]
    try:
        pool_size = db_pool.get_size()
    except Exception:
        pool_size = None

    return InfrastructureMetrics(
        database_up=database_up,
        pool_size=pool_size,
        checked_at=checked_at,
    )


def _count_recent_events(events: List[GPTLogEvent], hours: int = 24) -> int:
    if not events:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count = 0
    for evt in events:
        ts = getattr(evt, "timestamp", None)
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        if dt >= cutoff:
            count += 1
    return count


def _calculate_status(bot_metrics: BotMetrics, gpt_errors_1h: int) -> str:
    """
    Calculate system status based on bot health (online status + GPT errors).
    This function is used consistently in both debug logs and persisted telemetry.
    
    Status logic:
    - outage: Bot offline (after startup grace period) OR >5 GPT errors/hour
    - degraded: Bot starting up (<2min) OR 1-5 GPT errors/hour
    - operational: Bot online and no recent GPT errors
    """
    if not bot_metrics.online:
        # If bot has been running for more than 2 minutes and goes offline, it's a real outage
        # (could be Railway/host issue, bot crash, etc.)
        if bot_metrics.uptime_seconds and bot_metrics.uptime_seconds >= 120:
            return "outage"  # Bot was running but went offline - real outage (host issue, crash, etc.)
        elif bot_metrics.uptime_seconds and bot_metrics.uptime_seconds < 120:
            return "degraded"  # Still starting up, give it time
        else:
            # No uptime data - bot might not have started yet, or truly offline
            # If we have guilds, bot was connected before, so likely an outage
            return "outage" if len(bot_metrics.guilds) > 0 else "degraded"
    elif gpt_errors_1h > 5:
        return "outage"  # Too many recent GPT errors
    elif gpt_errors_1h > 0:
        return "degraded"  # Some GPT errors, but not critical
    else:
        return "operational"  # Bot is online and no recent errors


async def _telemetry_ingest_loop(interval: int = 45) -> None:
    """
    Background task that periodically ingests telemetry data to Supabase.
    
    This function runs continuously, collecting metrics and writing them to
    telemetry.subsystem_snapshots every `interval` seconds.
    """
    logger.info(f"🚀 Telemetry ingest loop started (interval: {interval}s)")
    
    # Wait a bit before first run to allow app to fully start
    await asyncio.sleep(5)
    
    # Track if we've seen the bot online at least once
    bot_has_been_online = False
    
    while True:
        try:
            # Collect metrics
            snapshot = await get_bot_snapshot()
            bot_payload = serialize_snapshot(snapshot)
            bot_metrics = BotMetrics(
                version=__version__,
                codename=CODENAME,
                **bot_payload,
            )
            
            # Track if bot has been online at least once
            if bot_metrics.online:
                bot_has_been_online = True
            gpt_metrics = _collect_gpt_metrics()
            ticket_stats = await _fetch_ticket_stats()
            
            # Persist to Supabase
            await _persist_telemetry_snapshot(bot_metrics, gpt_metrics, ticket_stats)
            
            # Flush retry queue after successful write
            await _flush_telemetry_queue()
            
            # Log the calculated status for debugging (using same logic as _persist_telemetry_snapshot)
            # Status is based ONLY on bot health (online status + GPT errors), NOT on open tickets
            gpt_errors_1h = _count_recent_events(gpt_metrics.recent_errors, hours=1)
            calculated_status = _calculate_status(bot_metrics, gpt_errors_1h)
            
            logger.debug(
                f"✅ Telemetry snapshot ingested: bot_online={bot_metrics.online}, "
                f"status={calculated_status}, uptime={bot_metrics.uptime_seconds}s, "
                f"guilds={len(bot_metrics.guilds)}, gpt_errors_1h={gpt_errors_1h}, "
                f"open_tickets={ticket_stats.open_count} (tickets excluded from status)"
            )
            
        except asyncio.CancelledError:
            logger.info("🛑 Telemetry ingest loop cancelled")
            raise
        except Exception as exc:
            logger.warning(
                f"⚠️ Telemetry ingest failed (will retry): {exc.__class__.__name__}: {exc}",
                exc_info=True
            )
            # Continue loop even on error
        
        # Sleep for the configured interval before next iteration
        await asyncio.sleep(interval)


async def _flush_telemetry_queue() -> None:
    """Flush telemetry queue with exponential backoff retry."""
    global _telemetry_queue
    
    if not _telemetry_queue:
        return
    
    # Process queue (copy to avoid modification during iteration)
    queue_copy = _telemetry_queue.copy()
    _telemetry_queue.clear()
    
    for item in queue_copy:
        retry_count = item.get("retry_count", 0)
        if retry_count >= MAX_TELEMETRY_RETRIES:
            logger.debug(f"⚠️ Dropping telemetry snapshot after {MAX_TELEMETRY_RETRIES} retries")
            continue
        
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s
        backoff_seconds = 2 ** retry_count
        await asyncio.sleep(backoff_seconds)
        
        try:
            # Retry the write
            await _supabase_post(
                "subsystem_snapshots",
                item["payload"],
                upsert=True,
                schema="telemetry"
            )
            logger.debug(f"✅ Telemetry snapshot retry succeeded (attempt {retry_count + 1})")
            # Success - don't re-queue
        except Exception as retry_error:
            # Still failed - increment retry count and re-queue
            item["retry_count"] = retry_count + 1
            if len(_telemetry_queue) < MAX_TELEMETRY_QUEUE_SIZE:
                _telemetry_queue.append(item)
            else:
                # Queue full - drop oldest
                _telemetry_queue.pop(0)
                _telemetry_queue.append(item)
            logger.debug(f"⚠️ Telemetry retry {retry_count + 1}/{MAX_TELEMETRY_RETRIES} failed: {retry_error}")


async def _persist_telemetry_snapshot(
    bot_metrics: BotMetrics,
    gpt_metrics: GPTMetrics,
    ticket_stats: TicketStats,
) -> None:
    """
    Persist telemetry snapshot to Supabase using REST API.
    
    Note: Telemetry data MUST go to Supabase, not to the local PostgreSQL database.
    The local PostgreSQL on Railway is only for reminders, tickets, etc.
    """
    # Collect metrics
    command_events_24h = 0
    global db_pool
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                try:
                    command_events_24h = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM audit_logs
                        WHERE created_at >= timezone('utc', now()) - interval '24 hours'
                        """
                    )
                    if command_events_24h is None:
                        command_events_24h = 0
                except pg_exceptions.UndefinedTableError:
                    command_events_24h = 0
                except Exception as exc:
                    logger.debug(f"Telemetry audit count failed (non-critical): {exc}")
                    command_events_24h = 0
        except Exception:
            command_events_24h = 0

    gpt_successes_24h = _count_recent_events(gpt_metrics.recent_successes)
    gpt_errors_24h = _count_recent_events(gpt_metrics.recent_errors)

    total_activity_24h = int(command_events_24h + gpt_successes_24h + gpt_errors_24h)

    error_rate = 0.0
    if gpt_successes_24h + gpt_errors_24h > 0:
        error_rate = round(
            gpt_errors_24h / float(gpt_successes_24h + gpt_errors_24h), 2
        )

    # Safely handle latency_ms - check for NaN and None
    latency_ms_raw = bot_metrics.latency_ms
    if latency_ms_raw is None or (isinstance(latency_ms_raw, float) and math.isnan(latency_ms_raw)):
        latency_ms = 0.0
    else:
        latency_ms = float(latency_ms_raw)
    
    latency_p50 = int(latency_ms) if not math.isnan(latency_ms) else 0
    latency_p95 = int(round(latency_ms * 1.5)) if not math.isnan(latency_ms) else 0

    # throughput_per_minute should be integer according to schema
    throughput_per_minute = 0
    if total_activity_24h:
        throughput_per_minute = int(round(total_activity_24h / (24 * 60)))

    queue_depth = ticket_stats.open_count
    active_bots = len(bot_metrics.guilds) or None

    # Only count recent GPT errors (last hour) for status, not all 24h errors
    # Old errors shouldn't keep the system in degraded state
    # NOTE: Open tickets are NOT an indicator of bot health - they're normal business operations
    gpt_errors_1h = _count_recent_events(gpt_metrics.recent_errors, hours=1)
    
    # Status is based ONLY on technical health: bot online status and GPT errors
    # Open tickets are excluded - they're a normal part of ticket bot functionality
    # Use the same calculation function as debug logs for consistency
    status = _calculate_status(bot_metrics, gpt_errors_1h)

    notes = (
        f"{total_activity_24h} events/24h · {ticket_stats.open_count} open tickets · "
        f"GPT errors 24h: {gpt_errors_24h}"
    )

    # Use Supabase REST API - this is the ONLY way to write telemetry
    # Note: Make sure 'telemetry' schema is exposed in Supabase Studio → Settings → API → Exposed Schemas
    # Send only the essential fields that we have data for, matching the database schema types:
    # - int4: uptime_seconds, throughput_per_minute, latency_p50, latency_p95, queue_depth, active_bots
    # - numeric: error_rate
    # - text: subsystem, label, status, notes
    # - timestamptz: last_updated, computed_at
    payload: Dict[str, Any] = {
        "subsystem": "alphapy",
        "label": "Alphapy Agents",
        "status": status,
        "uptime_seconds": int(bot_metrics.uptime_seconds or 0),
        "throughput_per_minute": int(throughput_per_minute),
        "error_rate": float(error_rate),
        "latency_p50": int(latency_p50),
        "latency_p95": int(latency_p95),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Add optional fields only if we have values
    if queue_depth is not None:
        payload["queue_depth"] = int(queue_depth)
    if active_bots is not None:
        payload["active_bots"] = int(active_bots)
    if notes:
        payload["notes"] = notes
    
    try:
        # Use schema parameter for Supabase REST API with custom schema
        # This will use Accept-Profile header to specify the telemetry schema
        await _supabase_post("subsystem_snapshots", payload, upsert=True, schema="telemetry")
        logger.debug("✅ Telemetry snapshot written to Supabase via REST API")
    except SupabaseConfigurationError as exc:
        logger.warning(
            f"⚠️ Cannot write telemetry to Supabase: {exc}. "
            "Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are configured."
        )
        # Don't queue configuration errors - they won't resolve by retrying
    except Exception as exc:
        logger.warning(
            f"⚠️ Failed to write telemetry to Supabase: {exc.__class__.__name__}: {exc}. "
            "Adding to retry queue."
        )
        # Add to retry queue
        global _telemetry_queue
        if len(_telemetry_queue) < MAX_TELEMETRY_QUEUE_SIZE:
            _telemetry_queue.append({
                "payload": payload,
                "retry_count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Queue full - drop oldest
            _telemetry_queue.pop(0)
            _telemetry_queue.append({
                "payload": payload,
                "retry_count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })


@router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    guild_id: Optional[int] = None,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    snapshot = await get_bot_snapshot()
    bot_payload = serialize_snapshot(snapshot)
    bot_metrics = BotMetrics(
        version=__version__,
        codename=CODENAME,
        **bot_payload,
    )
    gpt_metrics = _collect_gpt_metrics()
    # Guild filtering implemented for security - only shows data for specified guild
    reminder_stats = await _fetch_reminder_stats(guild_id)
    ticket_stats = await _fetch_ticket_stats(guild_id)
    infrastructure = await _collect_infrastructure_metrics()

    # Persist a telemetry snapshot asynchronously; ignore failures.
    asyncio.create_task(_persist_telemetry_snapshot(bot_metrics, gpt_metrics, ticket_stats))

    return DashboardMetrics(
        bot=bot_metrics,
        gpt=gpt_metrics,
        reminders=reminder_stats,
        tickets=ticket_stats,
        # Guild filtering implemented for security - only shows settings for specified guild
        settings_overrides=await _fetch_settings_overrides(guild_id),
        infrastructure=infrastructure,
    )


# Alias voor Mind monitoring systeem - verwacht /api/metrics
@router.get("/metrics", response_model=DashboardMetrics)
async def get_metrics(
    guild_id: Optional[int] = None,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Alias endpoint voor Mind monitoring systeem"""
    return await get_dashboard_metrics(guild_id, auth_user_id)


# ---------------------------------------------------------------------------
# Reminder REST endpoints (existing behaviour)
# ---------------------------------------------------------------------------


class Reminder(BaseModel):
    id: int
    name: str
    time: str  # of `datetime.time` als je deze exact gebruikt
    days: List[str]
    message: str
    channel_id: int
    user_id: str  # ← belangrijk: moet overeenkomen met je response (created_by)


@router.get("/reminders/{user_id}", response_model=List[Reminder])
async def get_user_reminders(user_id: str, auth_user_id: str = Depends(get_authenticated_user_id)):
    if auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        async with db_pool.acquire() as conn:
            rows = await get_reminders_for_user(conn, user_id)
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "time": r["time"].strftime("%H:%M"),
                "days": r["days"],
                "message": r["message"],
                "channel_id": r["channel_id"],
                "user_id": str(r["created_by"]),
            }
            for r in rows
        ]
    except Exception as exc:
        print("[ERROR] Failed to get reminders:", exc)
        return []


@router.post("/reminders")
async def add_reminder(reminder: Reminder, auth_user_id: str = Depends(get_authenticated_user_id)):
    global db_pool
    payload = reminder.dict()
    payload["created_by"] = payload.pop("user_id")
    if payload["created_by"] != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    async with db_pool.acquire() as conn:
        await create_reminder(conn, payload)
    return {"success": True}


@router.put("/reminders")
async def edit_reminder(reminder: Reminder, auth_user_id: str = Depends(get_authenticated_user_id)):
    global db_pool
    payload = reminder.dict()
    payload["created_by"] = payload.pop("user_id")
    if payload["created_by"] != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    async with db_pool.acquire() as conn:
        await update_reminder(conn, payload)
    return {"success": True}


@router.delete("/reminders/{reminder_id}/{created_by}")
async def remove_reminder(reminder_id: str, created_by: str, auth_user_id: str = Depends(get_authenticated_user_id)):
    if created_by != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    async with db_pool.acquire() as conn:
        await delete_reminder(conn, int(reminder_id), created_by)
    return {"success": True}


# ---------------------------------------------------------------------------
# Settings Management Endpoints (Web Configuration Interface)
# ---------------------------------------------------------------------------

class GuildSettingsResponse(BaseModel):
    system: Dict[str, Any] = {}
    reminders: Dict[str, Any] = {}
    embedwatcher: Dict[str, Any] = {}
    gpt: Dict[str, Any] = {}
    invites: Dict[str, Any] = {}
    gdpr: Dict[str, Any] = {}


class UpdateSettingsRequest(BaseModel):
    category: str
    settings: Dict[str, Any]


async def verify_guild_admin_access(
    guild_id: int,
    request: Request,
) -> None:
    """Verify that the authenticated user has admin access to the specified guild."""
    # This would need to be implemented with Discord API calls to verify permissions
    # For now, we'll rely on frontend validation and API key auth
    pass


@router.get("/dashboard/settings/{guild_id}", response_model=GuildSettingsResponse)
async def get_guild_settings(
    guild_id: int,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Get all settings for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Fetch all settings for this guild
            rows = await conn.fetch(
                """
                SELECT scope, key, value
                FROM bot_settings
                WHERE guild_id = $1
                ORDER BY scope, key;
                """,
                guild_id
            )

            # Organize settings by category
            settings = {
                'system': {},
                'reminders': {},
                'embedwatcher': {},
                'gpt': {},
                'invites': {},
                'gdpr': {}
            }

            for row in rows:
                scope = row['scope']
                key = row['key']
                value = row['value']

                # Convert string values back to appropriate types
                if scope in settings:
                    if key in ['allow_everyone_mentions']:
                        settings[scope][key] = value.lower() == 'true'
                    elif key in ['embed_watcher_offset_hours', 'max_tokens']:
                        try:
                            settings[scope][key] = int(value)
                        except ValueError:
                            settings[scope][key] = value
                    else:
                        settings[scope][key] = value

            return GuildSettingsResponse(**settings)

    except Exception as exc:
        print("[ERROR] Failed to get guild settings:", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch settings")


@router.post("/dashboard/settings/{guild_id}")
async def update_guild_settings(
    guild_id: int,
    request: UpdateSettingsRequest,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Update settings for a specific guild category."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Validate category
    valid_categories = ['system', 'reminders', 'embedwatcher', 'gpt', 'invites', 'gdpr']
    if request.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category: {request.category}")

    try:
        async with db_pool.acquire() as conn:
            # Start transaction
            async with conn.transaction():
                # First, delete existing settings for this category
                await conn.execute(
                    """
                    DELETE FROM bot_settings
                    WHERE guild_id = $1 AND scope = $2;
                    """,
                    guild_id, request.category
                )

                # Insert new settings
                for key, value in request.settings.items():
                    if value is not None and value != "":
                        await conn.execute(
                            """
                            INSERT INTO bot_settings (guild_id, scope, key, value)
                            VALUES ($1, $2, $3, $4);
                            """,
                            guild_id, request.category, key, str(value)
                        )

            return {"success": True, "message": f"Updated {request.category} settings"}

    except Exception as exc:
        print("[ERROR] Failed to update guild settings:", exc)
        raise HTTPException(status_code=500, detail="Failed to update settings")


# ---------------------------------------------------------------------------
# Onboarding Questions & Rules Management Endpoints (Web Configuration Interface)
# ---------------------------------------------------------------------------

class OnboardingQuestion(BaseModel):
    id: Optional[int] = None
    question: str
    question_type: Literal['select', 'multiselect', 'text', 'email']
    options: Optional[List[Dict[str, str]]] = None  # [{"label": "Option 1", "value": "value1"}]
    followup: Optional[Dict[str, Any]] = None  # {"value": {"question": "Followup question"}}
    required: bool = True
    enabled: bool = True
    step_order: int

class OnboardingRule(BaseModel):
    id: Optional[int] = None
    title: str
    description: str
    enabled: bool = True
    rule_order: int


@router.get("/dashboard/{guild_id}/onboarding/questions", response_model=List[OnboardingQuestion])
async def get_guild_onboarding_questions(
    guild_id: int,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Get all onboarding questions for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, step_order, question, question_type, options, followup, required, enabled
                FROM guild_onboarding_questions
                WHERE guild_id = $1 AND enabled = TRUE
                ORDER BY step_order
                """,
                guild_id
            )

            questions = []
            for row in rows:
                questions.append(OnboardingQuestion(
                    id=row["id"],
                    question=row["question"],
                    question_type=row["question_type"],
                    options=row["options"],
                    followup=row["followup"],
                    required=row["required"],
                    enabled=row["enabled"],
                    step_order=row["step_order"]
                ))

            return questions

    except Exception as exc:
        print("[ERROR] Failed to get guild onboarding questions:", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch questions")


@router.post("/dashboard/{guild_id}/onboarding/questions")
async def save_guild_onboarding_question(
    guild_id: int,
    question: OnboardingQuestion,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Save or update an onboarding question for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_onboarding_questions
                (guild_id, step_order, question, question_type, options, followup, required, enabled)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (guild_id, step_order)
                DO UPDATE SET
                    question = EXCLUDED.question,
                    question_type = EXCLUDED.question_type,
                    options = EXCLUDED.options,
                    followup = EXCLUDED.followup,
                    required = EXCLUDED.required,
                    enabled = EXCLUDED.enabled,
                    updated_at = CURRENT_TIMESTAMP
                """,
                guild_id,
                question.step_order,
                question.question,
                question.question_type,
                question.options,
                question.followup,
                question.required,
                question.enabled
            )

            return {"success": True, "message": "Question saved successfully"}

    except Exception as exc:
        print("[ERROR] Failed to save onboarding question:", exc)
        raise HTTPException(status_code=500, detail="Failed to save question")


@router.delete("/dashboard/{guild_id}/onboarding/questions/{question_id}")
async def delete_guild_onboarding_question(
    guild_id: int,
    question_id: int,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Delete an onboarding question for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM guild_onboarding_questions WHERE guild_id = $1 AND id = $2",
                guild_id, question_id
            )

            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Question not found")

            return {"success": True, "message": "Question deleted successfully"}

    except HTTPException:
        raise
    except Exception as exc:
        print("[ERROR] Failed to delete onboarding question:", exc)
        raise HTTPException(status_code=500, detail="Failed to delete question")


@router.get("/dashboard/{guild_id}/onboarding/rules", response_model=List[OnboardingRule])
async def get_guild_onboarding_rules(
    guild_id: int,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Get all onboarding rules for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, rule_order, title, description, enabled
                FROM guild_rules
                WHERE guild_id = $1 AND enabled = TRUE
                ORDER BY rule_order
                """,
                guild_id
            )

            rules = []
            for row in rows:
                rules.append(OnboardingRule(
                    id=row["id"],
                    title=row["title"],
                    description=row["description"],
                    enabled=row["enabled"],
                    rule_order=row["rule_order"]
                ))

            return rules

    except Exception as exc:
        print("[ERROR] Failed to get guild onboarding rules:", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch rules")


@router.post("/dashboard/{guild_id}/onboarding/rules")
async def save_guild_onboarding_rule(
    guild_id: int,
    rule: OnboardingRule,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Save or update an onboarding rule for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_rules
                (guild_id, rule_order, title, description, enabled)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, rule_order)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    enabled = EXCLUDED.enabled,
                    updated_at = CURRENT_TIMESTAMP
                """,
                guild_id,
                rule.rule_order,
                rule.title,
                rule.description,
                rule.enabled
            )

            return {"success": True, "message": "Rule saved successfully"}

    except Exception as exc:
        print("[ERROR] Failed to save onboarding rule:", exc)
        raise HTTPException(status_code=500, detail="Failed to save rule")


@router.delete("/dashboard/{guild_id}/onboarding/rules/{rule_id}")
async def delete_guild_onboarding_rule(
    guild_id: int,
    rule_id: int,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Delete an onboarding rule for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM guild_rules WHERE guild_id = $1 AND id = $2",
                guild_id, rule_id
            )

            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Rule not found")

            return {"success": True, "message": "Rule deleted successfully"}

    except HTTPException:
        raise
    except Exception as exc:
        print("[ERROR] Failed to delete onboarding rule:", exc)
        raise HTTPException(status_code=500, detail="Failed to delete rule")


class ReorderRequest(BaseModel):
    questions: Optional[List[int]] = None
    rules: Optional[List[int]] = None

@router.post("/dashboard/{guild_id}/onboarding/reorder")
async def reorder_onboarding_items(
    guild_id: int,
    request: ReorderRequest,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Reorder onboarding questions and rules."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Update question order
                if request.questions:
                    for i, question_id in enumerate(request.questions):
                        await conn.execute(
                            "UPDATE guild_onboarding_questions SET step_order = $1 WHERE guild_id = $2 AND id = $3",
                            i + 1, guild_id, question_id
                        )

                # Update rule order
                if request.rules:
                    for i, rule_id in enumerate(request.rules):
                        await conn.execute(
                            "UPDATE guild_rules SET rule_order = $1 WHERE guild_id = $2 AND id = $3",
                            i + 1, guild_id, rule_id
                        )

            return {"success": True, "message": "Order updated successfully"}

    except Exception as exc:
        print("[ERROR] Failed to reorder onboarding items:", exc)
        raise HTTPException(status_code=500, detail="Failed to reorder items")


# ---------------------------------------------------------------------------
# Settings History Endpoints (Web Configuration Interface)
# ---------------------------------------------------------------------------

class SettingsHistoryEntry(BaseModel):
    id: int
    scope: str
    key: str
    old_value: Optional[Any] = None
    new_value: Any
    value_type: Optional[str] = None
    changed_by: Optional[int] = None
    changed_at: str
    change_type: Literal['created', 'updated', 'deleted', 'rollback']


@router.get("/dashboard/{guild_id}/settings/history", response_model=List[SettingsHistoryEntry])
async def get_settings_history(
    guild_id: int,
    scope: Optional[str] = None,
    key: Optional[str] = None,
    limit: int = 50,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Get settings change history for a specific guild."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            if scope and key:
                query = """
                    SELECT id, scope, key, old_value, new_value, value_type, changed_by, changed_at, change_type
                    FROM settings_history
                    WHERE guild_id = $1 AND scope = $2 AND key = $3
                    ORDER BY changed_at DESC LIMIT $4
                """
                params = [guild_id, scope, key, limit]
            elif scope:
                query = """
                    SELECT id, scope, key, old_value, new_value, value_type, changed_by, changed_at, change_type
                    FROM settings_history
                    WHERE guild_id = $1 AND scope = $2
                    ORDER BY changed_at DESC LIMIT $3
                """
                params = [guild_id, scope, limit]
            else:
                query = """
                    SELECT id, scope, key, old_value, new_value, value_type, changed_by, changed_at, change_type
                    FROM settings_history
                    WHERE guild_id = $1
                    ORDER BY changed_at DESC LIMIT $2
                """
                params = [guild_id, limit]

            rows = await conn.fetch(query, *params)

            history = []
            for row in rows:
                history.append(SettingsHistoryEntry(
                    id=row["id"],
                    scope=row["scope"],
                    key=row["key"],
                    old_value=row["old_value"],
                    new_value=row["new_value"],
                    value_type=row["value_type"],
                    changed_by=row["changed_by"],
                    changed_at=row["changed_at"].isoformat(),
                    change_type=row["change_type"]
                ))

            return history

    except Exception as exc:
        print("[ERROR] Failed to get settings history:", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch settings history")


@router.post("/dashboard/{guild_id}/settings/rollback/{history_id}")
async def rollback_setting_change(
    guild_id: int,
    history_id: int,
    auth_user_id: str = Depends(get_authenticated_user_id)
):
    """Rollback a setting to a previous value from history."""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Get the history entry
            history_row = await conn.fetchrow(
                """
                SELECT scope, key, old_value, change_type, value_type
                FROM settings_history
                WHERE id = $1 AND guild_id = $2
                """,
                history_id, guild_id
            )

            if not history_row:
                raise HTTPException(status_code=404, detail="History entry not found")

            scope: str = history_row["scope"]
            key: str = history_row["key"]
            old_value: Any = history_row["old_value"]
            change_type: str = history_row["change_type"]

            # Only allow rollback for updated entries with old values
            if change_type != "updated" or old_value is None:
                raise HTTPException(status_code=400, detail="Cannot rollback this type of change")

            # Update the setting back to the old value
            await conn.execute(
                """
                UPDATE bot_settings
                SET value = $1, updated_by = $2, updated_at = NOW()
                WHERE guild_id = $3 AND scope = $4 AND key = $5
                """,
                old_value, int(auth_user_id), guild_id, scope, key
            )

            # Record the rollback in history
            await conn.execute(
                """
                INSERT INTO settings_history
                (guild_id, scope, key, old_value, new_value, value_type, changed_by, change_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'rollback')
                """,
                guild_id, scope, key, history_row["old_value"], old_value,
                history_row["value_type"], int(auth_user_id)
            )

            return {"success": True, "message": f"Rolled back {scope}.{key} to previous value"}

    except HTTPException:
        raise
    except Exception as exc:
        print("[ERROR] Failed to rollback setting:", exc)
        raise HTTPException(status_code=500, detail="Failed to rollback setting")


app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
