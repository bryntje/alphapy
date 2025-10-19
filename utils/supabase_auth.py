import logging
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError, PyJWKClient

import config

logger = logging.getLogger(__name__)

_jwk_client: Optional[PyJWKClient] = None


def _get_jwk_client() -> PyJWKClient:
    """Initialise and cache a PyJWKClient for Supabase."""
    global _jwk_client
    if not config.SUPABASE_JWKS_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase JWKS URL is not configured.",
        )
    if _jwk_client is None:
        headers = None
        if config.SUPABASE_ANON_KEY:
            headers = {"apikey": config.SUPABASE_ANON_KEY}
        logger.info("Initializing JWKS client for %s", config.SUPABASE_JWKS_URL)
        _jwk_client = PyJWKClient(config.SUPABASE_JWKS_URL, headers=headers)
    return _jwk_client


def _prepare_token(raw_header: str) -> str:
    token = raw_header.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def verify_supabase_token(authorization_header: Optional[str]) -> Dict[str, Any]:
    """
    Validate a Supabase JWT access token and return the decoded claims.

    Raises HTTP 401 when the token is missing or invalid.
    """
    if not authorization_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    token = _prepare_token(authorization_header)
    try:
        jwk_client = _get_jwk_client()
        signing_key = jwk_client.get_signing_key_from_jwt(token)

        decode_kwargs: Dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": {"verify_aud": False},
        }

        if config.SUPABASE_JWT_AUDIENCE:
            decode_kwargs["audience"] = config.SUPABASE_JWT_AUDIENCE
            decode_kwargs["options"]["verify_aud"] = True

        if config.SUPABASE_ISSUER:
            decode_kwargs["issuer"] = config.SUPABASE_ISSUER

        claims = jwt.decode(token, signing_key.key, **decode_kwargs)
        return claims
    except InvalidTokenError as exc:
        logger.warning("Invalid Supabase token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase token.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive catch
        logger.error("Failed to validate Supabase token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to validate Supabase token.",
        ) from exc
