"""
Webhook handler for reflection events from App.

Handles reflection.created events and optionally creates reminders or logs for analytics.
"""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status

from utils.supabase_client import get_user_id_for_discord
from webhooks.common import get_reflections_webhook_secret, validate_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/reflections", tags=["reflections"])


@router.post("")
async def handle_reflection_webhook(request: Request) -> Dict[str, str]:
    """
    Handle reflection.created events from App.
    
    Expected payload:
    {
        "event": "reflection.created",
        "user_id": "uuid",
        "reflection_id": "uuid",
        "date": "YYYY-MM-DD",
        "timestamp": "ISO8601"
    }
    """
    body = await request.body()
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("x-webhook-signature")
    )
    
    # Validate signature if secret is configured
    try:
        validate_webhook_signature(
            body, signature, get_reflections_webhook_secret(), log_name="reflections"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Signature validation error (non-critical): %s", e)
    
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc

    event_type = payload.get("event", "")
    user_id = payload.get("user_id")
    reflection_id = payload.get("reflection_id")
    date = payload.get("date")

    logger.info(
        "Reflection webhook received: event=%s, user_id=%s, reflection_id=%s, date=%s",
        event_type,
        user_id,
        reflection_id,
        date,
    )

    if event_type == "reflection.created" and user_id and reflection_id:
        # Optional: Create reminder suggestion or log for analytics
        # For now, just log the event
        logger.debug(
            f"Reflection created: user_id={user_id}, reflection_id={reflection_id}, date={date}"
        )
        
        # Future: Could create a reminder suggestion here
        # Future: Could update analytics/metrics
        
    return {"status": "acknowledged", "event": event_type}


__all__ = ["router"]
