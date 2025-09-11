# Alphapy Architecture

## High-level overview
- Discord bot (discord.py) with modular cogs under `cogs/`
- FastAPI app (`api.py`) for HTTP access to selected data (reminders)
- PostgreSQL for persistent storage (onboarding, reminders, GDPR, etc.)
- GPT helpers under `gpt/` and utilities in `utils/`
- Configuration via environment variables in `config.py`

## Key modules
- `cogs/onboarding.py`
  - Drives the user onboarding flow
  - Questions: 4-step flow with follow-ups and email validation
  - UI: `OnboardingView`, `OnboardingButton`, `OnboardingSelect`, `ConfirmButton`, `TextInputModal`, `FollowupModal`
  - Storage: `onboarding` table (JSONB responses per user)
  - Embeds: summary to user, log to `LOG_CHANNEL_ID`

- `cogs/reaction_roles.py`
  - Places persistent message in `RULES_CHANNEL_ID`
  - Starts onboarding after rules acceptance
  - Detects existing onboarding message via button `custom_id="start_onboarding"`

- `cogs/reminders.py`
  - Slash commands: `/add_reminder`, `/reminder_list`, `/reminder_delete`
  - Accepts optional embed link and parses details (title, time, days, location)
  - Stores reminders (recurring or one-off) with `call_time` support
  - Periodic job (`tasks.loop`) dispatches reminders
  - Idempotency: `last_sent_at` prevents duplicate sends in the same minute
  - T0 support: One-off reminders send at T−60 and at `event_time` (T0)

- `cogs/embed_watcher.py`
  - Listens in announcements channel and auto-creates reminders from embeds
  - Robust datetime parsing with Brussels timezone
  - Persists via `reminders` table, logs to `WATCHER_LOG_CHANNEL`

- `cogs/gdpr.py` and companions
  - GDPR accept/export flows

- `api.py`
  - FastAPI entrypoint, exposes read endpoints for dashboards/tools

## Data model (simplified)
- `onboarding`
  - `user_id BIGINT PRIMARY KEY`
  - `responses JSONB` (answers by index; values may be string | list[str] | {choice, followup, followup_label})
  - `timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

- `reminders`
  - `id SERIAL PRIMARY KEY`
  - `name TEXT`
  - `channel_id BIGINT`
  - `time TIME` (trigger time; T−60)
  - `call_time TIME` (display time; event clock)
  - `days TEXT[]` (0=Mon..6=Sun); empty with one-off `event_time`
  - `message TEXT`
  - `created_by BIGINT`
  - `origin_channel_id BIGINT` / `origin_message_id BIGINT`
  - `event_time TIMESTAMPTZ` (one-off event)
  - `location TEXT`
  - `last_sent_at TIMESTAMPTZ` (idempotency per minute)

## Configuration (`config.py`)
- Driven by env vars: `GUILD_ID`, `ROLE_ID`, `LOG_CHANNEL_ID`, `RULES_CHANNEL_ID`, `WATCHER_LOG_CHANNEL`, `ANNOUNCEMENTS_CHANNEL_ID`, `DATABASE_URL`, `ENABLE_EVERYONE_MENTIONS`, etc.
- Local overrides via optional `config_local.py`

## Control flow
1. User presses Start Onboarding → `ReactionRole` shows rules → starts `Onboarding`.
2. `Onboarding` prompts 4 questions; multi-select advances automatically; follow-ups via modal.
3. On completion: summary embed (ephemeral), log embed (log channel), role assignment, DB persist.
4. Reminders: via slash commands or auto from `EmbedReminderWatcher`.
5. `tasks.loop` in `reminders` dispatches messages at scheduled times:
   - One-off (T−60): `time == now` and `(event_time - 60m).date == today`
   - One-off (T0): `event_time::time == now`
   - Recurring: `time == now` and `weekday(now) ∈ days`
   - Skip if `date_trunc('minute', last_sent_at) == date_trunc('minute', now)`
   - After send: update `last_sent_at`; delete one-offs after T0

## Observability
- Centralized logging via `utils/logger.py`
- Discord log embeds to `WATCHER_LOG_CHANNEL` for created/sent/deleted/errors

## Security
- Tokens and DB credentials via env only (no hardcoded secrets)
- Optional controlled `@everyone` mentions via `ENABLE_EVERYONE_MENTIONS`

## Future improvements
- Migrations with Alembic for schema evolution
- Unit tests for parsing helpers and onboarding formatters
- Health endpoints and structured logging for the API
