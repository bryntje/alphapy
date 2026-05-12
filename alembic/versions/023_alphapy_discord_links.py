"""alphapy_discord_links — Innersync user UUID to Discord snowflake mapping.

Revision ID: 023_alphapy_discord_links
Revises: 022_api_observability_tables
Create Date: 2026-05-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "023_alphapy_discord_links"
down_revision: Union[str, None] = "022_api_observability_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alphapy_discord_links (
            innersync_user_id UUID NOT NULL,
            discord_user_id BIGINT NOT NULL,
            linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            link_source TEXT,
            CONSTRAINT alphapy_discord_links_pkey PRIMARY KEY (innersync_user_id),
            CONSTRAINT alphapy_discord_links_discord_user_id_key UNIQUE (discord_user_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_alphapy_discord_links_discord "
        "ON alphapy_discord_links(discord_user_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alphapy_discord_links_discord;")
    op.execute("DROP TABLE IF EXISTS alphapy_discord_links;")
