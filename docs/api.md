# API Reference

Complete API documentation for the Alphapy Discord Bot FastAPI server.

## Base URL

All API endpoints are prefixed with `/api` unless otherwise noted.

## Endpoint Categories

- **Health & Status**: Basic health checks and monitoring (`/api/health`, `/api/health/history`)
- **Metrics & Analytics**: Dashboard metrics and command analytics (`/api/dashboard/metrics`, `/top-commands`)
- **Dashboard Configuration**: Web dashboard endpoints for managing settings, onboarding, auto-moderation (requires Supabase JWT)
- **Auto-Moderation**: Complete auto-moderation rule management with analytics (`/api/dashboard/{guild_id}/automod/*`)
- **Onboarding Management**: Questions, rules, and flow configuration (`/api/dashboard/{guild_id}/onboarding/*`)
- **Reminder Management**: User-facing reminder CRUD operations (requires API key + user ID)
- **Exports**: CSV export endpoints for tickets and FAQ
- **Webhooks**: Incoming webhooks from Core-API (app-reflections, revoke-reflection); validated via `X-Webhook-Signature`

**Note for Mind Dashboard**: Mind primarily uses:
- `/api/dashboard/metrics` (or `/api/metrics` alias) for live metrics
- `/api/health` for health checks
- Dashboard configuration endpoints for web UI management

## Authentication

Most endpoints require authentication via:
- **API Key**: Pass in `X-API-Key` header
- **Supabase JWT**: Pass in `Authorization: Bearer <token>` header for dashboard endpoints
- **User ID**: Pass in `X-User-Id` header (for user-specific endpoints)

Example:
```bash
curl -H "X-API-Key: your_api_key" -H "X-User-Id: 123456789" \
  https://your-bot-url/api/reminders/123456789
```

Dashboard endpoints example:
```bash
curl -H "Authorization: Bearer supabase_token" \
  https://your-bot-url/api/dashboard/123456789/settings
```

## Endpoints

### Health & Status

#### `GET /api/health`

Enhanced health check endpoint with detailed metrics.

**Response:**
```json
{
  "service": "alphapy",
  "version": "2.4.0",
  "uptime_seconds": 3600,
  "db_status": "ok",
  "timestamp": "2026-01-21T12:00:00Z",
  "guild_count": 2,
  "active_commands_24h": 150,
  "gpt_status": "operational",
  "database_pool_size": 5
}
```

#### `GET /status`

Simple status check endpoint (legacy, no authentication required).

**Response:**
```json
{
  "online": true,
  "latency": 0,
  "uptime": "60 min"
}
```

**Fields:**
- `service`: Service name
- `version`: Bot version
- `uptime_seconds`: Uptime in seconds
- `db_status`: Database status (`ok`, `not_initialized`, or `error:...`)
- `timestamp`: ISO timestamp of check
- `guild_count`: Number of guilds bot is connected to (optional)
- `active_commands_24h`: Number of commands executed in last 24 hours (optional)
- `gpt_status`: Grok/LLM service status (`operational`, `degraded`, `error`) (optional)
- `database_pool_size`: Current size of the database connection pool (managed automatically by `asyncpg`)

#### `GET /api/health/history`

Get historical health check data for trend analysis.

**Query Parameters:**
- `hours` (optional, default: 24): Number of hours to look back
- `limit` (optional, default: 100): Maximum number of records to return

**Response:**
```json
{
  "history": [
    {
      "service": "alphapy",
      "version": "2.4.0",
      "uptime_seconds": 3600,
      "db_status": "ok",
      "guild_count": 2,
      "active_commands_24h": 150,
      "gpt_status": "operational",
      "database_pool_size": 5,
      "checked_at": "2026-01-21T12:00:00Z"
    }
  ],
  "period_hours": 24,
  "total_records": 1
}
```

### Metrics & Analytics

#### `GET /api/dashboard/metrics`

Comprehensive dashboard metrics including bot status, Grok/LLM stats, reminders, tickets, and command usage.

**Authentication:** Required (Supabase JWT token)

**Query Parameters:**
- `guild_id` (optional): Filter metrics by guild ID

**Response:**
```json
{
  "bot": {
    "version": "2.4.0",
    "codename": "Lifecycle Manager",
    "online": true,
    "latency_ms": 45.2,
    "uptime_seconds": 3600,
    "uptime_human": "1 hour",
    "commands_loaded": 30,
    "guilds": [...]
  },
  "gpt": {
    "last_success_time": "2026-01-21T12:00:00Z",
    "average_latency_ms": 1200,
    "total_tokens_today": 5000,
    "success_count": 100,
    "error_count": 2,
    ...
  },
  "reminders": {
    "total": 15,
    "recurring": 10,
    "one_off": 5,
    "next_event_time": "2026-01-21T19:00:00Z",
    ...
  },
  "tickets": {
    "total": 50,
    "open_count": 5,
    "per_status": {...},
    "open_ticket_ids": [123, 456, 789],
    "open_items": [
      {
        "id": 123,
        "username": "user123",
        "status": "open",
        "channel_id": 987654321,
        "created_at": "2026-01-21T12:00:00Z"
      }
    ],
    ...
  },
  "command_usage": {
    "top_commands": [
      {"command_name": "add_reminder", "usage_count": 45},
      {"command_name": "ticket", "usage_count": 30}
    ],
    "total_commands_24h": 150,
    "period_days": 7
  },
  "infrastructure": {
    "database_up": true,
    "pool_size": 5,
    "checked_at": "2026-01-21T12:00:00Z"
  },
  "premium_metrics": {
    "premium_checks_total": 120,
    "premium_checks_core_api": 80,
    "premium_checks_local": 40,
    "premium_cache_hits": 200,
    "premium_transfers_count": 3,
    "premium_cache_size": 25
  }
}
```

The optional `premium_metrics` block provides observability for the Premium guard:

- `premium_checks_total`: Total number of premium checks performed
- `premium_checks_core_api`: Checks served by the Core-API
- `premium_checks_local`: Checks served from local database/cache
- `premium_cache_hits`: Number of cache hits when resolving premium status
- `premium_transfers_count`: Number of premium transfers between guilds
- `premium_cache_size`: Current in-memory cache size for premium status

#### `GET /api/metrics`

Alias for `/api/dashboard/metrics` - provided for compatibility with Mind monitoring system.

**Authentication:** Required (Supabase JWT token)

**Query Parameters:**
- `guild_id` (optional): Filter metrics by guild ID

**Response:** Same as `/api/dashboard/metrics`

#### `GET /top-commands`

Command usage analytics endpoint.

**Query Parameters:**
- `guild_id` (optional): Filter by guild ID
- `days` (optional, default: 7): Number of days to look back
- `limit` (optional, default: 10): Maximum number of commands to return

**Response:**
```json
{
  "commands": {
    "add_reminder": 45,
    "ticket": 30,
    "reminder_list": 20
  },
  "period_days": 7,
  "guild_id": null,
  "total_commands": 3
}
```

### Dashboard Configuration Endpoints

These endpoints are used by the web dashboard (Mind) for configuration management.

#### `GET /api/dashboard/settings/{guild_id}`

Get all settings for a specific guild, organized by category.

**Authentication:** Required (Supabase JWT token)

**Path Parameters:**
- `guild_id` (required): Discord guild ID

**Response:**
```json
{
  "system": {
    "log_channel_id": 123456789,
    "rules_channel_id": 987654321,
    "log_level": "verbose"
  },
  "reminders": {
    "enabled": true,
    "default_channel_id": 111222333,
    "allow_everyone_mentions": false
  },
  "embedwatcher": {
    "announcements_channel_id": 444555666,
    "reminder_offset_minutes": 60,
    "gpt_fallback_enabled": true,
    "non_embed_enabled": false,
    "process_bot_messages": false
  },
  "gpt": {
    "model": "grok-3",
    "temperature": 0.7
  },
  "invites": {
    "enabled": true,
    "announcement_channel_id": 123456789,
    "with_inviter_template": "{member} joined! {inviter} now has {count} invites.",
    "no_inviter_template": "{member} joined, but no inviter data found."
  },
  "gdpr": {
    "enabled": true,
    "channel_id": 123456789
  },
  "automod": {
    "enabled": false,
    "log_channel_id": 123456789,
    "log_actions": true,
    "log_to_database": true
  },
  "onboarding": {
    "enabled": true,
    "mode": "rules_with_questions",
    "completion_role_id": 123456789,
    "join_role_id": 987654321
  },
  "ticketbot": {
    "category_id": 123456789,
    "staff_role_id": 987654321,
    "escalation_role_id": 555666777,
    "idle_days_threshold": 5,
    "auto_close_days_threshold": 14
  },
  "verification": {
    "verified_role_id": 123456789,
    "category_id": 987654321,
    "vision_model": "grok-3"
  }
}
```

#### `POST /api/dashboard/settings/{guild_id}`

Update settings for a specific guild category.

**Authentication:** Required (Supabase JWT token)

**Path Parameters:**
- `guild_id` (required): Discord guild ID

**Request Body:**
```json
{
  "category": "reminders",
  "settings": {
    "default_channel_id": "111222333",
    "allow_everyone_mentions": false
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Updated reminders settings"
}
```

#### `GET /api/dashboard/{guild_id}/onboarding/questions`

Get all onboarding questions for a guild.

**Authentication:** Required (Supabase JWT token)

**Response:**
```json
[
  {
    "id": 1,
    "question": "What is your trading experience?",
    "question_type": "select",
    "options": [{"label": "Beginner", "value": "beginner"}],
    "required": true,
    "enabled": true,
    "step_order": 1
  }
]
```

#### `POST /api/dashboard/{guild_id}/onboarding/questions`

Save or update an onboarding question.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Request Body:** Same structure as GET response

#### `PUT /api/dashboard/{guild_id}/onboarding/questions/{question_id}`

Update an onboarding question.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Request Body:** Same structure as GET response (all fields optional except `question_type`)

#### `DELETE /api/dashboard/{guild_id}/onboarding/questions/{question_id}`

Delete an onboarding question.

**Authentication:** Required (Supabase JWT token + guild admin access)

#### `GET /api/dashboard/{guild_id}/onboarding/rules`

Get all onboarding rules for a guild.

**Authentication:** Required (Supabase JWT token)

**Response:**
```json
[
  {
    "id": 1,
    "title": "Be Respectful",
    "description": "Treat all members with respect",
    "thumbnail_url": "https://example.com/thumb.png",
    "image_url": "https://example.com/image.png",
    "enabled": true,
    "rule_order": 1
  }
]
```

`thumbnail_url` and `image_url` are optional; shown as thumbnail (right) and image (bottom) in rule embeds.

#### `POST /api/dashboard/{guild_id}/onboarding/rules`

Save or update an onboarding rule.

**Authentication:** Required (Supabase JWT token + guild admin access)

#### `PUT /api/dashboard/{guild_id}/onboarding/rules/{rule_id}`

Update an onboarding rule.

**Authentication:** Required (Supabase JWT token + guild admin access)

#### `DELETE /api/dashboard/{guild_id}/onboarding/rules/{rule_id}`

Delete an onboarding rule.

**Authentication:** Required (Supabase JWT token + guild admin access)

#### `POST /api/dashboard/{guild_id}/onboarding/reorder`

Reorder onboarding questions and rules.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Request Body:**
```json
{
  "questions": [1, 3, 2],
  "rules": [2, 1]
}
```

**Response:**
```json
{
  "success": true
}
```

#### `GET /api/dashboard/{guild_id}/settings/history`

Get settings change history for a guild.

**Authentication:** Required (Supabase JWT token)

**Query Parameters:**
- `scope` (optional): Filter by scope (e.g., "reminders")
- `key` (optional): Filter by specific key
- `limit` (optional, default: 50): Maximum number of records

**Response:**
```json
[
  {
    "id": 1,
    "scope": "reminders",
    "key": "default_channel_id",
    "old_value": "111222333",
    "new_value": "444555666",
    "changed_by": 123456789,
    "changed_at": "2026-01-21T12:00:00Z",
    "change_type": "updated"
  }
]
```

#### `POST /api/dashboard/{guild_id}/settings/rollback/{history_id}`

Rollback a setting to a previous value.

**Authentication:** Required (Supabase JWT token)

**Response:**
```json
{
  "success": true,
  "message": "Rolled back reminders.default_channel_id to previous value"
}
```

### Auto-Moderation Management

#### `GET /api/dashboard/{guild_id}/automod/rules`

List all auto-moderation rules for a guild.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Response:**
```json
[
  {
    "id": 1,
    "guild_id": 123456789,
    "rule_type": "content",
    "name": "No Bad Words",
    "enabled": true,
    "config": {
      "content_type": "bad_words",
      "words": ["spam", "curse"]
    },
    "action_type": "warn",
    "action_config": {
      "message": "Please watch your language!"
    },
    "severity": 1,
    "created_by": 987654321,
    "created_at": "2026-01-21T12:00:00Z",
    "updated_at": "2026-01-21T12:00:00Z",
    "is_premium": false
  }
]
```

#### `POST /api/dashboard/{guild_id}/automod/rules`

Create a new auto-moderation rule.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Request Body:**
```json
{
  "rule_type": "content",
  "name": "No Links",
  "enabled": true,
  "config": {
    "content_type": "links",
    "allow_links": false,
    "whitelist": ["discord.com"],
    "blacklist": ["spam.com"]
  },
  "action_type": "delete",
  "action_config": {},
  "severity": 2
}
```

**Response:** Returns the created rule with assigned ID

#### `PUT /api/dashboard/{guild_id}/automod/rules/{rule_id}`

Update an existing auto-moderation rule.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Request Body:**
```json
{
  "name": "Updated Rule Name",
  "enabled": false,
  "severity": 3
}
```

**Response:** Returns the updated rule

#### `DELETE /api/dashboard/{guild_id}/automod/rules/{rule_id}`

Delete an auto-moderation rule.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Response:**
```json
{
  "success": true
}
```

#### `GET /api/dashboard/{guild_id}/automod/stats`

Get auto-moderation statistics and analytics.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Response:**
```json
{
  "total_rules": 5,
  "enabled_rules": 3,
  "rules_by_type": {
    "content": 2,
    "spam": 1,
    "links": 1,
    "mentions": 1
  },
  "total_violations": 127,
  "violations_today": 8,
  "violations_week": 45,
  "top_violated_rules": [
    {
      "name": "No Bad Words",
      "rule_type": "content",
      "violation_count": 23
    }
  ]
}
```

#### `GET /api/dashboard/{guild_id}/automod/violations`

Get recent auto-moderation violation logs.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Query Parameters:**
- `limit` (optional, default: 50): Maximum number of violations to return
- `days` (optional, default: 7): Number of days to look back

**Response:**
```json
[
  {
    "id": 1,
    "guild_id": 123456789,
    "user_id": 987654321,
    "message_id": 111222333,
    "channel_id": 444555666,
    "rule_id": 1,
    "action_taken": "warn",
    "message_content": "This message contained bad words",
    "ai_analysis": null,
    "context": {},
    "timestamp": "2026-01-21T12:00:00Z",
    "moderator_id": null
  }
]
```

#### `GET /api/dashboard/{guild_id}/automod/settings`

Get auto-moderation specific settings.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Response:**
```json
{
  "enabled": false,
  "log_channel_id": 123456789,
  "log_actions": true,
  "log_to_database": true
}
```

#### `POST /api/dashboard/{guild_id}/automod/settings`

Update auto-moderation settings.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Request Body:**
```json
{
  "enabled": true,
  "log_channel_id": 123456789,
  "log_actions": true,
  "log_to_database": true
}
```

**Response:**
```json
{
  "success": true
}
```

#### `GET /api/dashboard/logs`

Get operational logs (reconnect, disconnect, etc.) for the Mind dashboard. Requires guild admin access (verified via Supabase profile's Discord ID). Global events (e.g. `BOT_RECONNECT`, `BOT_DISCONNECT`) are included for any guild request.

**Authentication:** Required (Supabase JWT token + guild admin access)

**Query Parameters:**
- `guild_id` (required): Discord guild ID – user must have admin access to this guild
- `limit` (optional, default: 50, max: 100): Maximum number of log entries to return
- `event_types` (optional): Comma-separated list of event types to filter (e.g. `BOT_RECONNECT,BOT_DISCONNECT`)

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-02-10T21:30:00Z",
      "event_type": "BOT_RECONNECT",
      "guild_id": null,
      "message": "Reconnect phase complete: commands synced",
      "details": {"synced": 5, "skipped": 0}
    }
  ]
}
```

**Event types:**
- `BOT_READY` – Bot startup complete
- `BOT_RECONNECT` – Bot reconnected and resynced commands (includes `synced` and `skipped` counts)
- `BOT_DISCONNECT` – Bot disconnected from Discord
- `GUILD_SYNC` – Command sync per guild (success/failure/cooldown, includes `sync_type`: startup/reconnect/guild_join)
- `ONBOARDING_ERROR` – Onboarding errors (no rules configured, role assignment failures, member not found)
- `SETTINGS_CHANGED` – Settings changes via commands or API (includes `action`: set/clear/bulk_update/rollback, `source`: command/api)
- `COG_ERROR` – Slash command errors per guild (includes command name, user ID, error type)

### Reminder Management

#### `GET /api/reminders/{user_id}`

List reminders for a specific user.

**Authentication:** Required (API key + `X-User-Id` header; `X-User-Id` must match `user_id` in path)

**Path Parameters:**
- `user_id` (required): Discord user ID whose reminders to fetch

**Response:**
```json
[
  {
    "id": 1,
    "name": "Weekly Meeting",
    "channel_id": 123456789,
    "time": "18:00:00",
    "call_time": "19:00:00",
    "days": ["2"],
    "message": "Weekly team meeting",
    "location": "Conference Room",
    "event_time": null,
    "created_at": "2026-01-21T10:00:00Z"
  }
]
```

#### `POST /api/reminders`

Create a new reminder.

**Authentication:** Required (API key + `X-User-Id` header)

**Request Body:**
```json
{
  "name": "Team Standup",
  "channel_id": 123456789,
  "time": "09:00:00",
  "days": ["0", "2", "4"],
  "message": "Daily standup meeting",
  "location": "Main Channel"
}
```

#### `PUT /api/reminders`

Update an existing reminder.

**Authentication:** Required (API key + `X-User-Id` header; reminder's `user_id` must match `X-User-Id`)

**Request Body:** Same as POST, include `id` in payload. All fields optional except `id` and `user_id`.

#### `DELETE /api/reminders/{reminder_id}/{created_by}`

Delete a reminder.

**Authentication:** Required (API key + `X-User-Id` header; `created_by` must match `X-User-Id`)

**Path Parameters:**
- `reminder_id` (required): ID of the reminder to delete
- `created_by` (required): Discord user ID who created the reminder

### Exports

**Note:** Ticket and FAQ exports are available via Discord slash commands (`/export_tickets`, `/export_faq`), not API endpoints. These commands are admin-only and generate CSV files sent via Discord.

## Webhooks

These endpoints receive payloads from Core-API. They do not use API key authentication; use `X-Webhook-Signature` (HMAC) with the configured secret (`APP_REFLECTIONS_WEBHOOK_SECRET` or fallback). See [Configuration](configuration.md) for environment variables.

### `POST /webhooks/app-reflections`

Receives plaintext reflection content from the App via Core-API. Payload is stored in `app_reflections` and used for Grok context in user-self flows (e.g. `/growthcheckin` only; not used for ticket "Suggest reply" for privacy).

**Headers:** `X-Webhook-Signature` (optional if no secret configured)

**Request body:**
```json
{
  "user_id": 123456789,
  "reflection_id": "uuid-from-app",
  "plaintext_content": { "reflection_text": "...", "mantra": "...", "thoughts": "...", "future_message": "...", "date": "YYYY-MM-DD" }
}
```

**Response:** `200` with `{"status": "acknowledged", "reflection_id": "..."}`.

### `POST /webhooks/revoke-reflection`

Deletes a previously stored reflection when the user revokes consent in the App. Core-API sends this after consent is revoked.

**Headers:** `X-Webhook-Signature` (optional if no secret configured)

**Request body:**
```json
{
  "user_id": 123456789,
  "reflection_id": "uuid-from-app"
}
```

**Response:** `200` with `{"status": "deleted", "count": 1}` (or `count: 0` if no row matched).

## Error Responses

All endpoints may return standard HTTP error codes:

- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

Error response format:
```json
{
  "detail": "Error message description"
}
```

## Rate Limiting

- Health endpoints: No rate limiting
- Metrics endpoints: Rate limited per authentication token
- Reminder endpoints: Rate limited per user ID
- Export endpoints: Rate limited per API key

## Versioning

Current API version: **2.4.0** (Lifecycle Manager)

Version information is included in health check responses and can be queried via `/api/health`.

## Data Types Reference

### Settings Categories

- **system**: Log channels, log level
- **reminders**: Reminder functionality, default channels
- **embedwatcher**: Embed parsing, reminder offsets
- **gpt**: AI model configuration
- **invites**: Invite tracking settings
- **gdpr**: GDPR compliance settings
- **automod**: Auto-moderation configuration
- **onboarding**: User onboarding flow
- **ticketbot**: Ticket system configuration
- **verification**: Payment verification setup

### Auto-Moderation Rule Types

- `spam`: Message spam detection
- `content`: Content filtering (bad words, links, etc.)
- `regex`: Custom regex patterns (premium)
- `ai`: AI-powered content analysis (premium)
- `mentions`: Mention spam detection
- `caps`: Excessive capitalization
- `duplicate`: Duplicate message detection

### Auto-Moderation Action Types

- `delete`: Delete message
- `warn`: Send warning message
- `mute`: Mute user (premium)
- `timeout`: Timeout user (premium)
- `ban`: Ban user (premium)

### Onboarding Question Types

- `text`: Free text input
- `email`: Email validation
- `select`: Single choice dropdown
- `multiselect`: Multiple choice checkboxes
