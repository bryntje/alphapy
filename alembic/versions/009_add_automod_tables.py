"""Add auto-moderation tables

Revision ID: 009_add_automod_tables
Revises: 008_app_reflections
Create Date: 2026-03-10 12:30:00.000000

Adds tables for auto-moderation system including rules, actions, logs, and statistics.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009_add_automod_tables'
down_revision: Union[str, None] = '008_app_reflections'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Auto-mod actions table (must be created first for foreign key references)
    op.execute("""
        CREATE TABLE IF NOT EXISTS automod_actions (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            action_type TEXT NOT NULL, -- 'delete', 'warn', 'mute', 'timeout', 'ban'
            severity INTEGER DEFAULT 1,
            config JSONB NOT NULL,
            is_premium BOOLEAN DEFAULT false,
            created_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    # Auto-mod rules table
    op.execute("""
        CREATE TABLE IF NOT EXISTS automod_rules (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            rule_type TEXT NOT NULL, -- 'spam', 'content', 'ai', 'regex'
            name TEXT NOT NULL,
            enabled BOOLEAN DEFAULT true,
            config JSONB NOT NULL,
            action_id INTEGER REFERENCES automod_actions(id),
            created_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            is_premium BOOLEAN DEFAULT false
        )
    """)
    
    # Auto-mod logs table
    op.execute("""
        CREATE TABLE IF NOT EXISTS automod_logs (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            message_id BIGINT,
            channel_id BIGINT,
            rule_id INTEGER REFERENCES automod_rules(id),
            action_taken TEXT NOT NULL,
            message_content TEXT,
            ai_analysis JSONB,
            context JSONB,
            moderator_id BIGINT, -- For manual overrides
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            appeal_status TEXT DEFAULT 'none' -- 'none', 'pending', 'approved', 'denied'
        )
    """)
    
    # Auto-mod statistics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS automod_stats (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            rule_id INTEGER REFERENCES automod_rules(id),
            date DATE NOT NULL,
            triggers_count INTEGER DEFAULT 0,
            false_positives INTEGER DEFAULT 0,
            avg_response_time FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(guild_id, rule_id, date)
        )
    """)
    
    # Auto-mod user history table
    op.execute("""
        CREATE TABLE IF NOT EXISTS automod_user_history (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            rule_type TEXT NOT NULL,
            violation_count INTEGER DEFAULT 1,
            last_violation TIMESTAMPTZ DEFAULT NOW(),
            total_points INTEGER DEFAULT 0,
            context JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(guild_id, user_id, rule_type)
        )
    """)
    
    # Create indexes for performance
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_rules_guild_enabled ON automod_rules(guild_id, enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_rules_type ON automod_rules(rule_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_actions_guild ON automod_actions(guild_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_logs_guild_user ON automod_logs(guild_id, user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_logs_timestamp ON automod_logs(timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_logs_rule ON automod_logs(rule_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_stats_date ON automod_stats(date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automod_user_history_guild_user ON automod_user_history(guild_id, user_id)")


def downgrade() -> None:
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_automod_user_history_guild_user")
    op.execute("DROP INDEX IF EXISTS idx_automod_stats_date")
    op.execute("DROP INDEX IF EXISTS idx_automod_logs_rule")
    op.execute("DROP INDEX IF EXISTS idx_automod_logs_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_automod_logs_guild_user")
    op.execute("DROP INDEX IF EXISTS idx_automod_actions_guild")
    op.execute("DROP INDEX IF EXISTS idx_automod_rules_type")
    op.execute("DROP INDEX IF EXISTS idx_automod_rules_guild_enabled")
    
    # Drop tables in reverse order of creation (due to foreign key constraints)
    op.execute("DROP TABLE IF EXISTS automod_user_history")
    op.execute("DROP TABLE IF EXISTS automod_stats")
    op.execute("DROP TABLE IF EXISTS automod_logs")
    op.execute("DROP TABLE IF EXISTS automod_rules")
    op.execute("DROP TABLE IF EXISTS automod_actions")
