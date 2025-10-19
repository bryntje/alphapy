import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status

import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/supabase", tags=["supabase"])


def _validate_signature(body: bytes, signature: Optional[str]) -> None:
    """Validate Supabase webhook signature if a secret is configured."""
    secret = config.SUPABASE_WEBHOOK_SECRET
    if not secret:
        return
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Supabase signature header.",
        )

    provided = signature
    if signature.startswith("sha256="):
        provided = signature.split("=", 1)[1]

    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided, computed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase signature.",
        )


def _extract_user_id(payload: Dict[str, Any]) -> Optional[str]:
    record = payload.get("record") or payload.get("user") or {}
    return record.get("id")


@router.post("/auth")
async def supabase_auth_webhook(request: Request) -> Dict[str, str]:
    """Handle Supabase Auth webhooks for user lifecycle events."""
    body = await request.body()
    signature = (
        request.headers.get("supabase-signature")
        or request.headers.get("x-supabase-signature")
        or request.headers.get("x-signature")
    )
    _validate_signature(body, signature)

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc

    event_type = (
        str(
            payload.get("type")
            or payload.get("eventType")
            or payload.get("event_type")
            or ""
        ).upper()
    )
    user_id = _extract_user_id(payload)

    logger.info(
        "Supabase auth webhook received: type=%s, user_id=%s",
        event_type or "UNKNOWN",
        user_id,
    )

    if event_type in {"USER_DELETED", "USER_DESTROYED"} and user_id:
        # TODO: purge user data when data ownership contracts are finalised.
        logger.info(
            "Supabase user deletion event received for user_id=%s. "
            "Add data cleanup logic here.",
            user_id,
        )

    return {"status": "acknowledged"}
