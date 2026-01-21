"""Initial schema baseline

Revision ID: 001_initial
Revises: 
Create Date: 2026-01-21 13:00:00.000000

This migration represents the baseline schema as it exists in production.
All tables are created with IF NOT EXISTS to allow safe execution on existing databases.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bot settings tables (from utils/settings_service.py)
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            guild_id BIGINT NOT NULL,
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            value JSONB NOT NULL,
            value_type TEXT,
            updated_by BIGINT,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY(guild_id, scope, key)
        )
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS settings_history (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            old_value JSONB,
            new_value JSONB NOT NULL,
            value_type TEXT,
            changed_by BIGINT,
            changed_at TIMESTAMPTZ DEFAULT NOW(),
            change_type TEXT NOT NULL
        )
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_settings_history_guild_scope_key
        ON settings_history (guild_id, scope, key)
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_settings_history_changed_at
        ON settings_history (changed_at)
    """)
    
    # Reminders table (from cogs/reminders.py)
    op.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            channel_id BIGINT NOT NULL,
            time TIME,
            call_time TIME,
            days TEXT[],
            message TEXT,
            created_by BIGINT,
            origin_channel_id BIGINT,
            origin_message_id BIGINT,
            event_time TIMESTAMPTZ,
            location TEXT,
            last_sent_at TIMESTAMPTZ
        )
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reminders_event_time ON reminders(event_time)")
    
    # Onboarding tables (from cogs/onboarding.py)
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding (
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            responses JSONB,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(guild_id, user_id)
        )
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS guild_onboarding_questions (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            step_order INTEGER NOT NULL,
            question TEXT NOT NULL,
            question_type TEXT NOT NULL DEFAULT 'select',
            options JSONB,
            followup JSONB,
            required BOOLEAN DEFAULT TRUE,
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(guild_id, step_order)
        )
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS guild_rules (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            rule_order INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(guild_id, rule_order)
        )
    """)
    
    # Support tickets table (from cogs/ticketbot.py)
    op.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            username TEXT,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            channel_id BIGINT,
            claimed_by BIGINT,
            claimed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            escalated_to BIGINT
        )
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_user_id ON support_tickets(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_channel_id ON support_tickets(channel_id)")
    
    # FAQ tables (from cogs/faq.py)
    # Note: faq_entries table structure not fully visible in code, adding basic structure
    op.execute("""
        CREATE TABLE IF NOT EXISTS faq_entries (
            id SERIAL PRIMARY KEY,
            title TEXT,
            summary TEXT,
            keywords TEXT[],
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS faq_search_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            query TEXT,
            results_count INTEGER,
            searched_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    # API tables (from api.py)
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            command_name TEXT NOT NULL,
            command_type TEXT NOT NULL,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_guild_created ON audit_logs(guild_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_command ON audit_logs(command_name, created_at)")
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS health_check_history (
            id SERIAL PRIMARY KEY,
            service TEXT NOT NULL,
            version TEXT NOT NULL,
            uptime_seconds INTEGER NOT NULL,
            db_status TEXT NOT NULL,
            guild_count INTEGER,
            active_commands_24h INTEGER,
            gpt_status TEXT,
            database_pool_size INTEGER,
            checked_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_health_check_history_checked_at ON health_check_history(checked_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_health_check_history_service ON health_check_history(service, checked_at DESC)")


def downgrade() -> None:
    # Drop tables in reverse order (respecting dependencies)
    op.execute("DROP TABLE IF EXISTS health_check_history")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS faq_search_logs")
    op.execute("DROP TABLE IF EXISTS faq_entries")
    op.execute("DROP TABLE IF EXISTS support_tickets")
    op.execute("DROP TABLE IF EXISTS guild_rules")
    op.execute("DROP TABLE IF EXISTS guild_onboarding_questions")
    op.execute("DROP TABLE IF EXISTS onboarding")
    op.execute("DROP TABLE IF EXISTS reminders")
    op.execute("DROP TABLE IF EXISTS settings_history")
    op.execute("DROP TABLE IF EXISTS bot_settings")
