"""Add app_reflections table for plaintext reflections from App via Core webhook

Revision ID: 008_app_reflections
Revises: 007_premium_subs_rls
Create Date: 2026-02-28

Stores plaintext reflection content received from Core-API webhook for use in
user-self flows (e.g. growthcheckin only; not ticket suggestions). Consent validated by Core before webhook.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008_app_reflections"
down_revision: Union[str, None] = "007_premium_subs_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS app_reflections (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            reflection_id TEXT NOT NULL,
            plaintext_content JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, reflection_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_app_reflections_user_created "
        "ON app_reflections (user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_app_reflections_user_created")
    op.execute("DROP TABLE IF EXISTS app_reflections")
