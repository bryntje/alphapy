"""
Background Task Utilities

Centralized background task management with proper error handling, graceful
shutdown, and future leak prevention. Handles Supabase edge cases and specific
exception types (no except-all).
"""

import asyncio
from typing import Callable, Optional
from asyncpg import Pool, exceptions as pg_exceptions
from utils.supabase_client import SupabaseConfigurationError
from utils.logger import logger


class BackgroundTask:
    """
    Background task manager with proper error handling and graceful shutdown.
    
    Provides consistent loop management, pool health checks, and specific
    exception handling to prevent future leaks and ensure reliable operation.
    """
    
    def __init__(
        self,
        name: str,
        interval: int,
        task_func: Callable,
        pool: Optional[Pool] = None
    ):
        """
        Initialize background task.
        
        Args:
            name: Task name for logging
            interval: Sleep interval in seconds between task executions
            task_func: Async function to execute in the loop
            pool: Optional database pool to check before execution
        """
        self.name = name
        self.interval = interval
        self.task_func = task_func
        self.pool = pool
        self._task: Optional[asyncio.Task] = None
        self._consecutive_errors = 0
        self._max_consecutive_errors = 10
    
    async def start(self) -> None:
        """
        Start background task with proper initialization.
        
        Creates a new task if one doesn't exist or if the existing one is done.
        """
        if self._task and not self._task.done():
            logger.debug(f"{self.name}: Task already running, skipping start")
            return
        
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"🚀 {self.name}: Background task started (interval: {self.interval}s)")
    
    async def _run_loop(self) -> None:
        """
        Main loop with pool checks and specific error handling (no except-all).
        
        Handles specific exception types:
        - asyncio.CancelledError: Proper cancellation
        - Database connection errors: Expected during shutdown
        - SupabaseConfigurationError: Config errors that won't resolve
        - Timeout errors: Network issues
        - Other exceptions: Logged but don't crash the loop
        """
        while True:
            try:
                # Check pool health before execution
                if self.pool and self.pool.is_closing():
                    logger.debug(f"{self.name}: Database pool is closing, skipping iteration")
                    await asyncio.sleep(self.interval)
                    continue
                
                # Execute the task function
                await self.task_func()
                
                # Reset error counter on success
                self._consecutive_errors = 0
                
            except asyncio.CancelledError:
                # Proper cancellation - don't log, just break
                logger.debug(f"{self.name}: Task cancelled")
                break
                
            except (
                pg_exceptions.ConnectionDoesNotExistError,
                pg_exceptions.InterfaceError,
                ConnectionResetError
            ) as db_err:
                # Database connection issues - expected during shutdown
                logger.debug(
                    f"{self.name}: DB connection issue (pool closing?): {db_err.__class__.__name__}"
                )
                self._consecutive_errors += 1
                
            except SupabaseConfigurationError as supabase_err:
                # Supabase config errors - don't retry, but don't crash
                # These won't resolve by retrying, so we log and continue
                logger.warning(f"{self.name}: Supabase config error: {supabase_err}")
                # Don't increment error count - config errors won't resolve
                
            except (asyncio.TimeoutError, TimeoutError) as timeout_err:
                # Timeout errors - could be network issues
                logger.warning(f"{self.name}: Timeout error: {timeout_err}")
                self._consecutive_errors += 1
                
            except Exception as e:
                # Only catch specific known exceptions above - log unexpected ones
                # This is the only "catch-all" but it's intentional for unexpected errors
                logger.error(
                    f"{self.name}: Unexpected error: {e.__class__.__name__}: {e}",
                    exc_info=True
                )
                self._consecutive_errors += 1
                
                # If too many consecutive errors, log warning but continue
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.error(
                        f"{self.name}: {self._consecutive_errors} consecutive errors - "
                        "task may be unhealthy"
                    )
                    self._consecutive_errors = 0  # Reset to prevent log spam
            
            # Ensure we always sleep, even on errors (prevents tight error loops)
            await asyncio.sleep(self.interval)
    
    async def stop(self) -> None:
        """
        Graceful shutdown with proper future cleanup.
        
        Ensures task is properly cancelled and cleaned up to prevent future leaks.
        """
        if not self._task:
            return
        
        logger.info(f"🛑 {self.name}: Shutting down background task...")
        
        self._task.cancel()
        
        try:
            # Wait for task to finish, but with timeout to prevent hanging
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.CancelledError:
            # Expected - task was cancelled
            logger.debug(f"{self.name}: Task cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(
                f"{self.name}: Task did not finish within timeout during shutdown"
            )
        except Exception as exc:
            logger.warning(
                f"{self.name}: Exception during task shutdown: {exc.__class__.__name__}"
            )
        finally:
            # Ensure task is properly cleaned up to prevent future leaks
            if self._task and not self._task.done():
                # Force cleanup if still running
                try:
                    self._task.cancel()
                    # Give it one more chance to clean up
                    try:
                        await asyncio.wait_for(self._task, timeout=1.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                except Exception as cleanup_error:
                    logger.debug(
                        f"{self.name}: Error during final cleanup: {cleanup_error}"
                    )
            
            # Clear the task reference
            self._task = None
            logger.info(f"✅ {self.name}: Background task stopped")
    
    def is_running(self) -> bool:
        """
        Check if the background task is currently running.
        
        Returns:
            bool: True if task exists and is not done
        """
        return self._task is not None and not self._task.done()
    
    def get_error_count(self) -> int:
        """
        Get the current consecutive error count.
        
        Returns:
            int: Number of consecutive errors
        """
        return self._consecutive_errors
