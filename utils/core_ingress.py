"""Send telemetry and operational events to Core-API (neural plane centralisation)."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Dict, List

import httpx

import config

logger = logging.getLogger(__name__)

CORE_INGRESS_TIMEOUT = 10.0
MAX_OPERATIONAL_EVENTS_QUEUE = 200

# Queue for operational events when Core is configured; drained by telemetry/ingress loop
_operational_events_queue: deque = deque(maxlen=MAX_OPERATIONAL_EVENTS_QUEUE)


def _is_ingress_configured() -> bool:
    """Return True if Core-API ingress URL and service key are set."""
    return bool(
        getattr(config, "CORE_API_URL", None)
        and getattr(config, "ALPHAPY_SERVICE_KEY", None)
    )


async def post_telemetry(payload: Dict[str, Any] | List[Dict[str, Any]]) -> bool:
    """
    POST telemetry snapshot(s) to Core-API /ingress/telemetry.
    Returns True on success (2xx), False on failure or when Core is not configured.
    """
    if not _is_ingress_configured():
        return False

    url = f"{config.CORE_API_URL}/ingress/telemetry"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": config.ALPHAPY_SERVICE_KEY,
    }
    body: Dict[str, Any]
    if isinstance(payload, list):
        body = {"snapshots": payload}
    else:
        body = {"snapshots": [payload]}

    try:
        async with httpx.AsyncClient(timeout=CORE_INGRESS_TIMEOUT) as client:
            response = await client.post(url, json=body, headers=headers)
            if response.is_success:
                logger.debug("Core ingress telemetry POST succeeded")
                return True
            logger.warning(
                "Core ingress telemetry failed: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            return False
    except Exception as exc:
        logger.debug("Core ingress telemetry error: %s", exc)
        return False


def enqueue_operational_event(event: Dict[str, Any]) -> None:
    """
    Add an operational event to the queue for later POST to Core.
    Event must be JSON-serialisable (timestamp as ISO string, guild_id as int or None).
    Does not block; call from log_operational_event() hot path.
    """
    if not _is_ingress_configured():
        return
    if len(_operational_events_queue) >= MAX_OPERATIONAL_EVENTS_QUEUE:
        _operational_events_queue.pop()
    _operational_events_queue.append(event)


async def flush_operational_events_queue() -> None:
    """
    POST all queued operational events to Core-API /ingress/operational-events (batch).
    Call from the telemetry ingest loop or similar periodic task.
    """
    if not _is_ingress_configured() or not _operational_events_queue:
        return

    events: List[Dict[str, Any]] = []
    while _operational_events_queue:
        events.append(_operational_events_queue.popleft())

    url = f"{config.CORE_API_URL}/ingress/operational-events"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": config.ALPHAPY_SERVICE_KEY,
    }
    body = {"events": events}

    try:
        async with httpx.AsyncClient(timeout=CORE_INGRESS_TIMEOUT) as client:
            response = await client.post(url, json=body, headers=headers)
            if response.is_success:
                logger.debug("Core ingress operational-events POST succeeded (count=%d)", len(events))
            else:
                logger.warning(
                    "Core ingress operational-events failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                # Re-queue on failure (up to max size)
                for e in events:
                    if len(_operational_events_queue) < MAX_OPERATIONAL_EVENTS_QUEUE:
                        _operational_events_queue.append(e)
    except Exception as exc:
        logger.debug("Core ingress operational-events error: %s", exc)
        for e in events:
            if len(_operational_events_queue) < MAX_OPERATIONAL_EVENTS_QUEUE:
                _operational_events_queue.append(e)
