"""verification: add payment_date column for recency tracking

Revision ID: 017_verification_payment_date
Revises: 016_gdpr_compliance
Create Date: 2026-04-13

Adds a payment_date (DATE) column to verification_tickets so the date extracted
from the submitted screenshot is persisted for audit and debugging purposes.

This column is populated by the verification cog when the AI successfully reads
a payment date from the screenshot. It is nullable: older tickets and cases where
the date could not be read will remain NULL.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "017_verification_payment_date"
down_revision: Union[str, None] = "016_gdpr_compliance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.verification_tickets') IS NOT NULL THEN
                ALTER TABLE verification_tickets
                ADD COLUMN IF NOT EXISTS payment_date DATE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.verification_tickets') IS NOT NULL THEN
                ALTER TABLE verification_tickets
                DROP COLUMN IF EXISTS payment_date;
            END IF;
        END $$;
    """)
