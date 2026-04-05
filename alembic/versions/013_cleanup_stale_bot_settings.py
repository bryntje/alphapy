"""Remove stale bot_settings rows for renamed or dropped setting keys

Revision ID: 013_cleanup_stale_bot_settings
Revises: 012_add_guild_id_indexes
Create Date: 2026-04-05

The following rows exist in bot_settings but no longer have a matching
SettingDefinition registered in bot.py:

  embedwatcher.embed_watcher_offset_hours  -> renamed to embedwatcher.reminder_offset_minutes
  guild.module_status                      -> scope removed
  module_status.gdpr                       -> scope removed (replaced by gdpr.enabled)
  system.onboarding_channel_id             -> key removed

These rows were silently ignored on every startup and logged as UNKNOWN_SETTING.
This migration removes them so the log stays clean.

The fyi.* rows (first_guild_join, _last_sent_at, etc.) are intentionally
unregistered (stored via set_raw) and are NOT touched here.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "013_cleanup_stale_bot_settings"
down_revision: Union[str, None] = "012_add_guild_id_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Stale (scope, key) pairs to remove.
_STALE_KEYS = [
    ("embedwatcher", "embed_watcher_offset_hours"),
    ("guild", "module_status"),
    ("module_status", "gdpr"),
    ("system", "onboarding_channel_id"),
]


def upgrade() -> None:
    for scope, key in _STALE_KEYS:
        op.execute(
            f"DELETE FROM bot_settings WHERE scope = '{scope}' AND key = '{key}'"
        )


def downgrade() -> None:
    # Stale rows are not worth restoring — downgrade is a no-op.
    pass
