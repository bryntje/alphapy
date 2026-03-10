"""
Auto-Moderation Logging System

Provides comprehensive logging for auto-mod actions, violations, and statistics.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import asyncpg
import discord

from utils.db_helpers import acquire_safe
from utils.logger import logger

log = logging.getLogger(__name__)


class AutoModLogger:
    """Specialized logging system for auto-moderation events."""
    
    def __init__(self):
        self._buffer: List[Dict] = []
        self._buffer_size = 50
        self._last_flush = 0
        
    async def log_violation(self, guild_id: int, user_id: int, message_id: Optional[int],
                           channel_id: Optional[int], rule_id: int, action_type: str,
                           message_content: Optional[str] = None, ai_analysis: Optional[Dict] = None,
                           context: Optional[Dict] = None):
        """Log a rule violation and action taken."""
        try:
            log_entry = {
                'guild_id': guild_id,
                'user_id': user_id,
                'message_id': message_id,
                'channel_id': channel_id,
                'rule_id': rule_id,
                'action_taken': action_type,
                'message_content': message_content[:1000] if message_content else None,  # Limit length
                'ai_analysis': ai_analysis,
                'context': context,
                'timestamp': datetime.utcnow()
            }
            
            # Add to buffer for batch processing
            self._buffer.append(log_entry)
            
            # Flush if buffer is full or it's been more than 30 seconds
            import time
            if (len(self._buffer) >= self._buffer_size or 
                time.time() - self._last_flush > 30):
                await self._flush_buffer()
                
            # Also log to standard logger for immediate visibility
            log.info(f"Auto-mod violation: Guild {guild_id}, User {user_id}, Action: {action_type}, Rule: {rule_id}")
            
        except Exception as e:
            log.error(f"Error logging auto-mod violation: {e}")
            
    async def _flush_buffer(self):
        """Flush the log buffer to database."""
        if not self._buffer:
            return
            
        try:
            # Get database pool from global context or pass it in
            # For now, we'll need to modify this to work with the existing architecture
            entries = self._buffer.copy()
            self._buffer.clear()
            self._last_flush = 0
            
            # This would need to be called with a database pool
            # await self._insert_log_entries(entries)
            
        except Exception as e:
            log.error(f"Error flushing auto-mod log buffer: {e}")
            
    async def get_violation_history(self, guild_id: int, user_id: Optional[int] = None,
                                  limit: int = 100, days: int = 30) -> List[Dict]:
        """Get violation history for a guild or specific user."""
        try:
            # This would need database access
            # For now, return empty list
            return []
            
        except Exception as e:
            log.error(f"Error getting violation history: {e}")
            return []
            
    async def get_statistics(self, guild_id: int, days: int = 7) -> Dict[str, Any]:
        """Get moderation statistics for a guild."""
        try:
            # This would need database access
            # For now, return empty stats
            return {
                'total_violations': 0,
                'unique_users': 0,
                'top_rules': [],
                'daily_breakdown': {}
            }
            
        except Exception as e:
            log.error(f"Error getting moderation statistics: {e}")
            return {}
            
    async def create_appeal(self, guild_id: int, user_id: int, log_id: int, reason: str):
        """Create an appeal for a moderation action."""
        try:
            # This would need database access
            log.info(f"Appeal created: Guild {guild_id}, User {user_id}, Log {log_id}")
            
        except Exception as e:
            log.error(f"Error creating appeal: {e}")
            
    def format_log_entry(self, entry: Dict) -> str:
        """Format a log entry for display."""
        timestamp = entry.get('timestamp', datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S')
        user_id = entry.get('user_id', 'Unknown')
        action = entry.get('action_taken', 'Unknown')
        rule_id = entry.get('rule_id', 'Unknown')
        
        return f"[{timestamp}] User {user_id} - {action} (Rule {rule_id})"
        
    async def export_logs(self, guild_id: int, days: int = 30, format: str = 'json') -> str:
        """Export logs for a guild in specified format."""
        try:
            # This would need database access
            # For now, return empty string
            return ""
            
        except Exception as e:
            log.error(f"Error exporting logs: {e}")
            return ""
