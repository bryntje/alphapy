"""Add terms_acceptance table for GDPR compliance

Revision ID: 006_terms_acceptance_gdpr
Revises: 005_premium_one_active_per_user
Create Date: 2026-02-27

Adds terms_acceptance table to track user consent for GDPR compliance.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006_terms_acceptance_gdpr"
down_revision: Union[str, None] = "005_premium_one_active_per_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS terms_acceptance (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE,
            accepted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            version TEXT NOT NULL DEFAULT '2025-02-27',
            ip_address INET
        )
    """)

    # Add indexes for efficient queries
    op.execute("CREATE INDEX IF NOT EXISTS idx_terms_acceptance_user ON terms_acceptance (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_terms_acceptance_accepted_at ON terms_acceptance (accepted_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS terms_acceptance")