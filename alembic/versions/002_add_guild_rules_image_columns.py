"""Add thumbnail_url and image_url to guild_rules

Revision ID: 002_guild_rules_images
Revises: 001_initial
Create Date: 2026-02-10

Adds optional image columns to guild_rules for onboarding rule embeds
(thumbnail shown right/top, image shown at bottom). Safe to run on existing
databases; columns are nullable.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_guild_rules_images"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE guild_rules ADD COLUMN IF NOT EXISTS thumbnail_url TEXT")
    op.execute("ALTER TABLE guild_rules ADD COLUMN IF NOT EXISTS image_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE guild_rules DROP COLUMN IF EXISTS thumbnail_url")
    op.execute("ALTER TABLE guild_rules DROP COLUMN IF EXISTS image_url")
