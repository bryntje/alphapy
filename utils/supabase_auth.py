import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

import config

logger = logging.getLogger(__name__)

def _prepare_token(raw_header: str) -> str:
    token = raw_header.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


async def verify_supabase_token(authorization_header: str | None) -> dict[str, Any]:
    """Validate a Supabase JWT by calling Supabase's /auth/v1/user endpoint."""

    if not authorization_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase credentials are not configured.",
        )

    token = _prepare_token(authorization_header)
    auth_url = f"{config.SUPABASE_URL}/auth/v1/user"

    headers = {
        "apikey": config.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(auth_url, headers=headers)
        if response.status_code != 200:
            response_body = response.text
            is_expired = "expired" in response_body.lower() or "bad_jwt" in response_body.lower()

            if is_expired:
                logger.debug(
                    "Supabase token expired (normal): status=%s body=%s",
                    response.status_code,
                    response_body,
                )
            else:
                logger.warning(
                    "Supabase token validation failed: status=%s body=%s",
                    response.status_code,
                    response_body,
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Supabase token.",
            )
        payload = response.json()
        user = payload.get("user") or payload
        return {
            "sub": user.get("id"),
            "email": user.get("email"),
            "role": user.get("role"),
        }
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to validate Supabase token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to validate Supabase token.",
        ) from exc
