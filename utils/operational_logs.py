"""In-memory buffer for operational events (reconnect, disconnect, etc.) exposed via API."""

from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Union

MAX_OPERATIONAL_EVENTS = 100

_operational_events: Deque[Dict[str, Any]] = deque(maxlen=MAX_OPERATIONAL_EVENTS)


def _push_to_core_ingress(event: Dict[str, Any]) -> None:
    """Fire-and-forget: enqueue event for Core-API ingress (no await, non-blocking)."""
    try:
        from utils.core_ingress import enqueue_operational_event

        serialized = {
            "timestamp": event["timestamp"].isoformat() if hasattr(event["timestamp"], "isoformat") else event["timestamp"],
            "event_type": event["event_type"],
            "guild_id": event.get("guild_id"),
            "message": event["message"],
            "details": event.get("details") or {},
        }
        enqueue_operational_event(serialized)
    except Exception:
        pass


class EventType(str, Enum):
    """Operational event types for type safety and documentation."""
    BOT_READY = "BOT_READY"
    BOT_RECONNECT = "BOT_RECONNECT"
    BOT_DISCONNECT = "BOT_DISCONNECT"
    GUILD_SYNC = "GUILD_SYNC"
    ONBOARDING_ERROR = "ONBOARDING_ERROR"
    SETTINGS_CHANGED = "SETTINGS_CHANGED"
    COG_ERROR = "COG_ERROR"


def log_operational_event(
    event_type: Union[EventType, str],
    message: str,
    guild_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an operational event to the buffer for API exposure.
    
    Args:
        event_type: Event type (EventType enum or string for backward compatibility)
        message: Human-readable event message
        guild_id: Optional guild ID for guild-specific events
        details: Optional additional event details
    """
    # Convert enum to string if needed
    event_type_str = event_type.value if isinstance(event_type, EventType) else event_type
    
    event = {
        "timestamp": datetime.now(timezone.utc),
        "event_type": event_type_str,
        "guild_id": guild_id,
        "message": message,
        "details": details or {},
    }
    _operational_events.appendleft(event)
    _push_to_core_ingress(event)


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
    # Validate event_types against known EventType values to prevent abuse
    valid_event_types = {e.value for e in EventType}
    if event_types:
        event_types = [t for t in event_types if t in valid_event_types]
        # If user requested types but all were invalid, return no events
        if not event_types:
            return []
    
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
