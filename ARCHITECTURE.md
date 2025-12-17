# 🧬 Innersync • Alphapy Architecture

## High-level overview
- Discord bot (discord.py) with modular cogs under `cogs/`
- FastAPI app (`api.py`) for HTTP access to reminders and dashboard telemetry
- PostgreSQL for persistent storage (onboarding, reminders, GDPR, etc.)
- GPT helpers under `gpt/` and utilities in `utils/`
- Configuration via environment variables in `config.py`
- Authentication via Supabase Auth (Google/GitHub/Discord OAuth, JWT validated in `utils/supabase_auth.py`)

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
- `cogs/ticketbot.py`
  - Slash commands: `/ticket`, `/ticket_list`, `/ticket_claim`, `/ticket_close`, `/ticket_panel_post`
  - Channel UX: per-ticket private channel under `TICKET_CATEGORY_ID`
  - Interactive UI in channel: buttons to Claim/Close/Delete (staff only)
  - Summary: GPT summary posted on Close; persisted for clustering
  - FAQ: repeated-topic detection; proposal embed with “Add to FAQ” button (admin)
  - Extra status workflows (Phase 2): Wait for user, Escalate, `/ticket_status`
  - Ticket stats: `/ticket_stats` with interactive scope buttons (7d/30d/all)
  - Logging: create/claim/close/delete to `WATCHER_LOG_CHANNEL`

  - Listens in announcements channel and auto-creates reminders from embeds
  - Robust datetime parsing with Brussels timezone
  - Persists via `reminders` table, logs to `WATCHER_LOG_CHANNEL`

- `cogs/gdpr.py` and companions
  - GDPR accept/export flows

- `api.py`
  - FastAPI entrypoint, exposes read endpoints for dashboards/tools
  - `/api/dashboard/metrics` aggregates live bot telemetry (uptime, latency, guilds, command count) via `utils/runtime_metrics.get_bot_snapshot`
  - `/health` returns service metadata (name, version, uptime, timestamp) and performs a lightweight DB ping for readiness probes
  - Reminder CRUD endpoints secured with API key + `X-User-Id`
  - **Telemetry Ingest Background Job**: `_telemetry_ingest_loop()` runs continuously, collecting metrics and writing to `telemetry.subsystem_snapshots` in Supabase every 30-60 seconds (configurable). Ensures Mind dashboard always has fresh data without requiring endpoint calls.

## Data model (simplified)
- `onboarding`
  - `user_id BIGINT PRIMARY KEY`
  - `responses JSONB` (answers by index; values may be string | list[str] | {choice, followup, followup_label})
  - `timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

- `reminders`
- `support_tickets`
  - `id SERIAL PRIMARY KEY`
  - `user_id BIGINT`, `username TEXT`, `description TEXT`, `status TEXT DEFAULT 'open'`
  - `channel_id BIGINT`, `claimed_by BIGINT`, `claimed_at TIMESTAMPTZ`
  - `updated_at TIMESTAMPTZ`, `escalated_to BIGINT`
  - `created_at TIMESTAMPTZ DEFAULT NOW()`

- `ticket_summaries`
- `ticket_metrics`
  - `id BIGSERIAL PRIMARY KEY`
  - `snapshot JSONB`
  - `scope TEXT` (7d/30d/all)
  - `counts JSONB` (status → count)
  - `average_cycle_time BIGINT` (seconds)
  - `triggered_by BIGINT`
  - `created_at TIMESTAMPTZ DEFAULT NOW()`
  - `id SERIAL PRIMARY KEY`
  - `ticket_id INT NOT NULL`
  - `summary TEXT NOT NULL`
  - `similarity_key TEXT`
  - `created_at TIMESTAMPTZ DEFAULT NOW()`

- `faq_entries`
  - `id SERIAL PRIMARY KEY`
  - `similarity_key TEXT`
  - `summary TEXT NOT NULL`
  - `created_by BIGINT`
  - `created_at TIMESTAMPTZ DEFAULT NOW()`
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

## Configuration System

### Environment Variables (`config.py`)
- **Required:** `DATABASE_URL`, `BOT_TOKEN`, `OPENAI_API_KEY`
- **Optional:** `API_KEY`, `SUPABASE_*` vars for web integration
- **Legacy:** Most channel/role IDs are now **deprecated** - use `/config` commands instead

### Guild-Specific Settings (Database-Driven)
Each Discord server configures its own settings via `/config` commands:

**System Settings:**
- `system.log_channel_id` - Bot logging and error messages
- `system.rules_channel_id` - Rules channel for onboarding
- `system.onboarding_channel_id` - Welcome/onboarding channel

**Feature Settings:**
- `embedwatcher.announcements_channel_id` - Auto-reminder detection
- `invites.announcement_channel_id` - Invite tracking messages
- `gdpr.channel_id` - GDPR compliance documents
- `ticketbot.category_id` - Ticket channel category
- `ticketbot.staff_role_id` - Staff role for tickets
- `ticketbot.escalation_role_id` - Escalation role

**Behavior Settings:**
- `reminders.allow_everyone_mentions` - @everyone permissions
- `reminders.default_channel_id` - Default reminder channel
- `gpt.model` - AI model selection
- `gpt.temperature` - AI creativity level

### Multi-Guild Architecture
- ✅ **Complete isolation:** Each guild's data/settings are separate
- ✅ **Dynamic detection:** Bot automatically detects all joined servers
- ✅ **Per-guild configuration:** No hardcoded server-specific values
- ✅ **Admin control:** Server admins configure via Discord commands
- ✅ **Zero defaults:** All channels/roles must be explicitly configured

## Control flow
1. User presses Start Onboarding → `ReactionRole` shows rules → starts `Onboarding`.
2. `Onboarding` prompts 4 questions; multi-select advances automatically; follow-ups via modal.
3. On completion: summary embed (ephemeral), log embed (log channel), role assignment, DB persist.
4. Reminders: via slash commands or auto from `EmbedReminderWatcher`.
5. `tasks.loop` in `reminders` dispatches messages at scheduled times:
6. Tickets:
   - User runs `/ticket` or clicks panel button → per-ticket channel created with restricted access
   - Staff can Claim, Close; on Close: channel locks/renames and GPT summary posts
   - Summary stored; repeated topics trigger FAQ proposal; staff may add to FAQ
   - One-off (T−60): `time == now` and `(event_time - 60m).date == today`
   - One-off (T0): `event_time::time == now`
   - Recurring: `time == now` and `weekday(now) ∈ days`
   - Skip if `date_trunc('minute', last_sent_at) == date_trunc('minute', now)`
   - After send: update `last_sent_at`; delete one-offs after T0

## Observability
- Centralized logging via `utils/logger.py`
- Discord log embeds to `WATCHER_LOG_CHANNEL` for created/sent/deleted/errors
- `/health` endpoint available for external uptime monitoring and DB sanity checks
- `utils/runtime_metrics.py` snapshots Discord bot state for the dashboard API without blocking the event loop
- **Telemetry Ingest**: Background job continuously writes subsystem snapshots to Supabase `telemetry.subsystem_snapshots` table, ensuring Mind dashboard always has fresh data (runs every 30-60 seconds, configurable via `TELEMETRY_INGEST_INTERVAL`)

## Security
- Tokens and DB credentials via env only (no hardcoded secrets)
- Optional controlled `@everyone` mentions via `ENABLE_EVERYONE_MENTIONS`

## Future improvements
- Migrations with Alembic for schema evolution
- Unit tests for parsing helpers and onboarding formatters
- Health endpoints and structured logging for the API
