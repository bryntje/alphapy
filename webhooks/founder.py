"""
Webhook for founder welcome: Core notifies when an early-bird founder subscription
is activated so Alphapy can send a welcome DM to the user.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, status

from utils.logger import logger
from webhooks.common import get_founder_webhook_secret, validate_webhook_signature

router = APIRouter(prefix="/webhooks/founder", tags=["founder"])

_DEFAULT_FOUNDER_MESSAGE = (
    "Thank you for being an early supporter. You're now a **Founder** — "
    "we've assigned your Founder role in our server. Welcome to the community."
)


async def _send_founder_dm(user_id: int, message: str) -> bool:
    """Send a DM to the Discord user on the bot's event loop. Returns True if sent."""
    from gpt.helpers import bot_instance

    if bot_instance is None:
        logger.warning("Founder webhook: bot not available, cannot send DM")
        return False
    try:
        user = await bot_instance.fetch_user(user_id)
        if user is None:
            logger.warning("Founder webhook: could not fetch user %s", user_id)
            return False
        await user.send(message)
        return True
    except Exception as e:
        logger.warning("Founder webhook: failed to send DM to user %s: %s", user_id, e)
        return False


@router.post("")
async def handle_founder_webhook(request: Request) -> dict[str, str]:
    """
    Send a founder welcome DM to the user (e.g. after early-bird purchase).

    Expected payload:
    {
        "user_id": 123456789,   // Discord user ID (required)
        "message": "..."        // Optional; custom welcome text. If omitted, default is used.
    }
    """
    body = await request.body()
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("x-webhook-signature")
    )
    try:
        validate_webhook_signature(
            body, signature, get_founder_webhook_secret(), log_name="founder"
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

    message: str = payload.get("message") or _DEFAULT_FOUNDER_MESSAGE
    if not isinstance(message, str):
        message = _DEFAULT_FOUNDER_MESSAGE

    from gpt.helpers import bot_instance

    if bot_instance is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot not available to send DM.",
        )

    loop = bot_instance.loop

    try:
        future = asyncio.run_coroutine_threadsafe(
            _send_founder_dm(user_id, message), loop
        )
        # Await the result without blocking the event loop; wait_for raises asyncio.TimeoutError
        sent = await asyncio.wait_for(asyncio.wrap_future(future), timeout=10.0)
    except TimeoutError:
        logger.warning("Founder webhook: timeout sending DM to user %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timeout sending DM.",
        ) from None
    except asyncio.CancelledError:
        raise  # Let request cancellation propagate
    except Exception as e:
        logger.exception("Founder webhook: error sending DM: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send founder DM.",
        ) from e

    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send DM (user may have DMs disabled or bot could not fetch user).",
        )

    logger.info("Founder webhook: welcome DM sent to user_id=%s", user_id)
    return {"status": "acknowledged", "user_id": str(user_id)}
