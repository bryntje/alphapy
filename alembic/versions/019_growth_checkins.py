"""growth_checkins: add table for per-guild growth check-in activity log

Revision ID: 019_growth_checkins
Revises: 018_gdpr_acceptance_add_guild_id
Create Date: 2026-04-15

Adds a lightweight growth_checkins table that logs each /growthcheckin interaction
per guild. Reflection content is NOT stored here (stays in Supabase for privacy).
This table is used by the dashboard to show guild-level growth activity stats.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "019_growth_checkins"
down_revision: Union[str, None] = "018_gdpr_acceptance_add_guild_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS growth_checkins (
            id          BIGSERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            user_id     BIGINT NOT NULL,
            shared      BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_growth_checkins_guild_id ON growth_checkins(guild_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_growth_checkins_created_at ON growth_checkins(created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_growth_checkins_created_at")
    op.execute("DROP INDEX IF EXISTS idx_growth_checkins_guild_id")
    op.execute("DROP TABLE IF EXISTS growth_checkins")
