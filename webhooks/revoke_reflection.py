"""
Webhook handler for reflection revoke from Core-API.

Deletes stored reflection when user revokes consent in App.
"""

import hashlib
import hmac
import json
import logging
from typing import Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status

import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/revoke-reflection", tags=["revoke-reflection"])


def _validate_signature(body: bytes, signature: Optional[str]) -> None:
    """Validate webhook signature if a secret is configured."""
    secret = (
        getattr(config, "APP_REFLECTIONS_WEBHOOK_SECRET", None)
        or getattr(config, "WEBHOOK_SECRET", None)
        or getattr(config, "SUPABASE_WEBHOOK_SECRET", None)
    )
    if not secret:
        logger.debug("No revoke webhook secret configured - skipping signature validation")
        return

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature header.",
        )

    provided = signature
    if signature.startswith("sha256="):
        provided = signature.split("=", 1)[1]

    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided, computed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )


@router.post("")
async def handle_revoke_reflection_webhook(request: Request) -> dict:
    """
    Handle revoke reflection from Core-API.

    Expected payload:
    {
        "user_id": 123456789,  // Discord user ID
        "reflection_id": "uuid"
    }
    """
    body = await request.body()
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("x-webhook-signature")
    )
    try:
        _validate_signature(body, signature)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Signature validation error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature validation failed.",
        ) from e

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc

    user_id = payload.get("user_id")
    reflection_id = payload.get("reflection_id")

    if user_id is None or reflection_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: user_id, reflection_id.",
        )

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id must be an integer (Discord user ID).",
        )

    pool: Optional[asyncpg.Pool] = getattr(request.app.state, "db_pool", None)
    if not pool or pool.is_closing():
        logger.error("Database pool not available for revoke-reflection webhook")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable.",
        )

    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM app_reflections
                WHERE user_id = $1 AND reflection_id = $2
                """,
                user_id,
                reflection_id,
            )
    except Exception as e:
        logger.exception("Failed to delete from app_reflections: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke reflection.",
        ) from e

    # result is like "DELETE 1" or "DELETE 0"
    count = 0
    if result and result.split()[-1].isdigit():
        count = int(result.split()[-1])

    logger.info(
        "Revoke reflection webhook: user_id=%s, reflection_id=%s, deleted=%s",
        user_id,
        reflection_id,
        count,
    )
    return {"status": "deleted", "count": count}


__all__ = ["router"]
