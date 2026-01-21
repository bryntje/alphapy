"""
Command Tree Sync Utility

Centralized command sync management with cooldown protection, rate limit handling,
and automatic detection of guild-only commands.

Features:
- Cooldown tracking (30 min per-guild, 60 min global)
- Automatic guild-only command detection
- Safe sync with error handling
- Rate limit protection
"""

import time
from dataclasses import dataclass
from typing import Optional, Dict
import discord
from discord.ext import commands
from discord import app_commands
from utils.logger import logger

# Cooldown tracking: {key: last_sync_timestamp}
# Keys: "global" for global syncs, guild.id for per-guild syncs
_sync_cooldowns: Dict[str, float] = {}

# Cooldown periods in seconds
GLOBAL_COOLDOWN = 60 * 60  # 60 minutes
GUILD_COOLDOWN = 30 * 60   # 30 minutes

# Track if we've done initial global sync
_initial_global_sync_done = False


@dataclass
class SyncResult:
    """Result of a sync operation"""
    success: bool
    command_count: int
    error: Optional[str] = None
    cooldown_remaining: Optional[float] = None
    sync_type: str = "unknown"  # "global" or "guild"


def _get_cooldown_key(guild: Optional[discord.Guild]) -> str:
    """Get cooldown tracking key for a sync operation"""
    if guild is None:
        return "global"
    return str(guild.id)


def _check_cooldown(guild: Optional[discord.Guild], force: bool = False) -> Optional[float]:
    """
    Check if sync is on cooldown.
    
    Returns:
        None if not on cooldown, or seconds remaining if on cooldown
    """
    if force:
        return None
    
    key = _get_cooldown_key(guild)
    cooldown_period = GLOBAL_COOLDOWN if guild is None else GUILD_COOLDOWN
    
    if key not in _sync_cooldowns:
        return None
    
    last_sync = _sync_cooldowns[key]
    elapsed = time.time() - last_sync
    
    if elapsed < cooldown_period:
        remaining = cooldown_period - elapsed
        return remaining
    
    return None


def _update_cooldown(guild: Optional[discord.Guild]) -> None:
    """Update cooldown timestamp after successful sync"""
    key = _get_cooldown_key(guild)
    _sync_cooldowns[key] = time.time()


def detect_guild_only_commands(bot: commands.Bot) -> bool:
    """
    Detect if the command tree contains any guild-only commands.
    
    Returns:
        True if any guild-only commands are found, False otherwise
    """
    try:
        for command in bot.tree.walk_commands():
            # Check if command or its parent group is guild-only
            if hasattr(command, 'guild_only') and command.guild_only:
                return True
            
            # Check parent groups
            parent = command.parent
            while parent is not None:
                if hasattr(parent, 'guild_only') and parent.guild_only:
                    return True
                parent = getattr(parent, 'parent', None)
        
        return False
    except Exception as e:
        logger.warning(f"Error detecting guild-only commands: {e}")
        return False


async def safe_sync(
    bot: commands.Bot,
    guild: Optional[discord.Guild] = None,
    force: bool = False
) -> SyncResult:
    """
    Safely sync command tree with cooldown protection and error handling.
    
    Args:
        bot: Bot instance
        guild: Optional guild for per-guild sync. None for global sync.
        force: If True, bypass cooldown check
        
    Returns:
        SyncResult with sync status and details
    """
    sync_type = "guild" if guild else "global"
    start_time = time.time()
    
    # Check cooldown
    cooldown_remaining = _check_cooldown(guild, force)
    if cooldown_remaining is not None:
        minutes = int(cooldown_remaining / 60)
        seconds = int(cooldown_remaining % 60)
        message = f"Sync on cooldown. Wait {minutes}m {seconds}s before syncing again."
        logger.info(f"⏸️ {sync_type.capitalize()} sync skipped (cooldown): {message}")
        return SyncResult(
            success=False,
            command_count=0,
            error=message,
            cooldown_remaining=cooldown_remaining,
            sync_type=sync_type
        )
    
    # Perform sync
    try:
        if guild is None:
            # Global sync
            logger.info("🔄 Starting global command sync...")
            synced = await bot.tree.sync()
            command_count = len(synced)
            elapsed = time.time() - start_time
            logger.info(f"✅ Global sync completed: {command_count} commands synced in {elapsed:.2f}s")
            _update_cooldown(None)
            global _initial_global_sync_done
            _initial_global_sync_done = True
            return SyncResult(
                success=True,
                command_count=command_count,
                sync_type="global"
            )
        else:
            # Per-guild sync
            logger.info(f"🔄 Starting guild sync for {guild.name} (ID: {guild.id})...")
            # For guild-only commands, we don't need to copy global commands
            # Global commands are already available via global sync
            # Only sync the guild-specific command tree
            synced = await bot.tree.sync(guild=guild)
            command_count = len(synced)
            elapsed = time.time() - start_time
            logger.info(f"✅ Guild sync completed for {guild.name}: {command_count} commands synced in {elapsed:.2f}s")
            _update_cooldown(guild)
            return SyncResult(
                success=True,
                command_count=command_count,
                sync_type="guild"
            )
    
    except discord.HTTPException as e:
        elapsed = time.time() - start_time
        error_msg = f"Discord API error: {e}"
        
        # Check if it's a rate limit
        if e.status == 429:
            retry_after = getattr(e, 'retry_after', None)
            if retry_after:
                error_msg = f"Rate limited. Retry after {retry_after:.1f}s"
                # Update cooldown to retry_after time
                key = _get_cooldown_key(guild)
                _sync_cooldowns[key] = time.time() - (GUILD_COOLDOWN if guild else GLOBAL_COOLDOWN) + retry_after
        
        logger.error(f"❌ {sync_type.capitalize()} sync failed after {elapsed:.2f}s: {error_msg}")
        return SyncResult(
            success=False,
            command_count=0,
            error=error_msg,
            sync_type=sync_type
        )
    
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ {sync_type.capitalize()} sync failed after {elapsed:.2f}s: {error_msg}", exc_info=True)
        return SyncResult(
            success=False,
            command_count=0,
            error=error_msg,
            sync_type=sync_type
        )


def should_sync_global() -> bool:
    """
    Check if global sync should be performed.
    
    Returns:
        True if global sync hasn't been done yet, False otherwise
    """
    return not _initial_global_sync_done


def should_sync_guild(guild: discord.Guild) -> bool:
    """
    Check if guild sync should be performed.
    
    Args:
        guild: Guild to check
        
    Returns:
        True if guild has guild-only commands and sync is needed
    """
    # Always sync guild if we have guild-only commands
    # The cooldown check will prevent excessive syncs
    return True


def format_cooldown_message(remaining: float) -> str:
    """Format cooldown remaining time as human-readable message"""
    if remaining < 60:
        return f"{int(remaining)}s"
    elif remaining < 3600:
        minutes = int(remaining / 60)
        seconds = int(remaining % 60)
        return f"{minutes}m {seconds}s"
    else:
        hours = int(remaining / 3600)
        minutes = int((remaining % 3600) / 60)
        return f"{hours}h {minutes}m"
