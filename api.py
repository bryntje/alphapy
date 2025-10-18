import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

import asyncpg
from asyncpg import exceptions as pg_exceptions
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
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
from version import CODENAME, __version__

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Guard routes with an optional API key."""
    configured_key = getattr(config, "API_KEY", None)
    if configured_key and x_api_key != configured_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def get_authenticated_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-Id header")
    return x_user_id


# ---------------------------------------------------------------------------
# FastAPI app bootstrap
# ---------------------------------------------------------------------------

db_pool: Optional[asyncpg.Pool] = None
router = APIRouter(prefix="/api", dependencies=[Depends(verify_api_key)])


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/health", response_model=HealthStatus, include_in_schema=False)
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


async def _fetch_reminder_stats() -> ReminderStats:
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
            counts_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE COALESCE(array_length(days, 1), 0) > 0) AS recurring,
                    COUNT(*) FILTER (WHERE COALESCE(array_length(days, 1), 0) = 0) AS one_off
                FROM reminders;
                """
            )
            next_event_row = await conn.fetchrow(
                """
                SELECT event_time
                FROM reminders
                WHERE event_time IS NOT NULL AND event_time >= NOW()
                ORDER BY event_time ASC
                LIMIT 1;
                """
            )
            per_channel_rows = await conn.fetch(
                "SELECT channel_id, COUNT(*) AS c FROM reminders GROUP BY channel_id;"
            )
            upcoming_rows = await conn.fetch(
                """
                SELECT id, name, channel_id, event_time
                FROM reminders
                WHERE event_time IS NOT NULL AND event_time >= NOW()
                ORDER BY event_time ASC
                LIMIT 3;
                """
            )
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


async def _fetch_ticket_stats() -> TicketStats:
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
            status_rows = await conn.fetch(
                "SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS c FROM support_tickets GROUP BY status;"
            )
            last_row = await conn.fetchrow(
                "SELECT created_at FROM support_tickets ORDER BY created_at DESC LIMIT 1;"
            )
            avg_row = await conn.fetchrow(
                """
                SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) AS avg_s
                FROM support_tickets
                WHERE status = 'closed' AND updated_at IS NOT NULL;
                """
            )
            open_rows = await conn.fetch(
                """
                SELECT id, username, status, channel_id, created_at
                FROM support_tickets
                WHERE status IS DISTINCT FROM 'closed'
                ORDER BY created_at ASC
                LIMIT 10;
                """
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


async def _fetch_settings_overrides() -> List[SettingOverride]:
    global db_pool
    if db_pool is None:
        return []
    try:
        async with db_pool.acquire() as conn:
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


@router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(auth_user_id: str = Depends(get_authenticated_user_id)):
    snapshot = await get_bot_snapshot()
    bot_payload = serialize_snapshot(snapshot)
    bot_metrics = BotMetrics(
        version=__version__,
        codename=CODENAME,
        **bot_payload,
    )
    return DashboardMetrics(
        bot=bot_metrics,
        gpt=_collect_gpt_metrics(),
        reminders=await _fetch_reminder_stats(),
        tickets=await _fetch_ticket_stats(),
        settings_overrides=await _fetch_settings_overrides(),
        infrastructure=await _collect_infrastructure_metrics(),
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


app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
