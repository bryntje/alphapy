"""
Webhook handler for plaintext reflections from App via Core-API.

Stores reflection content in app_reflections for use in user-self flows (e.g.
/growthcheckin only; not used for ticket "Suggest reply" for privacy).
Consent is validated by Core before the webhook is sent.
"""

import json
import logging
from typing import Dict, Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status

from webhooks.common import get_app_reflections_secret, validate_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/app-reflections", tags=["app-reflections"])


@router.post("")
async def handle_app_reflection_webhook(request: Request) -> Dict[str, str]:
    """
    Handle plaintext reflection payload from Core-API.

    Expected payload:
    {
        "user_id": 123456789,  // Discord user ID
        "reflection_id": "uuid",
        "plaintext_content": { ... }  // JSON object with reflection fields
    }
    """
    body = await request.body()
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("x-webhook-signature")
    )
    try:
        validate_webhook_signature(
            body, signature, get_app_reflections_secret(), log_name="app-reflections"
        )
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
    plaintext_content = payload.get("plaintext_content")

    if user_id is None or reflection_id is None or plaintext_content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: user_id, reflection_id, plaintext_content.",
        )

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id must be an integer (Discord user ID).",
        )

    if not isinstance(plaintext_content, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plaintext_content must be a JSON object.",
        )

    pool: Optional[asyncpg.Pool] = getattr(request.app.state, "db_pool", None)
    if not pool or pool.is_closing():
        logger.error("Database pool not available for app-reflections webhook")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable.",
        )

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO app_reflections (user_id, reflection_id, plaintext_content)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (user_id, reflection_id) DO UPDATE SET
                    plaintext_content = EXCLUDED.plaintext_content
                """,
                user_id,
                reflection_id,
                json.dumps(plaintext_content),
            )
    except Exception as e:
        logger.exception("Failed to upsert app_reflections: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store reflection.",
        ) from e

    logger.info(
        "App reflection webhook: user_id=%s, reflection_id=%s",
        user_id,
        reflection_id,
    )
    return {"status": "acknowledged", "reflection_id": reflection_id}


__all__ = ["router"]
