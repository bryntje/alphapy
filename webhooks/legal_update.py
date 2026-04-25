"""
Webhook for legal document update notifications.

When docs/terms-of-service.md or docs/privacy-policy.md changes on master,
a GitHub Action fires this endpoint. The bot then posts an embed in the
configured channel of the main guild (MAIN_GUILD_ID).
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request, status

from utils.embed_builder import EmbedBuilder
from utils.logger import logger as bot_logger
from webhooks.common import get_legal_update_webhook_secret, validate_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/legal-update", tags=["legal-update"])

_DOC_LABELS = {
    "tos": ("📄 Terms of Service updated", "Our Terms of Service have been updated."),
    "pp": ("🔒 Privacy Policy updated", "Our Privacy Policy has been updated."),
}

_DOC_URLS = {
    "tos": "https://docs.innersync.tech/legal/terms-of-service",
    "pp": "https://docs.innersync.tech/legal/privacy-policy",
}


@router.post("")
async def handle_legal_update_webhook(request: Request) -> dict[str, str]:
    """
    Post a legal update embed in the main guild when PP or ToS changes.

    Expected payload:
    {
        "documents": ["tos", "pp"],   // which docs changed (required, at least one)
        "tos_version": "2026-03-31",  // new version date (required if "tos" in documents)
        "pp_version": "2026-03-31"    // new version date (required if "pp" in documents)
    }
    """
    body = await request.body()
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("x-webhook-signature")
    )
    try:
        validate_webhook_signature(
            body, signature, get_legal_update_webhook_secret(), log_name="legal-update"
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

    documents: list[str] = payload.get("documents", [])
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required field: documents (must contain 'tos' and/or 'pp').",
        )

    import config
    from gpt.helpers import bot_instance

    main_guild_id = getattr(config, "MAIN_GUILD_ID", 0)
    if not main_guild_id:
        logger.warning("legal-update webhook received but MAIN_GUILD_ID is not configured.")
        return {"status": "skipped", "reason": "MAIN_GUILD_ID not configured"}

    if bot_instance is None:
        logger.error("legal-update webhook: bot not available.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot not ready.",
        )

    # Determine target channel
    channel_id = getattr(config, "LEGAL_UPDATES_CHANNEL_ID", 0)
    if not channel_id:
        # Fall back to system.log_channel_id for the main guild
        try:
            from utils.settings_service import SettingsService

            settings = SettingsService(config.DATABASE_URL)
            value = settings.get("system", "log_channel_id", main_guild_id)
            channel_id = int(value) if value else 0
        except Exception as e:
            logger.warning("legal-update: could not resolve fallback channel: %s", e)

    if not channel_id:
        logger.warning(
            "legal-update webhook: no channel configured for main guild %s.", main_guild_id
        )
        return {"status": "skipped", "reason": "no target channel configured"}

    channel = bot_instance.get_channel(channel_id)
    if channel is None:
        logger.warning(
            "legal-update webhook: channel %s not found (guild %s).", channel_id, main_guild_id
        )
        return {"status": "skipped", "reason": "channel not found"}

    sent: list[str] = []
    for doc_key in documents:
        if doc_key not in _DOC_LABELS:
            logger.debug("legal-update: unknown document key %r — skipping.", doc_key)
            continue

        version = payload.get(f"{doc_key}_version", "")
        title, description = _DOC_LABELS[doc_key]
        doc_url = _DOC_URLS[doc_key]

        fields = [
            {"name": "📅 Effective date", "value": version or "see document", "inline": True},
            {"name": "🔗 Read the full document", "value": f"[View on docs.innersync.tech]({doc_url})", "inline": True},
        ]

        embed = EmbedBuilder.info(
            title=title,
            description=description,
            fields=fields,
            footer="Legal update | Innersync",
        )

        try:
            await channel.send(embed=embed)
            sent.append(doc_key)
            bot_logger.info(
                "legal-update: posted %s embed (version=%s) to channel %s guild %s",
                doc_key,
                version,
                channel_id,
                main_guild_id,
            )
        except Exception as e:
            logger.error("legal-update: failed to send embed for %s: %s", doc_key, e)

    return {"status": "acknowledged", "sent": ", ".join(sent) if sent else "none"}
