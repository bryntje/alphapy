# API Reference

Complete API documentation for the Alphapy Discord Bot FastAPI server.

## Base URL

All API endpoints are prefixed with `/api` unless otherwise noted.

## Endpoint Categories

- **Health & Status**: Basic health checks and monitoring (`/api/health`, `/api/health/history`)
- **Metrics & Analytics**: Dashboard metrics and command analytics (`/api/dashboard/metrics`, `/top-commands`)
- **Dashboard Configuration**: Web dashboard endpoints for managing settings, onboarding, etc. (requires Supabase JWT)
- **Reminder Management**: User-facing reminder CRUD operations (requires API key + user ID)
- **Exports**: CSV export endpoints for tickets and FAQ

**Note for Mind Dashboard**: Mind primarily uses:
- `/api/dashboard/metrics` (or `/api/metrics` alias) for live metrics
- `/api/health` for health checks
- Dashboard configuration endpoints for web UI management

## Authentication

Most endpoints require authentication via:
- **API Key**: Pass in `X-API-Key` header
- **User ID**: Pass in `X-User-Id` header (for user-specific endpoints)

Example:
```bash
curl -H "X-API-Key: your_api_key" -H "X-User-Id: 123456789" \
  https://your-bot-url/api/reminders/123456789
```

## Endpoints

### Health & Status

#### `GET /api/health`

Enhanced health check endpoint with detailed metrics.

**Response:**
```json
{
  "service": "alphapy",
  "version": "2.1.0",
  "uptime_seconds": 3600,
  "db_status": "ok",
  "timestamp": "2026-01-21T12:00:00Z",
  "guild_count": 2,
  "active_commands_24h": 150,
  "gpt_status": "operational",
  "database_pool_size": 5
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
- `gpt_status`: GPT service status (`operational`, `degraded`, `error`) (optional)
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
      "version": "2.1.0",
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

Comprehensive dashboard metrics including bot status, GPT stats, reminders, tickets, and command usage.

**Authentication:** Required (Supabase JWT token)

**Query Parameters:**
- `guild_id` (optional): Filter metrics by guild ID

**Response:**
```json
{
  "bot": {
    "version": "2.1.0",
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
  }
}
```

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
    "log_channel_id": "123456789",
    "rules_channel_id": "987654321"
  },
  "reminders": {
    "default_channel_id": "111222333",
    "allow_everyone_mentions": false
  },
  "embedwatcher": {
    "announcements_channel_id": "444555666"
  },
  "gpt": {
    "model": "grok-3",
    "temperature": 0.7
  },
  "invites": {},
  "gdpr": {}
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

**Authentication:** Required (Supabase JWT token)

**Request Body:** Same structure as GET response

#### `DELETE /api/dashboard/{guild_id}/onboarding/questions/{question_id}`

Delete an onboarding question.

**Authentication:** Required (Supabase JWT token)

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

**Authentication:** Required (Supabase JWT token)

#### `DELETE /api/dashboard/{guild_id}/onboarding/rules/{rule_id}`

Delete an onboarding rule.

**Authentication:** Required (Supabase JWT token)

#### `POST /api/dashboard/{guild_id}/onboarding/reorder`

Reorder onboarding questions and rules.

**Authentication:** Required (Supabase JWT token)

**Request Body:**
```json
{
  "questions": [1, 3, 2],
  "rules": [2, 1]
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

#### `GET /export_tickets`

Export tickets as CSV.

**Authentication:** Required (API key)

**Response:** CSV file download

#### `GET /export_faq`

Export FAQ entries as CSV.

**Authentication:** Required (API key)

**Response:** CSV file download

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

Current API version: **2.1.0** (Lifecycle Manager)

Version information is included in health check responses and can be queried via `/api/health`.
