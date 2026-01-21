# 🧬 Innersync • Alphapy Architecture

## High-level overview
- Discord bot (discord.py) with modular cogs under `cogs/`
- FastAPI app (`api.py`) for HTTP access to reminders, dashboard telemetry, and analytics
- PostgreSQL for persistent storage (onboarding, reminders, GDPR, tickets, analytics, etc.)
- Alembic for database schema migrations (`alembic/` directory)
- Pytest test suite (`tests/` directory) with 53+ tests
- GPT helpers under `gpt/` with retry queue and fallback handling
- Utilities in `utils/` including command tracking and runtime metrics
- Configuration via environment variables in `config.py` and database-driven guild settings
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
  - Slash commands: `/add_reminder`, `/reminder_list`, `/reminder_delete`, `/reminder_edit`
  - Accepts optional embed link and parses details (title, time, days, location)
  - Stores reminders (recurring or one-off) with `call_time` support
  - Rate limiting: `/add_reminder` has cooldown of 5 per minute per guild+user (prevents spam)
  - Periodic job (`tasks.loop`) dispatches reminders
  - Idempotency: `last_sent_at` prevents duplicate sends in the same minute
  - T0 support: One-off reminders send at T−60 and at `event_time` (T0)
  - Edit modal: `/reminder_edit` allows editing name, time, days, message, and channel

- `cogs/embed_watcher.py`
  - Listens in announcements channel and auto-creates reminders from embeds
  - Robust datetime parsing with Brussels timezone
  - Supports relative dates ("This Wednesday", "Next Friday", "Tomorrow")
  - Parses non-embed messages (configurable via settings)
  - Rich embed logging for parsing success/failure
  - Persists via `reminders` table, logs to log channel
  - Uses centralized utilities: `acquire_safe()` for database connections, `EmbedBuilder` for consistent embed formatting, `is_pool_healthy()` for connection checks

- `cogs/migrations.py`
  - Database migration management via Alembic
  - `/migrate` command: status, upgrade, downgrade, history
  - Admin-only access for safety

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
  - Uses `asyncpg` connection pool for database access (shared with bot)
  - `/api/dashboard/metrics` aggregates live bot telemetry (uptime, latency, guilds, command count, command usage stats) via `utils/runtime_metrics.get_bot_snapshot`
  - `/api/health` enhanced health probe with guild count, command usage, GPT status, database pool size
  - `/api/health/history` historical health check data for trend analysis
  - `/top-commands` command usage analytics endpoint (filterable by guild and time period)
  - Reminder CRUD endpoints secured with API key + `X-User-Id`
  - **IP-based Rate Limiting Middleware**: `RateLimitMiddleware` protects all API endpoints from abuse
    - 30 read requests per minute per IP
    - 10 write requests per minute per IP
    - Health/metrics endpoints excluded from rate limiting
    - Automatic cleanup of old rate limit entries (>1 minute)
    - Periodic cleanup task (every 10+ minutes) removes empty entries and enforces max 1000 IP entries
  - **Command Stats Caching**: TTL cache (30 seconds) with max 50 entries to reduce database queries
  - **Cache Metrics**: `CacheMetrics` model exposes all cache sizes in dashboard metrics endpoint
  - **Telemetry Ingest Background Job**: `_telemetry_ingest_loop()` runs continuously, collecting metrics and writing to `telemetry.subsystem_snapshots` in Supabase every 30-60 seconds (configurable). Ensures Mind dashboard always has fresh data without requiring endpoint calls. Gracefully handles connection errors and pool shutdown.
  - **Health Check History**: Automatic logging of health checks to `health_check_history` table

- `utils/command_tracker.py`
  - Automatic tracking of all command executions via event handlers in `bot.py`
  - Uses dedicated database connection pool created in bot's event loop (not FastAPI's loop) to avoid event loop conflicts
  - Initialized in `on_ready()` event handler, persists across bot restarts
  - Tracks both slash commands and text commands with success/failure status
  - Stores data in `audit_logs` table for analytics and `/command_stats` command
  - **Batching Queue**: In-memory queue (max 10k entries) with batch flush every 30s or at 1k entries threshold
  - Periodic flush task runs in background to write batches to database efficiently

- `utils/db_helpers.py`
  - Centralized database connection management utilities
  - `acquire_safe(pool)`: Async context manager for safe connection acquisition with comprehensive error handling
  - `is_pool_healthy(pool)`: Checks connection pool status before operations
  - Used across all cogs to eliminate duplicate try/except blocks

- `utils/validators.py`
  - Centralized permission and ownership validation
  - `validate_admin(interaction)`: Unified admin/owner check replacing duplicate logic across cogs
  - Type-safe validation functions for consistent permission checks

- `utils/embed_builder.py`
  - Consistent Discord embed creation with uniform styling
  - `EmbedBuilder` class with static methods: `info()`, `log()`, `warning()`, `success()`, `error()`, `status()`
  - Automatic timestamps and color coding based on embed type
  - Reduces boilerplate embed creation code across all cogs

- `utils/settings_helpers.py`
  - Cached settings wrapper for improved performance
  - `CachedSettingsHelper`: Type-safe getters (`get_int()`, `get_bool()`, `get_str()`) with caching
  - **LRU Cache**: Uses `OrderedDict` for LRU eviction with max 500 entries
  - Automatic eviction of oldest entries when cache exceeds max size
  - Eviction logging for monitoring cache behavior
  - `set_bulk()`: Batch settings updates for efficiency
  - Reduces repeated `SettingsService.get/put` calls with error handling

- `utils/parsers.py`
  - Centralized string parsing utilities
  - `parse_days_string()`: Parse day strings (e.g., "ma,wo,vr") to day arrays
  - `parse_time_string()`: Parse time strings with timezone support
  - `format_days_for_display()`: Format day arrays for user-friendly display
  - Shared regex patterns and date functions used by embed watcher and reminders
  - Includes unit tests in `tests/test_parsers.py`

- `utils/sanitizer.py`
  - Centralized input sanitization utilities for security
  - `escape_markdown()`: Escapes Discord markdown characters (*, _, `, [, ], >, |, ~) to prevent injection
  - `strip_mentions()`: Removes user mentions (`<@123456>`), role mentions (`<@&123456>`), channel mentions (`<#123456>`), and `@everyone`/`@here` to prevent spam
  - `url_filter()`: Filters or sanitizes URLs (can allow http/https or remove all URLs)
  - `safe_embed_text()`: Combines markdown escaping + mention removal + length truncation for embed-safe text
  - `safe_prompt()`: Blocks prompt injection/jailbreak attempts in GPT prompts by detecting patterns like "ignore previous", "act as", "system:", etc.
  - `safe_log_message()`: Sanitizes text for logging with control character removal and length limits (default 200 chars) to prevent log spam
  - Used across all cogs to sanitize user input before it reaches embeds, GPT prompts, or logs
  - Comprehensive test suite in `tests/test_sanitizer.py` with parametrized tests for attack vectors

- `utils/background_tasks.py`
  - Robust background task management
  - `BackgroundTask` class: Manages asynchronous loops with graceful shutdown
  - Specific error handling for connection errors, pool shutdown, and Supabase edge cases
  - Replaces duplicate task loop setup code across cogs

- `utils/command_sync.py`
  - Centralized command tree sync management with cooldown protection
  - `safe_sync()`: Main sync function with rate limit handling and error recovery
  - Cooldown tracking: 60 minutes for global syncs, 30 minutes for per-guild syncs
  - **Cooldown Cleanup**: Periodic cleanup task (every 10 minutes) removes expired entries
  - Max 500 cooldown entries with automatic eviction of oldest entries
  - Automatic detection of guild-only commands to optimize sync strategy
  - Parallel guild syncs for faster startup (multiple guilds synced simultaneously)
  - Rate limit protection with graceful error handling and retry-after support
  - Used by `bot.py` on startup and when joining new guilds
  - Manual sync command (`!sync`) with cooldown feedback and force option

## Database Schema

The bot uses PostgreSQL for persistent storage. Schema is managed via Alembic migrations (see `alembic/versions/001_initial_schema.py` for complete schema).

### Core Tables
- `bot_settings`
  - `guild_id BIGINT`, `scope TEXT`, `key TEXT` (composite primary key)
  - `value JSONB`, `value_type TEXT`, `updated_by BIGINT`, `updated_at TIMESTAMPTZ`

- `settings_history`
  - `id SERIAL PRIMARY KEY`
  - `guild_id BIGINT`, `scope TEXT`, `key TEXT`
  - `old_value JSONB`, `new_value JSONB`, `changed_by BIGINT`, `changed_at TIMESTAMPTZ`, `change_type TEXT`

- `onboarding`
  - `guild_id BIGINT`, `user_id BIGINT` (composite primary key)
  - `responses JSONB` (answers by index; values may be string | list[str] | {choice, followup, followup_label})
  - `timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

- `guild_onboarding_questions`
  - `id SERIAL PRIMARY KEY`
  - `guild_id BIGINT`, `step_order INTEGER` (unique per guild)
  - `question TEXT`, `question_type TEXT`, `options JSONB`, `followup JSONB`
  - `required BOOLEAN`, `enabled BOOLEAN`

- `guild_rules`
  - `id SERIAL PRIMARY KEY`
  - `guild_id BIGINT`, `rule_order INTEGER` (unique per guild)
  - `title TEXT`, `description TEXT`, `enabled BOOLEAN`

- `reminders`
  - `id SERIAL PRIMARY KEY`
  - `guild_id BIGINT`, `name TEXT`, `channel_id BIGINT`
  - `time TIME` (reminder trigger time, T−60)
  - `call_time TIME` (event display time, T0)
  - `days TEXT[]` (0=Mon..6=Sun); empty for one-off events
  - `message TEXT`, `created_by BIGINT`
  - `origin_channel_id BIGINT`, `origin_message_id BIGINT`
  - `event_time TIMESTAMPTZ` (one-off event timestamp)
  - `location TEXT`, `last_sent_at TIMESTAMPTZ` (idempotency)

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

## Memory Management & Resource Limits

The bot implements comprehensive memory management to prevent memory leaks and resource exhaustion:

### Caching Strategies

- **Command Tracker Queue**: In-memory batching queue (max 10k entries) with automatic flush every 30s or at 1k entries threshold. Reduces database write pressure by batching command usage logs.

- **Guild Settings Cache**: LRU cache using `OrderedDict` with max 500 entries. Automatically evicts oldest entries when limit is reached. Eviction is logged for monitoring.

- **Command Stats Cache**: TTL cache (30 seconds) with max 50 entries. Caches command usage statistics to reduce database queries for dashboard metrics.

- **IP Rate Limits**: Dictionary tracking with max 1000 IP entries. Periodic cleanup (every 10+ minutes) removes expired entries and enforces size limit with LRU eviction.

- **Sync Cooldowns**: Dictionary tracking with max 500 entries. Periodic cleanup (every 10 minutes) removes entries older than cooldown period + 1 hour buffer.

- **Ticket Bot Cooldowns**: Dictionary tracking with max 1000 entries and max age of 1 hour. Cleanup happens on access (no periodic loop) to remove stale entries.

### Cleanup Background Tasks

All cleanup tasks run every 10+ minutes (not too frequent for low traffic guilds) to prevent unnecessary CPU overhead:

- IP rate limits cleanup: Removes empty lists and enforces max dict size
- Sync cooldowns cleanup: Removes expired entries and enforces max size
- Command tracker flush: Writes batched entries to database

### Monitoring

- **Cache Metrics Endpoint**: `/api/dashboard/metrics` includes `CacheMetrics` with sizes of all caches and dictionaries
- **Size Logging**: All cleanup operations log cache/dict sizes for monitoring
- **Eviction Logging**: Cache evictions are logged at debug level for troubleshooting

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
1. Bot startup: `setup_hook()` loads all cogs → `on_ready()` syncs commands (global once, then guild-only per guild in parallel)
2. New guild join: `on_guild_join()` automatically syncs guild-only commands to new server
3. User presses Start Onboarding → `ReactionRole` shows rules → starts `Onboarding`.
4. `Onboarding` prompts 4 questions; multi-select advances automatically; follow-ups via modal.
5. On completion: summary embed (ephemeral), log embed (log channel), role assignment, DB persist.
6. Reminders: via slash commands or auto from `EmbedReminderWatcher`.
7. `tasks.loop` in `reminders` dispatches messages at scheduled times:
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

### Logging
- Centralized logging via `utils/logger.py`
- Discord log embeds to configured log channel for created/sent/deleted/errors
- Rich embed logging for embed watcher parsing results
- Structured logging for health checks

### Metrics & Analytics
- `/api/health` enhanced endpoint with detailed metrics (guild count, command usage, GPT status, pool size)
- `/api/health/history` historical health data for trend analysis
- `/top-commands` command usage analytics (filterable by guild and time period)
- `/command_stats` Discord slash command for command usage statistics (admin-only)
- `utils/runtime_metrics.py` snapshots Discord bot state for the dashboard API without blocking the event loop
- `utils/command_tracker.py` automatically tracks all command executions with dedicated database pool in bot's event loop
- Command statistics included in `/api/dashboard/metrics`
- All command tracking persists across bot restarts

### Telemetry
- **Telemetry Ingest**: Background job continuously writes subsystem snapshots to Supabase `telemetry.subsystem_snapshots` table, ensuring Mind dashboard always has fresh data (runs every 30-60 seconds, configurable via `TELEMETRY_INGEST_INTERVAL`)
- **Health Check History**: All health checks are automatically logged to `health_check_history` table
- **Command Analytics**: All command executions are tracked in `audit_logs` table for usage analysis

## Security
- Tokens and DB credentials via env only (no hardcoded secrets)
- Optional controlled `@everyone` mentions via `ENABLE_EVERYONE_MENTIONS`
- **Input Sanitization & Injection Prevention:**
  - Centralized sanitization utilities in `utils/sanitizer.py`
  - **Markdown Injection Protection**: All user input sanitized before going into embed titles, descriptions, and fields
  - **Mention Spam Prevention**: User/role/channel mentions stripped from user input in embeds
  - **Prompt Injection Protection**: GPT prompts sanitized to block jailbreak attempts (patterns like "ignore previous", "act as", "system:", etc.)
  - **URL Filtering**: Optional URL removal from user input to prevent exploits
  - **Log Spam Prevention**: Log messages sanitized with length limits (200 chars) and control character removal
  - Applied across all user input flows: reminders, tickets, FAQs, onboarding, GPT commands
  - Comprehensive test suite with parametrized tests for attack vectors
- **Rate Limiting & Abuse Prevention:**
  - Discord command cooldowns via `@app_checks.cooldown()` decorator:
    - `/add_reminder`: 5 per minute per guild+user
    - `/learn_topic`: 3 per minute per guild+user
    - `/create_caption`: 3 per minute per guild+user
    - `/growthcheckin`: 2 per 5 minutes per guild+user
    - `/leaderhelp`: 3 per minute per guild+user
    - `/ticket`: 1 per 30 seconds per user
  - In-memory cooldowns for button interactions (e.g., ticket "Suggest reply" button: 5 seconds)
  - FastAPI IP-based rate limiting middleware:
    - 30 read requests per minute per IP
    - 10 write requests per minute per IP
    - Protects against anonymous abuse and cost explosions

## Testing & Quality

### Test Infrastructure
- **Pytest** configuration with `pytest.ini`
- **Test fixtures** in `tests/conftest.py` (MockBot, MockSettingsService, sample embeds)
- **Unit tests** for embed parsing (`tests/test_embed_watcher_parsing.py`) - 30 tests
- **Unit tests** for reminder logic (`tests/test_reminder_parsing.py`) - 20 tests
- **Unit tests** for input sanitization (`tests/test_sanitizer.py`) - parametrized tests for markdown injection, mention spam, prompt injection/jailbreak attempts, URL exploits, length limits, and edge cases
- **53+ total tests** covering parsing, timing, edge cases, day matching, and security

### Database Migrations
- **Alembic** migration system configured (`alembic/` directory)
- **Baseline migration** (`001_initial_schema.py`) documents all existing tables
- **Migration commands** via `/migrate` and `/migrate_status` Discord commands
- **Migration guide** in `docs/migrations.md`
- Schema changes can now be versioned and tracked

## Recent Improvements (v1.9.0+)

### Database Architecture
- **Connection Pools**: All database connections use `asyncpg` connection pools instead of direct connections
- **Improved Reliability**: Better error handling for connection errors (`ConnectionDoesNotExistError`, `InterfaceError`, `ConnectionResetError`)
- **Graceful Shutdown**: Background tasks check pool status before operations and handle shutdown gracefully
- **Event Loop Isolation**: Command tracker uses dedicated pool in bot's event loop to avoid conflicts with FastAPI
- **Pool Management**: Each cog manages its own connection pool with appropriate size limits (typically 5-10 connections)

### Command Analytics
- Automatic tracking of all command executions via event handlers
- Command usage statistics in dashboard metrics
- `/top-commands` API endpoint for analytics
- `/command_stats` Discord slash command for real-time statistics (admin-only)
- Persistent tracking across bot restarts
- Dedicated database pool for command tracking in bot's event loop

### Health Monitoring
- Enhanced health endpoint with detailed metrics
- Health check history for trend analysis
- Structured logging for health checks

### Reminder Enhancements
- `/reminder_edit` command with modal interface
- Improved embed parsing with relative date support
- Rich embed logging for parsing results
- Midnight edge case handling

### GPT Integration
- Retry queue for rate-limited requests
- Fallback messages when GPT is unavailable
- Background retry task with exponential backoff
