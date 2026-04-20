"""engagement_system: add tables for challenges, weekly awards, streaks, badges and og claims

Revision ID: 020_engagement_system
Revises: 019_growth_checkins
Create Date: 2026-04-20

Adds all tables required by the Engagement module:
  - engagement_badges         — per-user, per-guild badge history
  - engagement_og_claims      — limited reaction-based OG claim tracking per guild
  - engagement_og_setup       — per-guild OG claim message/channel config
  - engagement_challenges     — challenge sessions per guild
  - engagement_participants   — per-challenge participant message counts
  - engagement_weekly_messages — indexed messages used for weekly award computation
  - engagement_weekly_awards  — weekly award period bookkeeping per guild
  - engagement_weekly_results — per-period winner records
  - engagement_streaks        — per-user, per-guild activity streak tracking

All tables are scoped to guild_id for multi-guild support.
"""

from typing import Sequence, Union
from alembic import op

revision: str = "020_engagement_system"
down_revision: Union[str, None] = "019_growth_checkins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Badges ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_badges (
            id          BIGSERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            user_id     BIGINT NOT NULL,
            badge_key   TEXT NOT NULL,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eng_badges_guild_user ON engagement_badges(guild_id, user_id)"
    )

    # --- OG claims ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_og_claims (
            guild_id    BIGINT NOT NULL,
            user_id     BIGINT NOT NULL,
            claimed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eng_og_claims_guild ON engagement_og_claims(guild_id)"
    )

    # --- OG setup (one row per guild) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_og_setup (
            guild_id    BIGINT PRIMARY KEY,
            message_id  BIGINT,
            channel_id  BIGINT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # --- Challenges ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_challenges (
            id          BIGSERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            channel_id  BIGINT,
            mode        TEXT NOT NULL DEFAULT 'leaderboard',
            title       TEXT,
            active      BOOLEAN NOT NULL DEFAULT TRUE,
            started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at     TIMESTAMPTZ,
            ended_at    TIMESTAMPTZ,
            winner_id   BIGINT,
            messages_count INT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eng_challenges_guild_active ON engagement_challenges(guild_id, active)"
    )

    # --- Challenge participants ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_participants (
            id              BIGSERIAL PRIMARY KEY,
            challenge_id    BIGINT NOT NULL REFERENCES engagement_challenges(id) ON DELETE CASCADE,
            user_id         BIGINT NOT NULL,
            message_count   INT NOT NULL DEFAULT 0,
            UNIQUE (challenge_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eng_participants_challenge ON engagement_participants(challenge_id)"
    )

    # --- Weekly messages index ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_weekly_messages (
            id              BIGSERIAL PRIMARY KEY,
            guild_id        BIGINT NOT NULL,
            message_id      BIGINT NOT NULL,
            channel_id      BIGINT NOT NULL,
            user_id         BIGINT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL,
            has_image       BOOLEAN NOT NULL DEFAULT FALSE,
            is_food         BOOLEAN NOT NULL DEFAULT FALSE,
            reactions_count INT NOT NULL DEFAULT 0,
            UNIQUE (guild_id, message_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eng_weekly_msgs_guild_created ON engagement_weekly_messages(guild_id, created_at)"
    )

    # --- Weekly award periods ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_weekly_awards (
            id          BIGSERIAL PRIMARY KEY,
            guild_id    BIGINT NOT NULL,
            week_start  DATE NOT NULL,
            week_end    DATE NOT NULL,
            UNIQUE (guild_id, week_start, week_end)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eng_weekly_awards_guild ON engagement_weekly_awards(guild_id)"
    )

    # --- Weekly award results ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_weekly_results (
            id          BIGSERIAL PRIMARY KEY,
            week_id     BIGINT NOT NULL REFERENCES engagement_weekly_awards(id) ON DELETE CASCADE,
            award_key   TEXT NOT NULL,
            user_id     BIGINT NOT NULL,
            metric      INT,
            message_id  BIGINT,
            UNIQUE (week_id, award_key)
        )
        """
    )

    # --- Streaks ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engagement_streaks (
            guild_id        BIGINT NOT NULL,
            user_id         BIGINT NOT NULL,
            last_day        DATE,
            current_days    INT NOT NULL DEFAULT 0,
            base_nickname   TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eng_streaks_guild ON engagement_streaks(guild_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_eng_streaks_guild")
    op.execute("DROP TABLE IF EXISTS engagement_streaks")
    op.execute("DROP TABLE IF EXISTS engagement_weekly_results")
    op.execute("DROP INDEX IF EXISTS idx_eng_weekly_awards_guild")
    op.execute("DROP TABLE IF EXISTS engagement_weekly_awards")
    op.execute("DROP INDEX IF EXISTS idx_eng_weekly_msgs_guild_created")
    op.execute("DROP TABLE IF EXISTS engagement_weekly_messages")
    op.execute("DROP INDEX IF EXISTS idx_eng_participants_challenge")
    op.execute("DROP TABLE IF EXISTS engagement_participants")
    op.execute("DROP INDEX IF EXISTS idx_eng_challenges_guild_active")
    op.execute("DROP TABLE IF EXISTS engagement_challenges")
    op.execute("DROP TABLE IF EXISTS engagement_og_setup")
    op.execute("DROP INDEX IF EXISTS idx_eng_og_claims_guild")
    op.execute("DROP TABLE IF EXISTS engagement_og_claims")
    op.execute("DROP INDEX IF EXISTS idx_eng_badges_guild_user")
    op.execute("DROP TABLE IF EXISTS engagement_badges")
