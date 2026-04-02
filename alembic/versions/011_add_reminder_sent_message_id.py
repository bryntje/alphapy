"""Add sent_message_id to reminders for T-60 message deletion

Revision ID: 011_add_reminder_sent_message_id
Revises: 010_add_custom_commands
Create Date: 2026-04-02

Tracks the Discord message ID of the T-60 (offset) reminder send.
When the T0 (on-time) reminder fires, the bot uses this ID to delete
the earlier T-60 message so both do not remain visible in the channel.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "011_add_reminder_sent_message_id"
down_revision: Union[str, None] = "010_add_custom_commands"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS sent_message_id BIGINT")


def downgrade() -> None:
    op.execute("ALTER TABLE reminders DROP COLUMN IF EXISTS sent_message_id")
