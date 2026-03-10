"""
Auto-Moderation Rule Processing Engine

Handles rule evaluation, configuration, and execution logic for the auto-mod system.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

import discord
from discord.ext import commands
import asyncpg

from utils.db_helpers import acquire_safe
from utils.logger import logger

log = logging.getLogger(__name__)


class RuleType(Enum):
    """Types of auto-mod rules."""
    SPAM = "spam"
    CONTENT = "content"
    AI = "ai"
    REGEX = "regex"


class ActionType(Enum):
    """Types of actions that can be taken."""
    DELETE = "delete"
    WARN = "warn"
    MUTE = "mute"
    TIMEOUT = "timeout"
    BAN = "ban"


@dataclass
class RuleResult:
    """Result of rule evaluation."""
    triggered: bool
    confidence: float
    reason: str
    context: Dict[str, Any]


class RuleProcessor:
    """Processes and evaluates auto-mod rules."""
    
    def __init__(self, bot: Optional[commands.Bot] = None):
        self.bot = bot
        self._rules_cache: Dict[int, List[Dict]] = {}  # guild_id -> rules
        self._cache_ttl = 300  # 5 minutes
        self._cache_updated: Dict[int, float] = {}
        
    async def load_rules(self):
        """Load all rules from database into cache."""
        try:
            pool = getattr(self.bot, 'db_pool', None) if self.bot else None
            if not pool:
                log.warning("No database pool available for rule loading")
                return
                
            async with acquire_safe(pool) as conn:
                rules = await conn.fetch("""
                    SELECT r.*, a.action_type, a.config as action_config
                    FROM automod_rules r
                    LEFT JOIN automod_actions a ON r.action_id = a.id
                    WHERE r.enabled = true
                    ORDER BY r.severity DESC
                """)
                
            # Organize by guild
            self._rules_cache.clear()
            for rule in rules:
                guild_id = rule['guild_id']
                if guild_id not in self._rules_cache:
                    self._rules_cache[guild_id] = []
                self._rules_cache[guild_id].append(dict(rule))
                
            log.info(f"Loaded {len(rules)} auto-mod rules into cache")
            
        except Exception as e:
            log.error(f"Error loading auto-mod rules: {e}")
            
    async def get_active_rules(self, guild_id: int) -> List[Dict]:
        """Get active rules for a guild, with cache refresh if needed."""
        current_time = time.time()
        
        # Check if cache needs refresh
        if (guild_id not in self._cache_updated or 
            current_time - self._cache_updated.get(guild_id, 0) > self._cache_ttl):
            
            await self._refresh_guild_rules(guild_id)
            self._cache_updated[guild_id] = current_time
            
        return self._rules_cache.get(guild_id, [])
        
    async def _refresh_guild_rules(self, guild_id: int):
        """Refresh rules for a specific guild."""
        try:
            pool = getattr(self.bot, 'db_pool', None) if hasattr(self, 'bot') else None
            if not pool:
                return
                
            async with acquire_safe(pool) as conn:
                rules = await conn.fetch("""
                    SELECT r.*, a.action_type, a.config as action_config
                    FROM automod_rules r
                    LEFT JOIN automod_actions a ON r.action_id = a.id
                    WHERE r.guild_id = $1 AND r.enabled = true
                    ORDER BY r.severity DESC
                """, guild_id)
                
            self._rules_cache[guild_id] = [dict(rule) for rule in rules]
            
        except Exception as e:
            log.error(f"Error refreshing rules for guild {guild_id}: {e}")
            
    async def evaluate_rule(self, rule: Dict, message: discord.Message, user_context: Dict[str, Any]) -> RuleResult:
        """Evaluate a single rule against a message."""
        rule_type = rule['rule_type']
        config = rule.get('config', {})
        
        try:
            if rule_type == RuleType.SPAM.value:
                return await self._evaluate_spam_rule(rule, message, user_context)
            elif rule_type == RuleType.CONTENT.value:
                return await self._evaluate_content_rule(rule, message)
            elif rule_type == RuleType.REGEX.value:
                return await self._evaluate_regex_rule(rule, message)
            elif rule_type == RuleType.AI.value:
                return await self._evaluate_ai_rule(rule, message, user_context)
            else:
                log.warning(f"Unknown rule type: {rule_type}")
                return RuleResult(False, 0.0, "Unknown rule type", {})
                
        except Exception as e:
            log.error(f"Error evaluating rule {rule['id']}: {e}")
            return RuleResult(False, 0.0, f"Error: {e}", {})
            
    async def _evaluate_spam_rule(self, rule: Dict, message: discord.Message, user_context: Dict[str, Any]) -> RuleResult:
        """Evaluate spam-related rules."""
        config = rule.get('config', {})
        spam_type = config.get('spam_type', 'frequency')
        
        if spam_type == 'frequency':
            # Check message frequency
            max_messages = config.get('max_messages', 5)
            time_window = config.get('time_window', 60)  # seconds
            
            message_count = len(user_context.get('message_timestamps', []))
            recent_messages = [
                ts for ts in user_context.get('message_timestamps', [])
                if time.time() - ts < time_window
            ]
            
            if len(recent_messages) >= max_messages:
                return RuleResult(
                    True,
                    min(1.0, len(recent_messages) / max_messages),
                    f"Too many messages ({len(recent_messages)} in {time_window}s)",
                    {'message_count': len(recent_messages), 'time_window': time_window}
                )
                
        elif spam_type == 'duplicate':
            # Check for duplicate messages
            last_message = user_context.get('last_message', '')
            if message.content.lower() == last_message.lower():
                max_duplicates = config.get('max_duplicates', 3)
                
                # Count duplicates in recent messages
                duplicates = sum(1 for ts in user_context.get('message_timestamps', [])[-max_duplicates:])
                
                if duplicates >= max_duplicates:
                    return RuleResult(
                        True,
                        0.9,
                        f"Duplicate message spam detected",
                        {'duplicate_count': duplicates}
                    )
                    
        elif spam_type == 'caps':
            # Check excessive caps usage
            min_length = config.get('min_length', 10)
            max_caps_ratio = config.get('max_caps_ratio', 0.7)
            
            if len(message.content) >= min_length:
                caps_count = sum(1 for c in message.content if c.isupper())
                caps_ratio = caps_count / len(message.content)
                
                if caps_ratio > max_caps_ratio:
                    return RuleResult(
                        True,
                        min(1.0, caps_ratio),
                        f"Excessive caps usage ({caps_ratio:.1%})",
                        {'caps_ratio': caps_ratio, 'caps_count': caps_count}
                    )
                    
        return RuleResult(False, 0.0, "No spam detected", {})
        
    async def _evaluate_content_rule(self, rule: Dict, message: discord.Message) -> RuleResult:
        """Evaluate content-based rules."""
        config = rule.get('config', {})
        content_type = config.get('content_type', 'bad_words')
        content_lower = message.content.lower()
        
        if content_type == 'bad_words':
            # Check for bad words
            bad_words = config.get('words', [])
            found_words = [word for word in bad_words if word.lower() in content_lower]
            
            if found_words:
                return RuleResult(
                    True,
                    min(1.0, len(found_words) / 5),
                    f"Bad words detected: {', '.join(found_words[:3])}",
                    {'found_words': found_words, 'word_count': len(found_words)}
                )
                
        elif content_type == 'links':
            # Check for unwanted links
            allow_links = config.get('allow_links', False)
            whitelist = config.get('whitelist', [])
            blacklist = config.get('blacklist', [])
            
            # Simple URL detection
            url_pattern = r'https?://[^\s]+'
            urls = re.findall(url_pattern, message.content, re.IGNORECASE)
            
            if urls and not allow_links:
                # Check against whitelist/blacklist
                for url in urls:
                    domain = re.search(r'https?://([^/]+)', url.lower())
                    if domain:
                        domain = domain.group(1)
                        
                        if whitelist and not any(allowed in domain for allowed in whitelist):
                            return RuleResult(
                                True,
                                0.8,
                                f"Unallowed link detected: {domain}",
                                {'url': url, 'domain': domain}
                            )
                            
                        if blacklist and any(blocked in domain for blocked in blacklist):
                            return RuleResult(
                                True,
                                0.9,
                                f"Blacklisted link detected: {domain}",
                                {'url': url, 'domain': domain}
                            )
                                
        elif content_type == 'mentions':
            # Check for mention spam
            max_mentions = config.get('max_mentions', 5)
            mention_count = len(message.mentions)
            
            if mention_count > max_mentions:
                return RuleResult(
                    True,
                    min(1.0, mention_count / (max_mentions * 2)),
                    f"Too many mentions ({mention_count})",
                    {'mention_count': mention_count, 'max_allowed': max_mentions}
                )
                
        return RuleResult(False, 0.0, "No content violation", {})
        
    async def _evaluate_regex_rule(self, rule: Dict, message: discord.Message) -> RuleResult:
        """Evaluate regex-based rules."""
        config = rule.get('config', {})
        patterns = config.get('patterns', [])
        
        for pattern_str in patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                matches = pattern.findall(message.content)
                
                if matches:
                    return RuleResult(
                        True,
                        min(1.0, len(matches) / 3),
                        f"Regex pattern matched: {pattern_str}",
                        {'pattern': pattern_str, 'matches': matches}
                    )
                    
            except re.error as e:
                log.warning(f"Invalid regex pattern '{pattern_str}': {e}")
                
        return RuleResult(False, 0.0, "No regex matches", {})
        
    async def _evaluate_ai_rule(self, rule: Dict, message: discord.Message, user_context: Dict[str, Any]) -> RuleResult:
        """Evaluate AI-powered rules (premium feature)."""
        # This will be implemented in Phase 2 with Grok integration
        # For now, return no violation
        return RuleResult(False, 0.0, "AI rules not yet implemented", {})
        
    async def create_rule(self, guild_id: int, rule_type: str, name: str, config: Dict, 
                         action_type: str, action_config: Dict, created_by: int, is_premium: bool = False) -> int:
        """Create a new auto-mod rule."""
        try:
            pool = getattr(self.bot, 'db_pool', None) if hasattr(self, 'bot') else None
            if not pool:
                raise ValueError("Database not available")
                
            async with acquire_safe(pool) as conn:
                # First create the action
                action_id = await conn.fetchval("""
                    INSERT INTO automod_actions (guild_id, action_type, config, is_premium, created_by)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """, guild_id, action_type, action_config, is_premium, created_by)
                
                # Then create the rule
                rule_id = await conn.fetchval("""
                    INSERT INTO automod_rules (guild_id, rule_type, name, config, action_id, created_by, is_premium)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                """, guild_id, rule_type, name, config, action_id, created_by, is_premium)
                
                # Clear cache for this guild
                if guild_id in self._rules_cache:
                    del self._rules_cache[guild_id]
                    
                return rule_id
                
        except Exception as e:
            log.error(f"Error creating auto-mod rule: {e}")
            raise
