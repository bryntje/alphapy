"""Add custom commands table

Revision ID: 010_add_custom_commands
Revises: 009_add_automod_tables
Create Date: 2026-03-26 10:00:00.000000

Adds the custom_commands table for guild-scoped automated message responses.
Supports exact, starts_with, contains, and regex trigger types with dynamic
variable substitution in responses.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010_add_custom_commands'
down_revision: Union[str, None] = '009_add_automod_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_commands (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            trigger_value TEXT NOT NULL,
            response TEXT NOT NULL,
            enabled BOOLEAN DEFAULT true,
            case_sensitive BOOLEAN DEFAULT false,
            delete_trigger BOOLEAN DEFAULT false,
            reply_to_user BOOLEAN DEFAULT true,
            uses INTEGER DEFAULT 0,
            created_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(guild_id, name)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_custom_commands_guild_enabled
            ON custom_commands(guild_id, enabled)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_custom_commands_guild_enabled")
    op.execute("DROP TABLE IF EXISTS custom_commands")
