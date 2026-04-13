"""GDPR compliance: register gdpr_acceptance table and drop unused ip_address column

Revision ID: 016_gdpr_compliance
Revises: 015_premium_expiry_warning
Create Date: 2026-04-13

Two administrative cleanups in one revision:

1. Formally register gdpr_acceptance in the Alembic migration chain.
   The table was created ad-hoc by cogs/migrate_gdpr.py (one-time SQLite → PG
   migration utility) and never tracked by Alembic. Without this migration,
   fresh deployments have no gdpr_acceptance table, causing store_gdpr_acceptance()
   in cogs/gdpr.py to fail at runtime.

2. Drop the ip_address column from terms_acceptance.
   The column was added in migration 006 for a planned web-based consent flow
   that was never implemented. Discord gateway interactions have no client IP,
   so the column is always NULL. Retaining it misleads auditors into thinking
   IP addresses are collected. If a web consent flow is added later, a new
   migration should re-introduce it with proper documentation.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "016_gdpr_compliance"
down_revision: Union[str, None] = "015_premium_expiry_warning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Register gdpr_acceptance table (CREATE IF NOT EXISTS is safe on existing DBs)
    op.execute("""
        CREATE TABLE IF NOT EXISTS gdpr_acceptance (
            user_id   BIGINT PRIMARY KEY,
            accepted  INTEGER NOT NULL DEFAULT 0,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Drop the never-populated ip_address column from terms_acceptance.
    #    Discord gateway interactions have no client IP — column is always NULL.
    op.execute("""
        ALTER TABLE terms_acceptance DROP COLUMN IF EXISTS ip_address
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gdpr_acceptance")
    op.execute("""
        ALTER TABLE terms_acceptance ADD COLUMN IF NOT EXISTS ip_address INET
    """)
