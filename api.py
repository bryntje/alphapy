import asyncio
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
from webhooks.supabase import router as supabase_webhook_router
from version import CODENAME, __version__

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global db_pool
    db_pool = await asyncpg.create_pool(config.DATABASE_URL)
    print("✅ DB pool created")
    try:
        yield
    finally:
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


async def _persist_telemetry_snapshot(
    bot_metrics: BotMetrics,
    gpt_metrics: GPTMetrics,
    ticket_stats: TicketStats,
) -> None:
    global db_pool
    if db_pool is None:
        return

    try:
        async with db_pool.acquire() as conn:
            command_events_24h = 0
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
            except Exception as exc:
                print("[WARN] telemetry audit count failed:", exc)
                command_events_24h = 0

            gpt_successes_24h = _count_recent_events(gpt_metrics.recent_successes)
            gpt_errors_24h = _count_recent_events(gpt_metrics.recent_errors)

            total_activity_24h = int(command_events_24h + gpt_successes_24h + gpt_errors_24h)

            error_rate = 0.0
            if gpt_successes_24h + gpt_errors_24h > 0:
                error_rate = round(
                    gpt_errors_24h / float(gpt_successes_24h + gpt_errors_24h), 2
                )

            latency_ms = bot_metrics.latency_ms or 0.0
            latency_p50 = int(latency_ms or 0)
            latency_p95 = int(round((latency_ms or 0) * 1.5))

            throughput_per_minute = 0.0
            if total_activity_24h:
                throughput_per_minute = round(total_activity_24h / (24 * 60), 2)

            queue_depth = ticket_stats.open_count
            active_bots = len(bot_metrics.guilds) or None

            incidents_open = ticket_stats.open_count + gpt_errors_24h
            if not bot_metrics.online:
                status = "outage"
            elif incidents_open > 5:
                status = "outage"
            elif incidents_open > 0:
                status = "degraded"
            else:
                status = "operational"

            notes = (
                f"{total_activity_24h} events/24h · {ticket_stats.open_count} open tickets · "
                f"GPT errors 24h: {gpt_errors_24h}"
            )

            await conn.execute(
                """
                insert into telemetry.subsystem_snapshots (
                    subsystem,
                    label,
                    status,
                    uptime_seconds,
                    throughput_per_minute,
                    error_rate,
                    latency_p50,
                    latency_p95,
                    queue_depth,
                    active_bots,
                    notes,
                    last_updated
                )
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, timezone('utc', now()))
                on conflict (subsystem) do update set
                    label = excluded.label,
                    status = excluded.status,
                    uptime_seconds = excluded.uptime_seconds,
                    throughput_per_minute = excluded.throughput_per_minute,
                    error_rate = excluded.error_rate,
                    latency_p50 = excluded.latency_p50,
                    latency_p95 = excluded.latency_p95,
                    queue_depth = excluded.queue_depth,
                    active_bots = excluded.active_bots,
                    notes = excluded.notes,
                    last_updated = excluded.last_updated
                """,
                "alphapy",
                "Alphapy Agents",
                status,
                bot_metrics.uptime_seconds or 0,
                throughput_per_minute,
                error_rate,
                latency_p50,
                latency_p95,
                queue_depth,
                active_bots,
                notes,
            )
    except Exception as exc:
        print("[WARN] telemetry snapshot failed:", exc)


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
