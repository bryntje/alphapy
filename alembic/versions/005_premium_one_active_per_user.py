"""Enforce at most one active premium subscription per user

Revision ID: 005_premium_one_active_per_user
Revises: 004_reminders_image_url
Create Date: 2026-02-26

Adds partial unique index on premium_subs so (user_id) is unique
where status = 'active'. Enables transfer by updating guild_id on
the single active row.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005_premium_one_active_per_user"
down_revision: Union[str, None] = "004_reminders_image_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep only the most recent active row per user; mark older duplicates as cancelled
    op.execute("""
        UPDATE premium_subs a
        SET status = 'cancelled'
        FROM (
            SELECT id, user_id,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) AS rn
            FROM premium_subs
            WHERE status = 'active'
        ) b
        WHERE a.id = b.id AND b.rn > 1
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_premium_subs_one_active_per_user "
        "ON premium_subs (user_id) WHERE status = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_premium_subs_one_active_per_user")
