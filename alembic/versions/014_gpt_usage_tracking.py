"""Add gpt_usage table for per-user daily GPT call quota tracking

Revision ID: 014_gpt_usage_tracking
Revises: 013_cleanup_stale_bot_settings
Create Date: 2026-04-08

Tracks how many GPT calls each (user, guild) pair makes per day.
Used by check_and_increment_gpt_quota() in utils/premium_guard.py to enforce
tier-based daily limits (free: 5, monthly: 25, yearly/lifetime: unlimited).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_gpt_usage_tracking"
down_revision: Union[str, None] = "013_cleanup_stale_bot_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS gpt_usage (
            user_id    BIGINT  NOT NULL,
            guild_id   BIGINT  NOT NULL,
            usage_date DATE    NOT NULL DEFAULT CURRENT_DATE,
            call_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, guild_id, usage_date)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gpt_usage_date ON gpt_usage (usage_date)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_gpt_usage_date")
    op.execute("DROP TABLE IF EXISTS gpt_usage")
