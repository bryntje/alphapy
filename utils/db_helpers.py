"""
Database Helper Utilities

Centralized database pool management and error handling to reduce boilerplate
across the codebase. Provides safe connection acquisition with automatic error
handling and reconnection logic.
"""

from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator, Callable, Any
import asyncpg
from asyncpg import exceptions as pg_exceptions
from utils.logger import logger


@asynccontextmanager
async def acquire_safe(
    pool: Optional[asyncpg.Pool],
    on_error: Optional[Callable[[Exception], Any]] = None
) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Safe pool acquire with automatic error handling and reconnection.
    
    Args:
        pool: The asyncpg connection pool (can be None)
        on_error: Optional callback function to handle connection errors
        
    Yields:
        asyncpg.Connection: A database connection from the pool
        
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
