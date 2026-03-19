import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status

import config
from utils.dashboard_webhooks import forward_supabase_auth
from utils.supabase_client import SupabaseConfigurationError, upsert_profile
from webhooks.common import validate_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/supabase", tags=["supabase"])


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
    validate_webhook_signature(
        body,
        signature,
        getattr(config, "SUPABASE_WEBHOOK_SECRET", None),
        missing_detail="Missing Supabase signature header.",
        invalid_detail="Invalid Supabase signature.",
    )

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

    if event_type in {"USER_CREATED", "USER_SIGNED_UP", "USER_UPDATED"} and user_id:
        profile_payload: Dict[str, Any] = {"user_id": user_id}
        record = payload.get("record") or payload.get("user") or {}
        raw_meta = record.get("raw_user_meta_data") or {}

        nickname = raw_meta.get("full_name") or raw_meta.get("user_name")
        discord_id = (
            raw_meta.get("provider_id")
            if raw_meta.get("provider") == "discord"
            else None
        )

        if nickname:
            profile_payload["nickname"] = nickname
        if discord_id:
            profile_payload["discord_id"] = str(discord_id)

        try:
            await upsert_profile(profile_payload)
        except SupabaseConfigurationError:
            logger.debug(
                "Supabase service role key not configured; skipping profile sync."
            )
        except Exception as exc:  # pragma: no cover - network path
            logger.warning(
                "Failed to upsert profile for user_id=%s: %s", user_id, exc
            )

    if event_type in {"USER_DELETED", "USER_DESTROYED"} and user_id:
        # TODO: purge user data when data ownership contracts are finalised.
        logger.info(
            "Supabase user deletion event received for user_id=%s. "
            "Add data cleanup logic here.",
            user_id,
        )

    forward_supabase_auth(payload)
    return {"status": "acknowledged"}
