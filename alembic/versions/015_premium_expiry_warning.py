"""Add expiry_warning_sent_at column to premium_subs

Revision ID: 015_premium_expiry_warning
Revises: 014_gpt_usage_tracking
Create Date: 2026-04-08

Tracks when a 7-day expiry warning DM was last sent to the user.
NULL means no warning has been sent yet. The daily background task in
cogs/premium.py uses this to avoid sending duplicate warnings.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "015_premium_expiry_warning"
down_revision: Union[str, None] = "014_gpt_usage_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE premium_subs
        ADD COLUMN IF NOT EXISTS expiry_warning_sent_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE premium_subs
        DROP COLUMN IF EXISTS expiry_warning_sent_at
    """)
