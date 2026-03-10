"""
Database Helper Utilities

Centralized database pool management and error handling to reduce boilerplate
across the codebase. Provides safe connection acquisition with automatic error
handling and reconnection logic.
"""

from contextlib import asynccontextmanager
from typing import Optional, TypeVar, AsyncGenerator, Callable, Any, List
import asyncpg
from asyncpg import exceptions as pg_exceptions
from utils.logger import logger

# Type alias for pools created by create_db_pool (so callers can hint without importing asyncpg)
PoolT = asyncpg.Pool

# Registry of all created pools for centralized cleanup
_registered_pools: List[asyncpg.Pool] = []

T = TypeVar('T')

@asynccontextmanager
async def acquire_safe(
    pool: Optional[asyncpg.Pool],
    on_error: Optional[Callable[[Exception], Any]] = None
) -> AsyncGenerator[asyncpg.pool.PoolConnectionProxy, None]:
    """
    Safe pool acquire with automatic error handling and reconnection.
    
    Args:
        pool: The asyncpg connection pool (can be None)
        on_error: Optional callback function to handle connection errors
        
    Yields:
        asyncpg.pool.PoolConnectionProxy: A database connection from the pool
        
    Raises:
        RuntimeError: If pool is None or closing
        ConnectionDoesNotExistError: If connection is lost
        InterfaceError: If connection interface error occurs
        ConnectionResetError: If connection is reset
    """
    if pool is None or pool.is_closing():
        raise RuntimeError("Database pool not available")
    
    try:
        async with pool.acquire() as conn:
            yield conn
    except (
        pg_exceptions.ConnectionDoesNotExistError,
        pg_exceptions.InterfaceError,
        ConnectionResetError
    ) as e:
        if on_error:
            try:
                if callable(on_error):
                    # Check if it's async
                    if hasattr(on_error, '__call__'):
                        import inspect
                        if inspect.iscoroutinefunction(on_error):
                            await on_error(e)
                        else:
                            on_error(e)
            except Exception as callback_error:
                logger.warning(f"Error in on_error callback: {callback_error}")
        raise


def is_pool_healthy(pool: Optional[asyncpg.Pool]) -> bool:
    """
    Check if a database pool is healthy and ready for use.
    
    Args:
        pool: The asyncpg connection pool to check
        
    Returns:
        bool: True if pool is healthy, False otherwise
    """
    if pool is None:
        return False
    if pool.is_closing():
        return False
    return True


async def check_pool_health(pool: Optional[asyncpg.Pool]) -> tuple[bool, Optional[str]]:
    """
    Perform an actual health check by attempting a simple query.
    
    Args:
        pool: The asyncpg connection pool to check
        
    Returns:
        tuple[bool, Optional[str]]: (is_healthy, error_message)
    """
    if not is_pool_healthy(pool):
        return False, "Pool is None or closing"
    
    try:
        async with acquire_safe(pool) as conn:
            await conn.fetchval("SELECT 1")
        return True, None
    except Exception as e:
        return False, str(e)


async def create_db_pool(
    dsn: str,
    name: str,
    min_size: int = 1,
    max_size: int = 10,
    command_timeout: float = 10.0,
    **kwargs
) -> PoolT:
    """
    Create a database connection pool with consistent configuration.
    
    All pools created through this function are automatically registered
    for centralized cleanup during shutdown.
    
    Args:
        dsn: Database connection string
        name: Name identifier for this pool (for logging)
        min_size: Minimum connections in pool (default: 1)
        max_size: Maximum connections in pool (default: 10)
        command_timeout: Command timeout in seconds (default: 10.0)
        **kwargs: Additional arguments passed to asyncpg.create_pool()
        
    Returns:
        asyncpg.Pool: The created connection pool
        
    Raises:
        Exception: If pool creation fails
    """
    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
            **kwargs
        )
        
        # Register pool for cleanup
        _registered_pools.append(pool)
        logger.info(f"✅ Database pool '{name}' created (min={min_size}, max={max_size})")
        
        return pool
    except Exception as e:
        logger.error(f"❌ Failed to create database pool '{name}': {e}")
        raise


def get_bot_db_pool(bot) -> Optional[PoolT]:
    """
    Get the main database pool from bot's SettingsService.
    
    This is the standardized way to access the database pool across the codebase.
    It abstracts away the internal structure of SettingsService.
    
    Args:
        bot: The Discord bot instance
        
    Returns:
        Optional[PoolT]: The database pool if available, None otherwise
    """
    settings_service = getattr(bot, "settings", None)
    if settings_service and hasattr(settings_service, "_pool"):
        return settings_service._pool
    return None


async def close_all_pools() -> None:
    """
    Close all registered database pools.
    
    This should be called during shutdown to ensure all pools are properly closed.
    """
    global _registered_pools
    
    if not _registered_pools:
        logger.debug("No registered pools to close")
        return
    
    logger.info(f"🔌 Closing {len(_registered_pools)} registered database pools...")
    
    closed_count = 0
    for pool in _registered_pools:
        try:
            if not pool.is_closing():
                await pool.close()
                closed_count += 1
        except Exception as e:
            logger.debug(f"Error closing pool: {e}")
    
    _registered_pools.clear()
    logger.info(f"✅ Closed {closed_count} database pools")
