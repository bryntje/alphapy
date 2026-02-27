# Database Schema Reference

Complete reference for all database tables used by the Alphapy Discord Bot.

## Overview

The bot uses PostgreSQL for persistent storage. Schema is managed via [Alembic migrations](migrations.md). All tables support multi-guild architecture via `guild_id` columns.

## Tables

### `bot_settings`

Guild-specific bot configuration settings.

**Columns:**
- `guild_id` (BIGINT, NOT NULL): Discord guild ID
- `scope` (TEXT, NOT NULL): Setting scope (e.g., "system", "reminders", "gpt")
- `key` (TEXT, NOT NULL): Setting key
- `value` (JSONB, NOT NULL): Setting value (stored as JSON)
- `value_type` (TEXT): Type of value (e.g., "channel", "bool", "int")
- `updated_by` (BIGINT): User ID who last updated this setting
- `updated_at` (TIMESTAMPTZ): Last update timestamp

**Primary Key:** `(guild_id, scope, key)`

**Indexes:** None (primary key provides efficient lookups)

---

### `settings_history`

Audit trail for settings changes.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `guild_id` (BIGINT, NOT NULL)
- `scope` (TEXT, NOT NULL)
- `key` (TEXT, NOT NULL)
- `old_value` (JSONB): Previous value
- `new_value` (JSONB, NOT NULL): New value
- `value_type` (TEXT)
- `changed_by` (BIGINT): User ID who made the change
- `changed_at` (TIMESTAMPTZ): Change timestamp
- `change_type` (TEXT, NOT NULL): Type of change (e.g., "created", "updated", "deleted", "rollback")

**Indexes:**
- `idx_settings_history_guild_scope_key` on `(guild_id, scope, key)`
- `idx_settings_history_changed_at` on `changed_at`

---

### `reminders`

Scheduled reminders (recurring and one-off events).

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `guild_id` (BIGINT, NOT NULL)
- `name` (TEXT, NOT NULL): Reminder name
- `channel_id` (BIGINT, NOT NULL): Channel to send reminder to
- `time` (TIME): Reminder trigger time (T−60 for one-off, reminder time for recurring)
- `call_time` (TIME): Event display time (T0, what user sees)
- `days` (TEXT[]): Days of week (0=Mon..6=Sun); empty for one-off events
- `message` (TEXT): Reminder message content
- `created_by` (BIGINT): User ID who created the reminder
- `origin_channel_id` (BIGINT): Original channel where embed was detected
- `origin_message_id` (BIGINT): Original message ID
- `event_time` (TIMESTAMPTZ): One-off event timestamp (NULL for recurring)
- `location` (TEXT): Event location
- `last_sent_at` (TIMESTAMPTZ): Last send timestamp (for idempotency)
- `image_url` (TEXT): Optional image or banner URL (Premium feature)

**Indexes:**
- `idx_reminders_time` on `time`
- `idx_reminders_event_time` on `event_time`

**Notes:**
- One-off events: `event_time` is set, `days` is empty
- Recurring events: `event_time` is NULL, `days` contains weekday numbers
- `time` is the reminder trigger time (T−60), `call_time` is the event time (T0)
- Premium: reminders with `image_url` require an active premium subscription for the creator

---

### `premium_subs`

Premium subscription status (local fallback when Core-API is unavailable). **One active subscription per user**; it applies to a single guild. Users can move it via `/premium_transfer` (or dashboard later).

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `user_id` (BIGINT, NOT NULL): Discord user ID
- `guild_id` (BIGINT, NOT NULL): Guild where Premium is active (can be updated for transfer)
- `tier` (TEXT, NOT NULL): `monthly`, `yearly`, `lifetime`
- `status` (TEXT, NOT NULL): `active`, `cancelled`, `expired`
- `stripe_subscription_id` (TEXT): External subscription ID (for support/cancellation only)
- `expires_at` (TIMESTAMPTZ): NULL for lifetime or N/A
- `created_at` (TIMESTAMPTZ): When the record was created

**Indexes:**
- `idx_premium_subs_user_guild` on `(user_id, guild_id)`
- `idx_premium_subs_guild_status` on `(guild_id, status)`
- `idx_premium_subs_one_active_per_user`: unique on `(user_id)` WHERE `status = 'active'` (enforces one active per user)

**GDPR:** This table stores only access-control data (user_id, guild_id, tier, status, optional external ID, expiry). No payment details, email, or other PII are stored here.

---

### `onboarding`

User onboarding responses per guild.

**Columns:**
- `guild_id` (BIGINT, NOT NULL)
- `user_id` (BIGINT, NOT NULL)
- `responses` (JSONB): User responses (answers by question index, plus personalization keys)
- `timestamp` (TIMESTAMP): Response timestamp

**Primary Key:** `(guild_id, user_id)`

**Notes:**
- Responses stored as JSONB with flexible structure
- Supports multi-select, text input, email validation, and follow-up questions
- Fixed personalization keys (synthetic steps after guild questions): `personalized_opt_in` (`"full"` | `"events_only"` | `"no"`), `preferred_language` (e.g. `"en"`, `"nl"`, or `"other: <text>"`)

---

### `guild_onboarding_questions`

Onboarding question definitions per guild.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `guild_id` (BIGINT, NOT NULL)
- `step_order` (INTEGER, NOT NULL): Question order
- `question` (TEXT, NOT NULL): Question text
- `question_type` (TEXT, NOT NULL): Type (select, multiselect, text, email)
- `options` (JSONB): Options for select/multiselect questions
- `followup` (JSONB): Conditional follow-up questions
- `required` (BOOLEAN): Whether question is required
- `enabled` (BOOLEAN): Whether question is enabled
- `created_at` (TIMESTAMP): Creation timestamp
- `updated_at` (TIMESTAMP): Last update timestamp

**Unique Constraint:** `(guild_id, step_order)`

---

### `guild_rules`

Guild rules for onboarding display.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `guild_id` (BIGINT, NOT NULL)
- `rule_order` (INTEGER, NOT NULL): Display order
- `title` (TEXT, NOT NULL): Rule title
- `description` (TEXT, NOT NULL): Rule description
- `thumbnail_url` (TEXT, nullable): Image shown right/top in embed (rechts)
- `image_url` (TEXT, nullable): Image shown at bottom in embed (onderaan)
- `enabled` (BOOLEAN): Whether rule is enabled
- `created_at` (TIMESTAMP): Creation timestamp
- `updated_at` (TIMESTAMP): Last update timestamp

**Unique Constraint:** `(guild_id, rule_order)`

---

### `support_tickets`

Support ticket system data.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `guild_id` (BIGINT, NOT NULL)
- `user_id` (BIGINT, NOT NULL): Ticket creator
- `username` (TEXT): Username at creation time
- `description` (TEXT, NOT NULL): Ticket description
- `status` (TEXT): Ticket status (open, claimed, waiting_for_user, escalated, closed, archived)
- `created_at` (TIMESTAMPTZ): Creation timestamp
- `channel_id` (BIGINT): Private channel ID for this ticket
- `claimed_by` (BIGINT): User ID who claimed the ticket
- `claimed_at` (TIMESTAMPTZ): Claim timestamp
- `updated_at` (TIMESTAMPTZ): Last update timestamp
- `escalated_to` (BIGINT): Role ID for escalation
- `archived_at` (TIMESTAMPTZ): When the ticket was archived (NULL if not archived)
- `archived_by` (BIGINT): User ID who archived the ticket

**Indexes:**
- `idx_support_tickets_user_id` on `user_id`
- `idx_support_tickets_status` on `status`
- `idx_support_tickets_channel_id` on `channel_id`

---

### `ticket_summaries`

GPT-generated summaries of closed tickets.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `ticket_id` (INTEGER, NOT NULL): Reference to support_tickets.id
- `summary` (TEXT, NOT NULL): GPT-generated summary
- `similarity_key` (TEXT): Key for detecting similar tickets
- `created_at` (TIMESTAMPTZ): Creation timestamp

**Notes:**
- Used for FAQ proposal generation when 3+ similar summaries appear

---

### `ticket_metrics`

Ticket statistics snapshots.

**Columns:**
- `id` (BIGSERIAL PRIMARY KEY)
- `snapshot` (JSONB): Full snapshot data
- `scope` (TEXT): Time scope (7d, 30d, all)
- `counts` (JSONB): Status → count mapping
- `average_cycle_time` (BIGINT): Average ticket lifecycle in seconds
- `triggered_by` (BIGINT): User ID who triggered the snapshot
- `created_at` (TIMESTAMPTZ): Snapshot timestamp

---

### `faq_entries`

FAQ entries for knowledge base.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `title` (TEXT): Entry title
- `summary` (TEXT): Entry summary/content
- `keywords` (TEXT[]): Search keywords
- `created_at` (TIMESTAMPTZ): Creation timestamp

**Notes:**
- Can be created manually or from ticket summaries via "Add to FAQ" button

---

### `faq_search_logs`

FAQ search analytics.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `user_id` (BIGINT): User who searched
- `query` (TEXT): Search query
- `results_count` (INTEGER): Number of results returned
- `searched_at` (TIMESTAMPTZ): Search timestamp

---

### `audit_logs`

Command usage analytics (automatically tracked).

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `guild_id` (BIGINT, NOT NULL): Guild where command was executed (0 for DMs)
- `user_id` (BIGINT, NOT NULL): User who executed the command
- `command_name` (TEXT, NOT NULL): Command name
- `command_type` (TEXT, NOT NULL): Type ('slash' or 'text')
- `success` (BOOLEAN): Whether command executed successfully
- `error_message` (TEXT): Error message if command failed
- `created_at` (TIMESTAMPTZ): Execution timestamp

**Indexes:**
- `idx_audit_logs_guild_created` on `(guild_id, created_at)`
- `idx_audit_logs_command` on `(command_name, created_at)`

**Notes:**
- Automatically populated by event handlers in `bot.py` (`on_app_command_completion`, `on_command_completion`, etc.)
- Uses dedicated database connection pool created in bot's event loop (not FastAPI's loop)
- Initialized in `on_ready()` event handler, persists across bot restarts
- Used for command usage analytics, dashboard metrics, and `/command_stats` Discord command
- Tracking is non-blocking and failures don't affect command execution

---

### `health_check_history`

Historical health check data for trend analysis.

**Columns:**
- `id` (SERIAL PRIMARY KEY)
- `service` (TEXT, NOT NULL): Service name
- `version` (TEXT, NOT NULL): Bot version
- `uptime_seconds` (INTEGER, NOT NULL): Uptime at check time
- `db_status` (TEXT, NOT NULL): Database status
- `guild_count` (INTEGER): Number of guilds
- `active_commands_24h` (INTEGER): Commands executed in last 24h
- `gpt_status` (TEXT): GPT service status
- `database_pool_size` (INTEGER): Database pool size
- `checked_at` (TIMESTAMPTZ): Health check timestamp

**Indexes:**
- `idx_health_check_history_checked_at` on `checked_at DESC`
- `idx_health_check_history_service` on `(service, checked_at DESC)`

**Notes:**
- Automatically populated on each `/api/health` call
- Auto-cleanup: Records older than 30 days are automatically deleted

---

## Database Connection Architecture

The bot uses `asyncpg` connection pools for all database operations, providing:
- **Better concurrency**: Multiple operations can run simultaneously
- **Connection reuse**: Efficient resource management
- **Graceful error handling**: Automatic retry and recovery from connection errors
- **Event loop isolation**: Command tracker uses dedicated pool in bot's event loop

### Connection Pool Configuration

Each component manages its own connection pool with appropriate size limits:
- **FastAPI (`api.py`)**: Main pool for API endpoints (shared with bot)
- **Command Tracker**: Dedicated pool in bot's event loop (min_size=1, max_size=5)
- **Reminders Cog**: Pool for reminder operations (max_size=10)
- **Ticket Bot**: Pool for ticket operations (max_size=10)
- **FAQ Cog**: Pool for FAQ operations (max_size=5)
- **Embed Watcher**: Pool for embed parsing (max_size=10)
- **Other Cogs**: Individual pools as needed (typically max_size=5)

All pools include:
- Connection timeout handling
- Graceful shutdown on cog unload
- Error handling for connection failures
- Pool status checks before operations

## Schema Management

All schema changes are managed via Alembic migrations. See [migrations.md](migrations.md) for migration workflow.

**Current Migration:** `001_initial` (baseline)

To view current schema state:
```bash
alembic current
```

To apply migrations:
```bash
alembic upgrade head
```

---

## Multi-Guild Architecture

All tables that store guild-specific data include a `guild_id` column:
- `bot_settings`
- `settings_history`
- `reminders`
- `onboarding`
- `guild_onboarding_questions`
- `guild_rules`
- `support_tickets`
- `audit_logs`

Tables without `guild_id` are global:
- `ticket_summaries` (linked via `ticket_id` → `support_tickets` → `guild_id`)
- `ticket_metrics` (scope-based, not guild-specific)
- `faq_entries` (global knowledge base)
- `faq_search_logs` (analytics)
- `health_check_history` (system-wide)

---

## Indexes

All tables have appropriate indexes for common query patterns:
- Primary keys provide efficient lookups
- Foreign key columns are indexed where applicable
- Time-based columns have indexes for range queries
- Composite indexes support multi-column filters

---

## Data Retention

- **Health check history**: Auto-deletes records older than 30 days
- **Audit logs**: No automatic cleanup (can be configured per guild)
- **Ticket summaries**: No automatic cleanup
- **Other tables**: No automatic cleanup (manual maintenance recommended)

---

## Backup Recommendations

Regular backups should include:
- All tables (full database backup recommended)
- Focus on `bot_settings`, `reminders`, `support_tickets`, `onboarding` for critical data
- `audit_logs` and `health_check_history` can be excluded from frequent backups (analytics only)
