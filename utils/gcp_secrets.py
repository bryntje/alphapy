"""
Google Cloud Secret Manager Utility

Provides secure access to secrets stored in Google Cloud Secret Manager with
caching and graceful fallback to environment variables for local development.
"""

import logging
import os
import time
from typing import Optional, Dict, Tuple

import config

logger = logging.getLogger(__name__)

# In-memory cache for secrets: {secret_name: (value, expiry_timestamp)}
_secret_cache: Dict[str, Tuple[str, float]] = {}
# Cache TTL: 1 hour (3600 seconds)
CACHE_TTL = 3600


class SecretManagerError(Exception):
    """Raised when Secret Manager operations fail."""


def _is_cache_valid(secret_name: str) -> bool:
    """Check if cached secret is still valid."""
    if secret_name not in _secret_cache:
        return False
    
    _, expiry = _secret_cache[secret_name]
    return time.time() < expiry


def _get_from_cache(secret_name: str) -> Optional[str]:
    """Retrieve secret from cache if valid."""
    if _is_cache_valid(secret_name):
        value, _ = _secret_cache[secret_name]
        logger.debug(f"Retrieved secret '{secret_name}' from cache")
        return value
    return None


def _store_in_cache(secret_name: str, value: str) -> None:
    """Store secret in cache with TTL."""
    expiry = time.time() + CACHE_TTL
    _secret_cache[secret_name] = (value, expiry)
    logger.debug(f"Cached secret '{secret_name}' (expires in {CACHE_TTL}s)")


def _fetch_from_secret_manager(secret_name: str, project_id: str) -> Optional[str]:
    """
    Fetch secret from Google Cloud Secret Manager.
    
    Args:
        secret_name: Name of the secret in Secret Manager
        project_id: GCP project ID
        
    Returns:
        Secret value as string, or None if not found or error occurs
        
    Note:
        All exceptions are caught and logged, returning None instead of raising.
        This allows graceful fallback to environment variables.
    """
    try:
        from google.cloud import secretmanager  # pyright: ignore[reportMissingImports]
    except ImportError:
        logger.warning(
            "google-cloud-secret-manager not installed. "
            "Install with: pip install google-cloud-secret-manager"
        )
        return None
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        
        logger.info(f"Fetching secret '{secret_name}' from Secret Manager (project: {project_id})")
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")
        
        logger.info(f"✅ Successfully retrieved secret '{secret_name}' from Secret Manager")
        return secret_value
        
    except Exception as e:
        logger.error(
            f"Failed to fetch secret '{secret_name}' from Secret Manager: {e}",
            exc_info=True
        )
        return None


def get_secret(secret_name: str, project_id: Optional[str] = None) -> Optional[str]:
    """
    Get secret value from Secret Manager or environment variable fallback.
    
    Priority order:
    1. In-memory cache (if valid)
    2. Google Cloud Secret Manager (if project_id is configured)
    3. Environment variable (fallback for local development)
    
    Args:
        secret_name: Name of the secret in Secret Manager or environment variable
        project_id: Optional GCP project ID. If not provided, uses GOOGLE_PROJECT_ID from config
        
    Returns:
        Secret value as string, or None if not found
        
    Example:
        >>> credentials = get_secret("alphapy-google-credentials", "my-project")
        >>> # Or use default from config:
        >>> credentials = get_secret("alphapy-google-credentials")
    """
    # Check cache first
    cached_value = _get_from_cache(secret_name)
    if cached_value is not None:
        return cached_value
    
    # Try Secret Manager if project_id is available
    effective_project_id = project_id or config.GOOGLE_PROJECT_ID
    if effective_project_id:
        try:
            secret_value = _fetch_from_secret_manager(secret_name, effective_project_id)
            if secret_value is not None:
                _store_in_cache(secret_name, secret_value)
                return secret_value
            logger.debug(
                f"Secret Manager unavailable or secret '{secret_name}' not found, "
                "falling back to environment variable"
            )
        except Exception as e:
            logger.debug(
                f"Secret Manager error for '{secret_name}': {e}, "
                "falling back to environment variable"
            )
    
    # Fallback to environment variable
    env_value = os.getenv(secret_name.upper().replace("-", "_"))
    if env_value:
        logger.info(f"Using environment variable for secret '{secret_name}'")
        # Cache environment variable value too (shorter TTL might be better, but using same for consistency)
        _store_in_cache(secret_name, env_value)
        return env_value
    
    logger.warning(f"Secret '{secret_name}' not found in Secret Manager or environment variables")
    return None


def clear_cache(secret_name: Optional[str] = None) -> None:
    """
    Clear secret cache.
    
    Args:
        secret_name: If provided, clears only this secret. Otherwise clears all cached secrets.
    """
    if secret_name:
        _secret_cache.pop(secret_name, None)
        logger.debug(f"Cleared cache for secret '{secret_name}'")
    else:
        _secret_cache.clear()
        logger.debug("Cleared all secret caches")


__all__ = ["get_secret", "clear_cache", "CACHE_TTL"]
