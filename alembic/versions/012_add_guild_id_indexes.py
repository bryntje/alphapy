"""Add guild_id indexes to high-traffic tables

Revision ID: 012_add_guild_id_indexes
Revises: 011_add_reminder_sent_message_id
Create Date: 2026-04-02

All guild-scoped queries filter by guild_id (BIGINT). Without an index,
every lookup requires a sequential scan of the full table. These indexes
cover the most frequently queried tables that were missing this index.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "012_add_guild_id_indexes"
down_revision: Union[str, None] = "011_add_reminder_sent_message_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminders_guild_id "
        "ON reminders(guild_id)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_tickets_guild_id "
        "ON support_tickets(guild_id)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_automod_logs_guild_id "
        "ON automod_logs(guild_id)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_automod_user_history_guild_id "
        "ON automod_user_history(guild_id)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_app_reflections_user_id "
        "ON app_reflections(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_reminders_guild_id")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_support_tickets_guild_id")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_automod_logs_guild_id")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_automod_user_history_guild_id")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_app_reflections_user_id")
