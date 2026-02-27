"""Add premium_subs table for Premium tier

Revision ID: 003_premium_subs
Revises: 002_guild_rules_images
Create Date: 2026-02-26

GDPR: No payment or PII in this table; only access control fields
(user_id, guild_id, tier, status, optional stripe_subscription_id, expires_at, created_at).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003_premium_subs"
down_revision: Union[str, None] = "002_guild_rules_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS premium_subs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            tier TEXT NOT NULL,
            status TEXT NOT NULL,
            stripe_subscription_id TEXT,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_premium_subs_user_guild ON premium_subs (user_id, guild_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_premium_subs_guild_status ON premium_subs (guild_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS premium_subs")
