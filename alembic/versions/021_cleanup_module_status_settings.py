"""cleanup_module_status_settings: remove all remaining module_status.* rows from bot_settings

Revision ID: 021_cleanup_module_status
Revises: 020_engagement_system
Create Date: 2026-04-20

Migration 013 only removed module_status.gdpr, but several other module_status.*
rows were never cleaned up and cause UNKNOWN_SETTING log noise on every startup:

  module_status.rules
  module_status.embedwatcher
  module_status.onboarding
  module_status.verification
  module_status.custom_commands
  module_status.faq
  module_status.invites
  module_status.reminders
  module_status.gpt
  (and any other module_status.* that may exist)

All module_status.* settings have been superseded by dedicated per-scope enabled
flags (e.g. gdpr.enabled, automod.enabled) registered in bot.py. The module_status
scope is no longer used anywhere in the codebase.

This migration deletes the entire module_status scope in one shot rather than
enumerating individual keys, so any future stragglers are also covered.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_cleanup_module_status"
down_revision: Union[str, None] = "020_engagement_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wipe the entire module_status scope — it is no longer registered in bot.py
    op.execute(
        sa.text("DELETE FROM bot_settings WHERE scope = 'module_status'")
    )


def downgrade() -> None:
    # These rows are stale and not worth restoring.
    pass
