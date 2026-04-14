"""gdpr_acceptance: add guild_id column for per-guild scoping

Revision ID: 018_gdpr_acceptance_add_guild_id
Revises: 017_verification_payment_date
Create Date: 2026-04-14

Adds a guild_id BIGINT column to gdpr_acceptance so acceptances can be
scoped per guild. Nullable to remain backward compatible with existing rows
that were recorded before this column existed.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "018_gdpr_acceptance_add_guild_id"
down_revision: Union[str, None] = "017_verification_payment_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE gdpr_acceptance ADD COLUMN IF NOT EXISTS guild_id BIGINT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE gdpr_acceptance DROP COLUMN IF EXISTS guild_id"
    )
