"""
Settings Helper Utilities

Cached settings access and bulk operations to reduce database queries and
boilerplate code across cogs. Provides type-safe getters with automatic
coercion and caching.
"""

from collections import OrderedDict
from typing import Optional, Any, Dict
from utils.settings_service import SettingsService
from utils.logger import logger


class CachedSettingsHelper:
    """
    Wrapper around SettingsService that provides caching and type-safe getters.
    
    Reduces database queries by caching frequently accessed settings and provides
    convenient type coercion methods. Uses LRU cache with max size limit.
    """
    
    def __init__(self, settings: SettingsService, max_cache_size: int = 500):
        """
        Initialize the cached settings helper.
        
        Args:
            settings: The SettingsService instance to wrap
            max_cache_size: Maximum number of entries in cache (default: 500)
        """
        self._settings = settings
        self._cache: OrderedDict[tuple[str, str, int], Any] = OrderedDict()
        self._cache_enabled = True
        self._max_cache_size = max_cache_size
    
    def _get_cache_key(self, scope: str, key: str, guild_id: int) -> tuple[str, str, int]:
        """Generate cache key from scope, key, and guild_id."""
        return (scope, key, guild_id)
    
    def _evict_if_needed(self) -> None:
        """Evict oldest entry if cache exceeds max size."""
        if len(self._cache) >= self._max_cache_size:
            # Remove oldest (first) entry
            evicted_key = self._cache.popitem(last=False)
            logger.debug(f"Settings cache eviction: size={len(self._cache)}/{self._max_cache_size}, evicted={evicted_key[0]}")
    
    def clear_cache(self, scope: Optional[str] = None, key: Optional[str] = None, guild_id: Optional[int] = None) -> None:
        """
        Clear cached settings. If parameters are provided, only clear matching entries.
        
        Args:
            scope: Optional scope to filter by
            key: Optional key to filter by
            guild_id: Optional guild_id to filter by
        """
        if scope is None and key is None and guild_id is None:
            self._cache.clear()
            return
        
        keys_to_remove = []
        for cache_key in self._cache.keys():
            cache_scope, cache_key_name, cache_guild_id = cache_key
            if (scope is None or cache_scope == scope) and \
               (key is None or cache_key_name == key) and \
               (guild_id is None or cache_guild_id == guild_id):
                keys_to_remove.append(cache_key)
        
        for key_to_remove in keys_to_remove:
            del self._cache[key_to_remove]
    
    def get_int(self, scope: str, key: str, guild_id: int, fallback: int = 0) -> int:
        """
        Cached int getter with type coercion.
        
        Args:
            scope: Settings scope (e.g., "system", "reminders")
            key: Settings key (e.g., "log_channel_id")
            guild_id: Guild ID to get setting for
            fallback: Default value if setting is not found or invalid
            
        Returns:
            int: The setting value as an integer
        """
        cache_key = self._get_cache_key(scope, key, guild_id)
        
        if self._cache_enabled and cache_key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            cached_value = self._cache[cache_key]
            if isinstance(cached_value, int):
                return cached_value
        
        try:
            value = self._settings.get(scope, key, guild_id, fallback)
            coerced = int(value) if value else fallback
            if self._cache_enabled:
                self._evict_if_needed()  # Before adding new entry
                self._cache[cache_key] = coerced
                self._cache.move_to_end(cache_key)  # Mark as recently used
            return coerced
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to coerce setting {scope}.{key} to int: {e}")
            if self._cache_enabled:
                self._evict_if_needed()  # Before adding new entry
                self._cache[cache_key] = fallback
                self._cache.move_to_end(cache_key)  # Mark as recently used
            return fallback
    
    def get_bool(self, scope: str, key: str, guild_id: int, fallback: bool = False) -> bool:
        """
        Cached bool getter with type coercion.
        
        Args:
            scope: Settings scope
            key: Settings key
            guild_id: Guild ID
            fallback: Default value if setting is not found or invalid
            
        Returns:
            bool: The setting value as a boolean
        """
        cache_key = self._get_cache_key(scope, key, guild_id)
        
        if self._cache_enabled and cache_key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            cached_value = self._cache[cache_key]
            if isinstance(cached_value, bool):
                return cached_value
        
        try:
            value = self._settings.get(scope, key, guild_id, fallback)
            if isinstance(value, bool):
                coerced = value
            elif isinstance(value, str):
                coerced = value.lower() in ("true", "1", "yes", "on")
            else:
                coerced = bool(value) if value else fallback
            
            if self._cache_enabled:
                self._evict_if_needed()  # Before adding new entry
                self._cache[cache_key] = coerced
                self._cache.move_to_end(cache_key)  # Mark as recently used
            return coerced
        except Exception as e:
            logger.warning(f"Failed to coerce setting {scope}.{key} to bool: {e}")
            if self._cache_enabled:
                self._evict_if_needed()  # Before adding new entry
                self._cache[cache_key] = fallback
                self._cache.move_to_end(cache_key)  # Mark as recently used
            return fallback
    
    def get_str(self, scope: str, key: str, guild_id: int, fallback: str = "") -> str:
        """
        Cached string getter.
        
        Args:
            scope: Settings scope
            key: Settings key
            guild_id: Guild ID
            fallback: Default value if setting is not found
            
        Returns:
            str: The setting value as a string
        """
        cache_key = self._get_cache_key(scope, key, guild_id)
        
        if self._cache_enabled and cache_key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            cached_value = self._cache[cache_key]
            if isinstance(cached_value, str):
                return cached_value
        
        try:
            value = self._settings.get(scope, key, guild_id, fallback)
            coerced = str(value) if value else fallback
            if self._cache_enabled:
                self._evict_if_needed()  # Before adding new entry
                self._cache[cache_key] = coerced
                self._cache.move_to_end(cache_key)  # Mark as recently used
            return coerced
        except Exception as e:
            logger.warning(f"Failed to coerce setting {scope}.{key} to str: {e}")
            if self._cache_enabled:
                self._evict_if_needed()  # Before adding new entry
                self._cache[cache_key] = fallback
                self._cache.move_to_end(cache_key)  # Mark as recently used
            return fallback
    
    async def set_bulk(
        self,
        guild_id: int,
        updates: Dict[tuple[str, str], Any],
        updated_by: Optional[int] = None
    ) -> None:
        """
        Bulk settings update in a more efficient way.
        
        Note: This doesn't use a transaction yet, but groups operations.
        Future enhancement: Use database transaction for atomic updates.
        
        Args:
            guild_id: Guild ID to update settings for
            updates: Dictionary mapping (scope, key) tuples to values
            updated_by: Optional user ID who made the changes
        """
        for (scope, key), value in updates.items():
            try:
                await self._settings.set(scope, key, value, guild_id, updated_by)
                # Invalidate cache for this setting
                cache_key = self._get_cache_key(scope, key, guild_id)
                self._cache.pop(cache_key, None)
            except Exception as e:
                logger.error(f"Failed to set setting {scope}.{key}: {e}")
                # Continue with other updates even if one fails
    
    async def invalidate_cache(self, scope: str, key: str, guild_id: int) -> None:
        """
        Invalidate cache for a specific setting (useful after external updates).
        
        Args:
            scope: Settings scope
            key: Settings key
            guild_id: Guild ID
        """
        cache_key = self._get_cache_key(scope, key, guild_id)
        self._cache.pop(cache_key, None)
