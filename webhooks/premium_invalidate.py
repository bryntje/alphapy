"""
Webhook for premium cache invalidation when Core notifies of a subscription change.

When a user's premium status changes (payment, cancellation, expiry), Core calls
this endpoint so Alphapy clears the in-memory cache and the next is_premium()
check refetches from Core/DB.
"""

import json
import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status

from utils.premium_guard import invalidate_premium_cache
from webhooks.common import get_premium_invalidate_secret, validate_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/premium-invalidate", tags=["premium-invalidate"])


@router.post("")
async def handle_premium_invalidate_webhook(request: Request) -> Dict[str, str]:
    """
    Invalidate premium cache for a user (and optionally a guild).

    Expected payload:
    {
        "user_id": 123456789,   // Discord user ID (required)
        "guild_id": 987654321   // Optional; if omitted, all cache entries for user are cleared
    }
    """
    body = await request.body()
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("x-webhook-signature")
    )
    try:
        validate_webhook_signature(
            body, signature, get_premium_invalidate_secret(), log_name="premium-invalidate"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Unexpected signature validation error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        ) from e

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc

    user_id_raw = payload.get("user_id")
    if user_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required field: user_id.",
        )

    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id must be an integer (Discord user ID).",
        )

    guild_id: Optional[int] = None
    guild_id_raw = payload.get("guild_id")
    if guild_id_raw is not None:
        try:
            guild_id = int(guild_id_raw)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="guild_id must be an integer (Discord guild ID) or omitted.",
            )

    invalidate_premium_cache(user_id, guild_id)
    logger.info(
        "Premium cache invalidated: user_id=%s guild_id=%s",
        user_id,
        guild_id if guild_id is not None else "all",
    )
    return {"status": "acknowledged", "user_id": str(user_id)}
