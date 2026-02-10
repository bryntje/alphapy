"""In-memory buffer for operational events (reconnect, disconnect, etc.) exposed via API."""

from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

MAX_OPERATIONAL_EVENTS = 100

_operational_events: Deque[Dict[str, Any]] = deque(maxlen=MAX_OPERATIONAL_EVENTS)


def log_operational_event(
    event_type: str,
    message: str,
    guild_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an operational event to the buffer for API exposure."""
    event = {
        "timestamp": datetime.now(timezone.utc),
        "event_type": event_type,
        "guild_id": guild_id,
        "message": message,
        "details": details or {},
    }
    _operational_events.appendleft(event)


def get_operational_events(
    guild_id: Optional[int] = None,
    limit: int = 50,
    event_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Get operational events from the buffer, optionally filtered.

    Events are included if:
    - guild_id is None (global event), OR
    - event's guild_id matches the requested guild_id.

    Returns events sorted newest first, limited to `limit`.
    """
    filtered: List[Dict[str, Any]] = []
    for event in _operational_events:
        if event_types and event["event_type"] not in event_types:
            continue
        ev_guild = event.get("guild_id")
        if ev_guild is not None and guild_id is not None and ev_guild != guild_id:
            continue
        # Include global events (ev_guild is None) for any guild request
        filtered.append(event)
        if len(filtered) >= limit:
            break

    # Serialize for JSON (datetime -> ISO string)
    result: List[Dict[str, Any]] = []
    for e in filtered:
        result.append({
            "timestamp": e["timestamp"].isoformat(),
            "event_type": e["event_type"],
            "guild_id": e.get("guild_id"),
            "message": e["message"],
            "details": e.get("details") or {},
        })
    return result
