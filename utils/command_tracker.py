"""
Command usage tracking utility for analytics.

This module provides decorators and helpers to track command usage
across all Discord bot commands (slash and text commands).
"""

import functools
import logging
import asyncio
from typing import Optional, Callable, Any, List, Dict
from dataclasses import dataclass
from datetime import datetime
import discord
from discord.ext import commands
import asyncpg
from asyncpg import exceptions as pg_exceptions

logger = logging.getLogger("bot")

# Global database pool reference (set by bot initialization)
_db_pool: Optional[asyncpg.Pool] = None

# In-memory queue for batching command usage logs
@dataclass
class CommandUsageEntry:
    """Entry in the command usage queue."""
    guild_id: int
    user_id: int
    command_name: str
    command_type: str
    success: bool
    error_message: Optional[str]

_command_queue: List[CommandUsageEntry] = []
MAX_QUEUE_SIZE = 10000
FLUSH_THRESHOLD = 1000
FLUSH_INTERVAL = 30  # seconds
_flush_task: Optional[asyncio.Task] = None

# Export _db_pool for checking if it's already initialized
__all__ = ['set_db_pool', 'log_command_usage', 'track_command', '_db_pool', 'start_flush_task', 'stop_flush_task']


def set_db_pool(pool: asyncpg.Pool) -> None:
    """Set the database pool for command tracking."""
    global _db_pool
    # Close existing pool if any
    if _db_pool and not _db_pool.is_closing():
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule close in the event loop
                asyncio.create_task(_db_pool.close())
            else:
                loop.run_until_complete(_db_pool.close())
        except Exception as e:
            logger.debug(f"Error closing old command tracker pool: {e}")
    _db_pool = pool
    logger.info("✅ Command tracker: Database pool set")


async def log_command_usage(
    guild_id: Optional[int],
    user_id: int,
    command_name: str,
    command_type: str,
    success: bool = True,
    error_message: Optional[str] = None
) -> None:
    """
    Log command usage to in-memory queue (batched writes to audit_logs table).
    
    Args:
        guild_id: Guild ID (None for DMs)
        user_id: User ID who executed the command
        command_name: Name of the command
        command_type: 'slash' or 'text'
        success: Whether command executed successfully
        error_message: Error message if command failed
    """
    # Use 0 for guild_id if None (DMs)
    effective_guild_id = guild_id if guild_id is not None else 0
    
    # Add to queue (thread-safe append)
    global _command_queue
    if len(_command_queue) >= MAX_QUEUE_SIZE:
        # Queue full - drop oldest entry (FIFO)
        _command_queue.pop(0)
        logger.warning(f"Command tracker queue full ({MAX_QUEUE_SIZE}), dropping oldest entry")
    
    entry = CommandUsageEntry(
        guild_id=effective_guild_id,
        user_id=user_id,
        command_name=command_name,
        command_type=command_type,
        success=success,
        error_message=error_message
    )
    _command_queue.append(entry)
    
    # Trigger flush if threshold reached
    if len(_command_queue) >= FLUSH_THRESHOLD:
        asyncio.create_task(_flush_command_queue())


async def _flush_command_queue() -> None:
    """Flush command usage queue to database in batches."""
    global _command_queue
    
    if not _command_queue:
        return
    
    if _db_pool is None:
        logger.debug("Command tracking: Database pool not initialized yet, skipping flush")
        return
    
    if _db_pool.is_closing():
        logger.debug("Command tracking: Database pool is closing, skipping flush")
        return
    
    # Copy queue and clear it
    queue_copy = _command_queue.copy()
    queue_size = len(queue_copy)
    _command_queue.clear()
    
    if queue_size == 0:
        return
    
    try:
        async with _db_pool.acquire() as conn:
            # Use execute_many for batch insert
            await conn.executemany(
                """
                INSERT INTO audit_logs (guild_id, user_id, command_name, command_type, success, error_message)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [
                    (
                        entry.guild_id,
                        entry.user_id,
                        entry.command_name,
                        entry.command_type,
                        entry.success,
                        entry.error_message
                    )
                    for entry in queue_copy
                ]
            )
        logger.debug(f"Command tracker: Flushed {queue_size} entries to database")
    except pg_exceptions.UndefinedTableError:
        logger.warning("Command tracking: audit_logs table does not exist yet. Queue will be retried on next flush.")
        # Re-add entries to queue for retry
        _command_queue.extend(queue_copy)
    except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
        logger.debug(f"Command tracking: Database connection unavailable (pool closing?): {conn_err.__class__.__name__}")
        # Re-add entries to queue for retry
        _command_queue.extend(queue_copy)
    except Exception as e:
        logger.warning(f"Command tracking flush failed (non-critical): {e}", exc_info=True)
        # Re-add entries to queue for retry (but limit to prevent infinite growth)
        if len(_command_queue) < MAX_QUEUE_SIZE:
            _command_queue.extend(queue_copy)


async def _periodic_flush_loop() -> None:
    """Background task that periodically flushes the command queue."""
    global _command_queue
    
    while True:
        try:
            await asyncio.sleep(FLUSH_INTERVAL)
            
            queue_size = len(_command_queue)
            if queue_size > 0:
                logger.debug(f"Command tracker: Periodic flush triggered, queue size: {queue_size}")
                await _flush_command_queue()
                logger.debug(f"Command tracker: Queue size after flush: {len(_command_queue)}")
        except asyncio.CancelledError:
            # Final flush on shutdown
            logger.info("Command tracker: Flush task cancelled, performing final flush...")
            await _flush_command_queue()
            logger.info(f"Command tracker: Final flush complete, remaining queue size: {len(_command_queue)}")
            raise
        except Exception as e:
            logger.error(f"Command tracker: Error in periodic flush loop: {e}", exc_info=True)
            await asyncio.sleep(FLUSH_INTERVAL)  # Wait before retrying


def start_flush_task() -> None:
    """Start the periodic flush task."""
    global _flush_task
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_periodic_flush_loop())
        logger.info("✅ Command tracker: Periodic flush task started")


def stop_flush_task() -> None:
    """Stop the periodic flush task and perform final flush."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        _flush_task.cancel()
        try:
            # Wait for task to complete (with timeout)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule wait in event loop
                asyncio.create_task(asyncio.wait_for(_flush_task, timeout=5.0))
            else:
                loop.run_until_complete(asyncio.wait_for(_flush_task, timeout=5.0))
        except Exception as e:
            logger.debug(f"Command tracker: Error stopping flush task: {e}")


def track_command(command_type: str = "slash"):
    """
    Decorator to track command usage.
    
    Usage:
        @track_command("slash")
        @app_commands.command(...)
        async def my_command(interaction: discord.Interaction):
            ...
    
    Args:
        command_type: 'slash' or 'text'
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract interaction or context from args
            interaction: Optional[discord.Interaction] = None
            ctx: Optional[commands.Context] = None
            
            # Find interaction or context in args
            for arg in args:
                if isinstance(arg, discord.Interaction):
                    interaction = arg
                    break
                elif isinstance(arg, commands.Context):
                    ctx = arg
                    break
            
            # Determine command name and user info
            command_name = func.__name__
            user_id = 0
            guild_id: Optional[int] = None
            
            if interaction:
                command_name = interaction.command.name if interaction.command else func.__name__
                user_id = interaction.user.id
                guild_id = interaction.guild.id if interaction.guild else None
            elif ctx:
                command_name = ctx.command.name if ctx.command else func.__name__
                user_id = ctx.author.id
                guild_id = ctx.guild.id if ctx.guild else None
            
            # Track command execution
            success = True
            error_message = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_message = str(e)[:500]  # Truncate long error messages
                raise
            finally:
                # Log command usage (non-blocking)
                try:
                    await log_command_usage(
                        guild_id=guild_id,
                        user_id=user_id,
                        command_name=command_name,
                        command_type=command_type,
                        success=success,
                        error_message=error_message
                    )
                except Exception:
                    # Silently fail - tracking should never break commands
                    pass
        
        return wrapper
    return decorator
