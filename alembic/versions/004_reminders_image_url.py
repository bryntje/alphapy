"""Add image_url to reminders for Premium image/banner support

Revision ID: 004_reminders_image_url
Revises: 003_premium_subs
Create Date: 2026-02-26

Adds optional image_url column to reminders table.
Premium users can attach images/banners to reminders.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004_reminders_image_url"
down_revision: Union[str, None] = "003_premium_subs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS image_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE reminders DROP COLUMN IF EXISTS image_url")
