"""
Auto-Moderation Analytics Service

Provides analytics and metrics for auto-moderation performance and effectiveness.
"""

import csv
import io
import logging
from typing import Any

import asyncpg
from discord.ext import commands

from utils.db_helpers import acquire_safe, get_bot_db_pool

log = logging.getLogger(__name__)


class AutoModAnalytics:
    """Analytics service for auto-moderation metrics."""
    
    def __init__(self, bot: commands.Bot | None = None):
        self.bot = bot
    
    def _get_pool(self) -> asyncpg.Pool | None:
        if not self.bot:
            return None
        return get_bot_db_pool(self.bot)
    
    async def get_rule_effectiveness(self, guild_id: int, rule_id: int, days: int = 30) -> dict[str, Any]:
        """
        Get effectiveness metrics for a specific rule.
        
        Returns:
            - trigger_count: number of times rule was triggered
            - false_positive_rate: estimated false positive percentage
            - avg_response_time: average time to action
            - top_violators: list of user_ids with most violations
        """
        pool = self._get_pool()
        if not pool:
            return {}
        
        try:
            async with acquire_safe(pool) as conn:
                trigger_count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM automod_logs
                    WHERE guild_id = $1 AND rule_id = $2
                      AND timestamp > NOW() - ($3::text || ' days')::interval
                    """,
                    guild_id,
                    rule_id,
                    days,
                ) or 0
                
                top_violators = await conn.fetch(
                    """
                    SELECT user_id, COUNT(*) AS count
                    FROM automod_logs
                    WHERE guild_id = $1 AND rule_id = $2
                      AND timestamp > NOW() - ($3::text || ' days')::interval
                    GROUP BY user_id
                    ORDER BY count DESC
                    LIMIT 5
                    """,
                    guild_id,
                    rule_id,
                    days,
                )
                
                stats = await conn.fetchrow(
                    """
                    SELECT
                        COALESCE(SUM(triggers_count), 0)   AS total_triggers,
                        COALESCE(SUM(false_positives), 0)  AS total_fp,
                        AVG(NULLIF(avg_response_time, 0))  AS avg_rt
                    FROM automod_stats
                    WHERE guild_id = $1 AND rule_id = $2
                      AND date > CURRENT_DATE - ($3::text || ' days')::interval
                    """,
                    guild_id,
                    rule_id,
                    days,
                )
                total_t = int(stats["total_triggers"]) if stats else 0
                total_fp = int(stats["total_fp"]) if stats else 0
                false_positive_rate = round((total_fp / total_t * 100), 2) if total_t > 0 else 0.0
                avg_response_time = round(float(stats["avg_rt"]), 3) if stats and stats["avg_rt"] else 0.0

                return {
                    "trigger_count": int(trigger_count),
                    "false_positive_rate": false_positive_rate,
                    "avg_response_time": avg_response_time,
                    "top_violators": [
                        {"user_id": int(row["user_id"]), "count": int(row["count"])}
                        for row in top_violators
                    ],
                }
        except Exception as e:
            log.error(f"Error getting rule effectiveness for rule {rule_id}: {e}")
            return {}
    
    async def get_guild_overview(self, guild_id: int, days: int = 7) -> dict[str, Any]:
        """
        Get overview metrics for a guild's auto-moderation activity.
        
        Returns:
            - total_violations: total number of violations
            - total_actions: breakdown by action type
            - most_triggered_rules: top 5 rules by trigger count
            - trend: daily violation trend
        """
        pool = self._get_pool()
        if not pool:
            return {}
        
        try:
            async with acquire_safe(pool) as conn:
                total_violations = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM automod_logs
                    WHERE guild_id = $1
                      AND timestamp > NOW() - ($2::text || ' days')::interval
                    """,
                    guild_id,
                    days,
                ) or 0
                
                action_breakdown = await conn.fetch(
                    """
                    SELECT action_taken, COUNT(*) AS count
                    FROM automod_logs
                    WHERE guild_id = $1
                      AND timestamp > NOW() - ($2::text || ' days')::interval
                    GROUP BY action_taken
                    ORDER BY count DESC
                    """,
                    guild_id,
                    days,
                )
                
                most_triggered = await conn.fetch(
                    """
                    SELECT rule_id, COUNT(*) AS count
                    FROM automod_logs
                    WHERE guild_id = $1
                      AND timestamp > NOW() - ($2::text || ' days')::interval
                    GROUP BY rule_id
                    ORDER BY count DESC
                    LIMIT 5
                    """,
                    guild_id,
                    days,
                )
                
                daily_trend = await conn.fetch(
                    """
                    SELECT
                        DATE(timestamp) AS day,
                        COUNT(*) AS count
                    FROM automod_logs
                    WHERE guild_id = $1
                      AND timestamp > NOW() - ($2::text || ' days')::interval
                    GROUP BY DATE(timestamp)
                    ORDER BY day
                    """,
                    guild_id,
                    days,
                )

                return {
                    "total_violations": int(total_violations),
                    "total_actions": {
                        row["action_taken"]: int(row["count"])
                        for row in action_breakdown
                    },
                    "most_triggered_rules": [
                        {"rule_id": int(row["rule_id"]), "count": int(row["count"])}
                        for row in most_triggered
                    ],
                    "trend": {
                        str(row["day"]): int(row["count"])
                        for row in daily_trend
                    },
                }
        except Exception as e:
            log.error(f"Error getting guild overview for guild {guild_id}: {e}")
            return {}
    
    async def export_metrics(self, guild_id: int, days: int = 30, format: str = "csv") -> str:
        """
        Export rule effectiveness metrics as CSV.

        Returns CSV string with columns:
        rule_id, triggers, false_positives, false_positive_rate_pct, avg_response_time_s, top_violator_id, top_violator_count
        """
        pool = self._get_pool()
        if not pool:
            return ""
        try:
            async with acquire_safe(pool) as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        l.rule_id,
                        COUNT(*) AS triggers,
                        COALESCE(s.false_positives, 0) AS false_positives,
                        CASE WHEN COUNT(*) > 0
                            THEN ROUND(COALESCE(s.false_positives, 0)::numeric / COUNT(*) * 100, 2)
                            ELSE 0
                        END AS false_positive_rate_pct,
                        COALESCE(ROUND(CAST(s.avg_response_time AS numeric), 3), 0) AS avg_response_time_s
                    FROM automod_logs l
                    LEFT JOIN automod_stats s
                        ON s.guild_id = l.guild_id AND s.rule_id = l.rule_id
                           AND s.date > CURRENT_DATE - ($2::text || ' days')::interval
                    WHERE l.guild_id = $1
                      AND l.timestamp > NOW() - ($2::text || ' days')::interval
                    GROUP BY l.rule_id, s.false_positives, s.avg_response_time
                    ORDER BY triggers DESC
                    """,
                    guild_id,
                    days,
                )
            if not rows:
                return ""
            fieldnames = ["rule_id", "triggers", "false_positives", "false_positive_rate_pct", "avg_response_time_s"]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows([dict(r) for r in rows])
            return buf.getvalue()
        except Exception as e:
            log.error(f"Error exporting metrics for guild {guild_id}: {e}")
            return ""
