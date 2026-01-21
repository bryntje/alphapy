"""
Command usage tracking utility for analytics.

This module provides decorators and helpers to track command usage
across all Discord bot commands (slash and text commands).
"""

import functools
import logging
from typing import Optional, Callable, Any
import discord
from discord.ext import commands
import asyncpg
from asyncpg import exceptions as pg_exceptions

logger = logging.getLogger("bot")

# Global database pool reference (set by bot initialization)
_db_pool: Optional[asyncpg.Pool] = None

# Export _db_pool for checking if it's already initialized
__all__ = ['set_db_pool', 'log_command_usage', 'track_command', '_db_pool']


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
    Log command usage to audit_logs table.
    
    Args:
        guild_id: Guild ID (None for DMs)
        user_id: User ID who executed the command
        command_name: Name of the command
        command_type: 'slash' or 'text'
        success: Whether command executed successfully
        error_message: Error message if command failed
    """
    if _db_pool is None:
        # Pool not initialized yet - log at debug level
        logger.debug("Command tracking: Database pool not initialized yet")
        return
    
    if _db_pool.is_closing():
        # Pool is closing - this is expected during shutdown
        logger.debug("Command tracking: Database pool is closing")
        return
    
    # Use 0 for guild_id if None (DMs)
    effective_guild_id = guild_id if guild_id is not None else 0
    
    try:
        async with _db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (guild_id, user_id, command_name, command_type, success, error_message)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                effective_guild_id,
                user_id,
                command_name,
                command_type,
                success,
                error_message
            )
    except pg_exceptions.UndefinedTableError:
        # Table doesn't exist yet - log at warning level so we know about it
        logger.warning("Command tracking: audit_logs table does not exist yet. Commands will not be tracked until table is created.")
    except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
        # Pool is closing or connection was lost - this is expected during shutdown
        logger.debug(f"Command tracking: Database connection unavailable (pool closing?): {conn_err.__class__.__name__}")
    except Exception as e:
        # Log at warning level so we can see if there are persistent issues
        logger.warning(f"Command tracking failed (non-critical): {e}", exc_info=True)


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
