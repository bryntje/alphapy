"""
Reminder Repository

All SQL for the reminders table lives here. Cogs and API handlers
acquire a connection via acquire_safe() and pass it in — this module
owns only the queries, not the pool or error handling.
"""

from datetime import date, time
from typing import Any, Dict, List, Optional

import asyncpg


async def create(
    conn: asyncpg.Connection,
    guild_id: int,
    name: str,
    channel_id: int,
    reminder_time: time,
    call_time: Optional[time],
    days: List[str],
    message: Optional[str],
    created_by: int,
    origin_channel_id: Optional[int] = None,
    origin_message_id: Optional[int] = None,
    event_time: Optional[Any] = None,
    image_url: Optional[str] = None,
    location: Optional[str] = None,
) -> int:
    """Insert a new reminder and return its id."""
    return await conn.fetchval(
        """
        INSERT INTO reminders
            (guild_id, name, channel_id, time, call_time, days, message,
             created_by, origin_channel_id, origin_message_id, event_time, image_url, location)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        RETURNING id
        """,
        guild_id, name, channel_id, reminder_time, call_time, days or [],
        message, created_by, origin_channel_id, origin_message_id,
        event_time, image_url, location,
    )


async def get_by_id(
    conn: asyncpg.Connection,
    guild_id: int,
    reminder_id: int,
) -> Optional[asyncpg.Record]:
    """Fetch a reminder by id (admin — any owner)."""
    return await conn.fetchrow(
        "SELECT * FROM reminders WHERE id = $1 AND guild_id = $2",
        reminder_id, guild_id,
    )


async def get_by_id_for_user(
    conn: asyncpg.Connection,
    guild_id: int,
    reminder_id: int,
    user_id: int,
) -> Optional[asyncpg.Record]:
    """Fetch a reminder by id restricted to its owner."""
    return await conn.fetchrow(
        "SELECT * FROM reminders WHERE id = $1 AND guild_id = $2 AND created_by = $3",
        reminder_id, guild_id, user_id,
    )


async def delete(
    conn: asyncpg.Connection,
    guild_id: int,
    reminder_id: int,
) -> None:
    """Delete a reminder by id (admin — any owner)."""
    await conn.execute(
        "DELETE FROM reminders WHERE id = $1 AND guild_id = $2",
        reminder_id, guild_id,
    )


async def delete_by_owner(
    conn: asyncpg.Connection,
    reminder_id: int,
    created_by: Any,
) -> None:
    """Delete a reminder restricted to its owner (used by FastAPI)."""
    await conn.execute(
        "DELETE FROM reminders WHERE id = $1 AND created_by = $2",
        reminder_id, created_by,
    )


async def list_for_guild(
    conn: asyncpg.Connection,
    guild_id: int,
) -> List[asyncpg.Record]:
    """List all reminders for a guild (admin view)."""
    return await conn.fetch(
        """
        SELECT id, name, time, call_time, days, event_time, location, message, channel_id
        FROM reminders
        WHERE guild_id = $1
        ORDER BY COALESCE(call_time, time) ASC, name ASC
        """,
        guild_id,
    )


async def list_for_user(
    conn: asyncpg.Connection,
    guild_id: int,
    user_id: int,
    channel_id: int,
) -> List[asyncpg.Record]:
    """List reminders visible to a non-admin user (owns or in their channel)."""
    return await conn.fetch(
        """
        SELECT id, name, time, call_time, days, event_time, location, message, channel_id
        FROM reminders
        WHERE guild_id = $1 AND (created_by = $2 OR channel_id = $3)
        ORDER BY COALESCE(call_time, time) ASC, name ASC
        """,
        guild_id, user_id, channel_id,
    )


async def list_active(
    conn: asyncpg.Connection,
    current_time_obj: time,
    current_date: date,
    current_day: str,
    is_late_night: bool,
    next_date: date,
    next_day: str,
) -> List[asyncpg.Record]:
    """
    Fetch reminders that should fire at the current minute.

    Parameters: $1/$4=current_time_obj, $2=current_date, $3=current_day,
    $5=is_late_night, $6=next_date, $7=next_day.

    Three cases:
    - One-off T-60: time col = reminder time, matched by event date
    - One-off T0:   call_time col = event time
    - Recurring:    time col matches weekday (including midnight edge case)
    """
    return await conn.fetch(
        """
        SELECT id, guild_id, channel_id, name, message, location,
               origin_channel_id, origin_message_id, event_time, days, call_time,
               last_sent_at, image_url, sent_message_id
        FROM reminders
        WHERE (
            -- One-off at T-60: time col = reminder time, matches event date
            (
                event_time IS NOT NULL
                AND time::time = $1::time
                AND (
                    ((event_time AT TIME ZONE 'Europe/Brussels') - INTERVAL '60 minutes')::date = $2
                    OR
                    ($5 = true AND (event_time AT TIME ZONE 'Europe/Brussels')::date = $6)
                )
            )
            OR
            -- One-off at T0: call_time col = event time
            (
                event_time IS NOT NULL
                AND call_time::time = $4::time
                AND (event_time AT TIME ZONE 'Europe/Brussels')::date = $2
            )
            OR
            -- Recurring: time col matches current weekday+time
            (
                event_time IS NULL
                AND time::time = $1::time
                AND (
                    (
                        $3 = ANY(days)
                        OR EXISTS (
                            SELECT 1 FROM unnest(days) AS day_val
                            WHERE day_val::text IN ('ma', 'maandag', 'monday', 'di', 'dinsdag', 'tuesday',
                                                    'wo', 'woe', 'woensdag', 'wednesday', 'do', 'donderdag', 'thursday',
                                                    'vr', 'vrijdag', 'friday', 'za', 'zaterdag', 'saturday',
                                                    'zo', 'zondag', 'sunday')
                            AND (
                                ($3 = '0' AND day_val::text IN ('ma', 'maandag', 'monday'))
                                OR ($3 = '1' AND day_val::text IN ('di', 'dinsdag', 'tuesday'))
                                OR ($3 = '2' AND day_val::text IN ('wo', 'woe', 'woensdag', 'wednesday'))
                                OR ($3 = '3' AND day_val::text IN ('do', 'donderdag', 'thursday'))
                                OR ($3 = '4' AND day_val::text IN ('vr', 'vrijdag', 'friday'))
                                OR ($3 = '5' AND day_val::text IN ('za', 'zaterdag', 'saturday'))
                                OR ($3 = '6' AND day_val::text IN ('zo', 'zondag', 'sunday'))
                            )
                        )
                    )
                    OR
                    -- Midnight edge case: reminder at 23:xx, check next day
                    (
                        $5 = true
                        AND (
                            $7 = ANY(days)
                            OR EXISTS (
                                SELECT 1 FROM unnest(days) AS day_val
                                WHERE day_val::text IN ('ma', 'maandag', 'monday', 'di', 'dinsdag', 'tuesday',
                                                        'wo', 'woe', 'woensdag', 'wednesday', 'do', 'donderdag', 'thursday',
                                                        'vr', 'vrijdag', 'friday', 'za', 'zaterdag', 'saturday',
                                                        'zo', 'zondag', 'sunday')
                                AND (
                                    ($7 = '0' AND day_val::text IN ('ma', 'maandag', 'monday'))
                                    OR ($7 = '1' AND day_val::text IN ('di', 'dinsdag', 'tuesday'))
                                    OR ($7 = '2' AND day_val::text IN ('wo', 'woe', 'woensdag', 'wednesday'))
                                    OR ($7 = '3' AND day_val::text IN ('do', 'donderdag', 'thursday'))
                                    OR ($7 = '4' AND day_val::text IN ('vr', 'vrijdag', 'friday'))
                                    OR ($7 = '5' AND day_val::text IN ('za', 'zaterdag', 'saturday'))
                                    OR ($7 = '6' AND day_val::text IN ('zo', 'zondag', 'sunday'))
                                )
                            )
                        )
                    )
                )
            )
        )
        """,
        current_time_obj, current_date, current_day, current_time_obj,
        is_late_night, next_date, next_day,
    )


async def update_sent_at(
    conn: asyncpg.Connection,
    reminder_id: int,
    guild_id: int,
    last_sent_at: Any,
    sent_message_id: Optional[int] = None,
) -> None:
    """Update the idempotency marker after a reminder fires."""
    if sent_message_id is not None:
        await conn.execute(
            "UPDATE reminders SET last_sent_at = $1, sent_message_id = $2 WHERE id = $3 AND guild_id = $4",
            last_sent_at, sent_message_id, reminder_id, guild_id,
        )
    else:
        await conn.execute(
            "UPDATE reminders SET last_sent_at = $1 WHERE id = $2 AND guild_id = $3",
            last_sent_at, reminder_id, guild_id,
        )


async def update_fields(
    conn: asyncpg.Connection,
    reminder_id: int,
    guild_id: int,
    name: str,
    reminder_time: time,
    call_time: time,
    days: List[str],
    message: Optional[str],
    channel_id: Optional[int] = None,
) -> None:
    """Update editable reminder fields (from edit modal)."""
    if channel_id is not None:
        await conn.execute(
            """
            UPDATE reminders
            SET name = $1, time = $2, call_time = $3, days = $4, message = $5, channel_id = $6
            WHERE id = $7 AND guild_id = $8
            """,
            name, reminder_time, call_time, days or [], message, channel_id,
            reminder_id, guild_id,
        )
    else:
        await conn.execute(
            """
            UPDATE reminders
            SET name = $1, time = $2, call_time = $3, days = $4, message = $5
            WHERE id = $6 AND guild_id = $7
            """,
            name, reminder_time, call_time, days or [], message,
            reminder_id, guild_id,
        )


async def autocomplete_all(
    conn: asyncpg.Connection,
    guild_id: int,
) -> List[asyncpg.Record]:
    """Fetch id+name pairs for autocomplete (all reminders in guild)."""
    return await conn.fetch(
        "SELECT id, name FROM reminders WHERE guild_id = $1 ORDER BY id DESC LIMIT 25",
        guild_id,
    )


async def autocomplete_for_user(
    conn: asyncpg.Connection,
    guild_id: int,
    user_id: int,
) -> List[asyncpg.Record]:
    """Fetch id+name pairs for autocomplete (user's own reminders)."""
    return await conn.fetch(
        "SELECT id, name FROM reminders WHERE guild_id = $1 AND created_by = $2 ORDER BY id DESC LIMIT 25",
        guild_id, user_id,
    )


async def get_for_api(
    conn: asyncpg.Connection,
    user_id: Any,
    guild_id: Optional[int] = None,
) -> List[asyncpg.Record]:
    """Fetch reminders for a user (FastAPI endpoint)."""
    if guild_id:
        return await conn.fetch(
            """
            SELECT id, name, time, call_time, days, event_time, message, channel_id, created_by, location
            FROM reminders
            WHERE guild_id = $1 AND created_by = $2
            ORDER BY COALESCE(call_time, time) ASC
            """,
            guild_id, user_id,
        )
    return await conn.fetch(
        """
        SELECT id, name, time, call_time, days, event_time, message, channel_id, created_by, location
        FROM reminders
        WHERE created_by = $1
        ORDER BY COALESCE(call_time, time) ASC
        """,
        user_id,
    )


async def create_for_api(conn: asyncpg.Connection, data: Dict[str, Any]) -> None:
    """Create a reminder from FastAPI payload (simplified fields)."""
    days = data.get("days")
    if not days:
        days_list: List[str] = []
    elif isinstance(days, str):
        days_list = [days]
    else:
        days_list = list(days)
    await conn.execute(
        """
        INSERT INTO reminders (name, channel_id, time, days, message, created_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        data["name"], str(data["channel_id"]), data["time"],
        days_list, data["message"], data["created_by"],
    )


async def update_for_api(conn: asyncpg.Connection, data: Dict[str, Any]) -> None:
    """Update a reminder from FastAPI payload."""
    days = data.get("days")
    if not days:
        days_list: List[str] = []
    elif isinstance(days, str):
        days_list = [days]
    else:
        days_list = list(days)
    await conn.execute(
        """
        UPDATE reminders
        SET name = $1, time = $2, days = $3, message = $4
        WHERE id = $5 AND created_by = $6
        """,
        data["name"], data["time"], days_list, data["message"],
        data["id"], data["created_by"],
    )
