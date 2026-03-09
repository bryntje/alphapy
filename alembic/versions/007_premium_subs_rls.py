"""Enable Row Level Security on premium_subs (Supabase)

Revision ID: 007_premium_subs_rls
Revises: 006_terms_acceptance_gdpr
Create Date: 2026-03-08

Enables RLS on premium_subs so that in Supabase only the backend role
(table owner / service role / superuser) can access the table. No policies
are added for anon/authenticated, so direct client access sees no rows.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007_premium_subs_rls"
down_revision: Union[str, None] = "006_terms_acceptance_gdpr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE premium_subs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE premium_subs DISABLE ROW LEVEL SECURITY")
