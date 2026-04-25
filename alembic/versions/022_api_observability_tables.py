"""create_api_observability_tables

Revision ID: 022_api_observability_tables
Revises: 021_cleanup_module_status
Create Date: 2026-04-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "022_api_observability_tables"
down_revision: Union[str, None] = "021_cleanup_module_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            command_name TEXT NOT NULL,
            command_type TEXT NOT NULL,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_guild_created ON audit_logs(guild_id, created_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_command ON audit_logs(command_name, created_at);"
    )

    op.execute(
        """
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
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_health_check_history_checked_at ON health_check_history(checked_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_health_check_history_service ON health_check_history(service, checked_at DESC);"
    )

    # Reminder scheduler support index for date-based filtering.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_event_time ON reminders(event_time);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_reminders_event_time;")
    op.execute("DROP INDEX IF EXISTS idx_health_check_history_service;")
    op.execute("DROP INDEX IF EXISTS idx_health_check_history_checked_at;")
    op.execute("DROP TABLE IF EXISTS health_check_history;")
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_command;")
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_guild_created;")
    op.execute("DROP TABLE IF EXISTS audit_logs;")
