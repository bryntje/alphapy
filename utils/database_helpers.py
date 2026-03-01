"""
Database helper utilities for common database operations.
"""
import asyncpg
from typing import Optional
from .db_helpers import create_db_pool, is_pool_healthy, acquire_safe


class DatabaseManager:
    """Helper class for managing database connections and common operations."""

    def __init__(self, pool_name: str, config_dict: dict):
        self.pool_name = pool_name
        self.config = config_dict
        self._pool: Optional[asyncpg.Pool] = None

    async def ensure_pool(self) -> asyncpg.Pool:
        """Ensure database pool is available, create if needed."""
        if not is_pool_healthy(self._pool):
            self._pool = await create_db_pool(
                self.config.get('DATABASE_URL', ''),
                name=self.pool_name,
                min_size=1,
                max_size=5,
                command_timeout=10.0
            )
        return self._pool

    async def execute_query(self, query: str, *args):
        """Execute a query with automatic pool management."""
        pool = await self.ensure_pool()
        async with acquire_safe(pool) as conn:
            return await conn.fetch(query, *args)

    async def execute_single(self, query: str, *args):
        """Execute a query and return single result."""
        pool = await self.ensure_pool()
        async with acquire_safe(pool) as conn:
            return await conn.fetchval(query, *args)


# Global instances for common use
# These can be imported and used across cogs
status_db = DatabaseManager("status", {"DATABASE_URL": None})  # Will be set at runtime
gdpr_db = DatabaseManager("gdpr", {"DATABASE_URL": None})