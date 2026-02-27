# AGENTS.md

## 🧠 Innersync • Alphapy Bot – AI Agent Manifest

This document describes the active AI agents and modular features of the Innersync • Alphapy Discord Bot.

### Codebase language: English only (no Dutch/NL)

**The entire codebase is in English.** Do not introduce Dutch in:
- Source code, comments, docstrings
- User-facing strings (embeds, buttons, commands, error messages)
- Log messages and operational logs

This applies even when the user speaks Dutch in chat or in instructions. Keep all code, comments, and in-app text in English. Exceptions: display labels that are intentionally in another language (e.g. language names like "Nederlands", "Español" in onboarding options) are allowed.

---

## 📣 Agent: EmbedReminderWatcher

- **Path**: `cogs/embed_watcher.py`
- **Purpose**: Detects new embeds in the announcements channel and automatically creates reminders.
- **Triggers**: `on_message` → embed parsing
- **Storage**: PostgreSQL (reminders table)
- **Special parsing**: Title, time, days, location via NLP
- **Helper function**: `parse_embed_for_reminder()`
- **Reminder name**: Short title for the reminder (max ~50 chars) via `_short_title_for_reminder_name()` – first line of the description or first part of the title, so the sent reminder embed has a clear title instead of the full embed text.
- **Message formatting**: For a single long text block, `_format_message_paragraphs()` adds paragraph breaks after sentences and splits timezones ("3 PM EST | 8 PM UK") across lines with bullets for a more readable description.
- **Logging**: Guild log channel (`system.log_channel_id`); log embeds use `safe_embed_text(..., 1024)` for field values (Discord limit).
- **Dependencies**: `discord.py`, `asyncpg`, `spaCy` (optional)
- **Known Issues**: Timezone parsing is critical; NLP requires correct embed structure.

---

## 🧾 Agent: ReminderManager

- **Path**: `cogs/reminders.py`
- **Purpose**: Slash commands for manually adding and managing reminders.
- **Commands**:
 - `/add_reminder` – add reminder (manual or via message link)
 - `/reminder_list` – view active reminders
 - `/reminder_edit` – edit reminder via modal
 - `/reminder_delete` – delete reminder
- **Interaction**: Uses the same parser as `EmbedReminderWatcher`.
- **Sent embeds**: Reminder title truncated to 240 chars (Discord limit); Location field limited to 1024 chars for embed field values.

---

## 🚀 Agent: GrokInteraction

- **Purpose**: AI functionality with Grok.
- **Commands**:
 - `/create_caption` – generate caption
 - `/learn_topic` – explanation of a topic
 - `/gptstatus` – Grok/LLM API status

---

## 🌱 Agent: GrowthCheckIn

- **Purpose**: Guides personal growth of community members via Grok.
- **Command**:
 - `/growthcheckin`
- **Logging**: Storage of answers for processing or follow-up.
- **Premium**: Premium users get Mockingbird spicy mode (direct, sharp, challenge assumptions) in the reply.

---

## ⚡ Agent: Premium

- **Path**: `cogs/premium.py`, `utils/premium_guard.py`
- **Purpose**: Premium tier UX and access control. Guard used by reminders (images), growthcheckin (spicy), embed watcher, onboarding.
- **Model**: One active subscription per user, applied to one guild. User can move it via `/premium_transfer` (or later dashboard).
- **Commands**:
 - `/premium` – pricing embed, "how it works" (one server, pay once, transfer later), checkout button (or "Coming soon" if no URL)
 - `/premium_check` – (Admin) check if a user has premium in this guild
 - `/my_premium` – check your own Premium status and expiry in this server
 - `/premium_transfer` – move your Premium to this server (local DB only; when Core-API is source of truth, use dashboard)
- **Guard**: `utils/premium_guard.is_premium(user_id, guild_id)` – Core-API `/premium/verify` when configured, else local `premium_subs` table; in-memory cache with TTL. `premium_required_message(feature_name)` for gated-feature replies. `transfer_premium_to_guild(user_id, guild_id)` and `get_active_premium_guild(user_id)` for transfer (local DB).

---

## 🔐 Agent: GDPRHandler

- **Purpose**: Support for data rights.
- **Command**:
 - `/export_onboarding` – exports onboarding data as CSV
- **Future**:
 - `/delete_my_data` (not yet implemented)

---

## 🧮 Agent: InviteTracker

- **Purpose**: Tracks Discord invites per user.
- **Commands**:
 - `/inviteleaderboard`
 - `/setinvites`
 - `/resetinvites`

---

## 📜 Agent: Onboarding

- **Path**: `cogs/onboarding.py`, `cogs/reaction_roles.py`, `cogs/configuration.py`
- **Purpose**: Configurable onboarding flow with rules and questions.
- **Setup wizard**: `/config start` – interactive server setup; the bot asks for each part whether a channel/role should be set (choose or skip). All prompts in English.
- **Commands** (via `/config onboarding`):
 - `show`, `enable`, `disable`, `set_mode` – status and mode
 - `add_question`, `delete_question`, `reset_questions` – manage questions
 - `add_rule` – add rule (optional `thumbnail_url`, `image_url`)
 - `delete_rule`, `reset_rules` – manage rules
 - `set_role`, `reset_role` – completion role
 - `panel_post` – post onboarding panel with Start button
 - `reorder` – change order of questions
- **Rules**: No default rules; admins must configure rules. When no rules: error message to user and log to log channel.
- **Images**: Rules can have `thumbnail_url` (right/top) and/or `image_url` (bottom).
- **Personalization (synthetic steps)**: After guild questions, two fixed steps: (1) opt-in for personalized reminders ("Yes, please!" / "Only for events and sessions" / "No, thanks"), (2) for full/events_only a language question (Nederlands, English, Español, etc., or "Other language…" with free input). Answers stored in `onboarding.responses` as `personalized_opt_in` and `preferred_language`.
- **Helper**: `get_user_personalization(user_id, guild_id)` on the Onboarding cog – returns `{"opt_in": "full"|"events_only"|"no"|None, "language": str}` from the latest onboarding; graceful fallback to `{"opt_in": None, "language": "en"}`. Call from other cogs via `bot.get_cog("Onboarding")` then `await cog.get_user_personalization(...)`.
- **Logging**: `system.log_channel_id` for onboarding logs and "no rules" warnings.
- **API**: Dashboard endpoints for questions and rules (`/api/dashboard/{guild_id}/onboarding/*`).

---

## 🔄 Agent: UtilityAdmin

- **Purpose**: Supporting tasks.
- **Commands**:
 - `/clean` – delete messages
 - `/sendto` – send message to specific channel
 - `/reload` – reload an extension

---

## 💡 Contextual FYI tips

- **Path**: `utils/fyi_tips.py`
- **Purpose**: Sends short, context-sensitive tips when certain first-time events occur per guild (e.g. first onboarding completed, first reminder, first ticket, bot joins server). Tips are sent at most once per guild per type; a per-guild 24h cooldown prevents spam when multiple first-time events happen in one day.
- **Storage**: `bot_settings` (scope `fyi`), keys with prefix `first_*` (e.g. `first_onboarding_done`, `first_guild_join`). Copy and logic in `utils/fyi_tips.py`. Only scope `fyi` is used; `SettingsService.get_raw` / `set_raw` / `clear_raw` accept only scope `fyi` and log on failure (`RAW_GET_FAILED`, `RAW_SET_FAILED`, `RAW_CLEAR_FAILED`).
- **Phase 1 (live)**: `first_guild_join`, `first_onboarding_done`, `first_config_wizard_complete`, `first_reminder`, `first_ticket`. Phase 2 triggers (e.g. watcher, Grok, invites, growth, add_rule) can be enabled later.
- **Admin/testing**: `/config fyi reset <key>` and `/config fyi send <key>` (admin-only, `validate_admin`). Reset clears the flag so the next natural trigger sends the FYI again; send forces delivery to the log channel.

---

## 🌐 API Agent: FastAPI Dashboard Endpoint

- **Path**: `api.py`
- **Purpose**: Exposes reminders and realtime metrics for dashboards.
- **Endpoints**:
 - `/api/reminders/*` – CRUD for user reminders (API key + `X-User-Id`)
 - `/api/dashboard/metrics` – live bot status, Grok/LLM log stats, reminder and ticket counts
 - `/api/dashboard/logs` – operational logs with guild-admin check
- **Helpers**: `utils/runtime_metrics.get_bot_snapshot()` provides safe cross-thread snapshots from Discord.
- **Operational Logs**: In-memory buffer (`utils/operational_logs.py`) with max 100 events
 - **Event Types**:
   - `BOT_READY` – Bot startup complete
   - `BOT_DISCONNECT` – Bot disconnected from Discord
   - `BOT_RECONNECT` – Bot reconnected and resynced commands
   - `GUILD_SYNC` – Command sync per guild (success/failure/cooldown)
   - `ONBOARDING_ERROR` – Onboarding errors (no rules, role assignment fails)
   - `SETTINGS_CHANGED` – Settings changes via commands or API
   - `COG_ERROR` – Slash command errors per guild
 - **Filtering**: Guild-specific with admin access control via Supabase JWT
 - **Implementation**: Top-level imports in all modules for optimal performance; consistent error handling and logging patterns

---

## 📊 Agent: Telemetry Ingest Background Job

- **Path**: `api.py` (`_telemetry_ingest_loop()`)
- **Purpose**: Automatic periodic telemetry data ingest to Supabase for Mind dashboard.
- **Functionality**:
 - Runs continuously as background task in FastAPI lifespan
 - Collects metrics every 30–60 seconds (configurable via `TELEMETRY_INGEST_INTERVAL`)
 - Writes to `telemetry.subsystem_snapshots` with subsystem='alphapy'
 - Collects: bot status, uptime, latency, throughput, error rate, queue depth, active bots
 - Graceful error handling: errors are logged but do not stop the task
- **Configuration**:
 - `TELEMETRY_INGEST_INTERVAL` (default: 45 seconds) in `config.py`
- **Logging**: Info on start, debug on successful ingest, warning on errors
- **Known Issues**: None – task starts automatically on API server startup and stops correctly on shutdown

---

## 🔐 Agent: GCP Secret Manager Utility

- **Path**: `utils/gcp_secrets.py`
- **Purpose**: Secure access to secrets in Google Cloud Secret Manager with caching and fallback to environment variables.
- **Functionality**:
 - `get_secret()`: Fetches secrets from Secret Manager or environment variable (priority: cache → Secret Manager → env var)
 - `clear_cache()`: Removes cached secrets (for rotation/testing)
 - In-memory caching with TTL (1 hour) to minimize Secret Manager calls
 - Graceful fallback to environment variables for local development
- **Configuration**:
 - `GOOGLE_PROJECT_ID`: GCP project ID for Secret Manager access
 - `GOOGLE_SECRET_NAME`: Name of the secret in Secret Manager (default: "alphapy-google-credentials")
 - `GOOGLE_CREDENTIALS_JSON`: Fallback environment variable for local development
- **Usage**:
 - `utils/drive_sync.py` uses Secret Manager for Google Drive service account credentials
 - Can be extended for other GCP secrets in the future
- **Security**:
 - No hardcoded credentials
 - Logging of which method is used (Secret Manager vs env var)
 - Error handling for Secret Manager failures
- **Dependencies**: `google-cloud-secret-manager>=2.16.0`
- **Known Issues**: None

---

## 🎨 Embed Styling Guide

### Informative Embeds – Uniform style

All informative embeds (e.g. `/reminder_list`, `/command_stats`, `/gptstatus`) must follow a uniform style for consistency and professionalism.

#### Basic structure

```python
embed = discord.Embed(
    title="📋 [Title with emoji]",
    description="[Short description or summary]",
    color=discord.Color.blue(),  # See colors below
    timestamp=datetime.now(BRUSSELS_TZ)  # Always timestamp for context
)
```

#### Colors

Use the following colors for different types of information:

- **Blue (`discord.Color.blue()`)**: Default informative embeds
  - Examples: `/reminder_list`, `/command_stats`, general information
- **Orange (`discord.Color.orange()`)**: Warnings or empty states
  - Examples: "No reminders found", "No commands executed"
- **Green (`discord.Color.green()`)**: Successful actions or positive status
  - Examples: Successful operations, "All systems operational"
- **Red (`discord.Color.red()`)**: Errors or critical warnings
  - Examples: Errors, failed operations
- **Teal (`discord.Color.teal()`)**: Status information
  - Examples: `/gptstatus` (Grok/LLM status), system status

#### Fields

- **Use emojis for visual hierarchy**: `📅`, `⏰`, `📍`, `📺`, `🔄`, `📌`, etc.
- **Field names**: Short and descriptive with emoji prefix
  - Good: `📅 Period`, `🔄 Recurring (5)`, `📌 One-off (2)`
  - Avoid: `Period:`, `Recurring reminders:`
- **Field values**:
  - Use `\n` for multiple items
  - Format: `**Item Name**\nDetails...`
  - For lists: numbering with `1.`, `2.`, etc. or bullets with `•`
- **Inline fields**: Use `inline=True` for related information that can sit side by side (max 3 per row)

#### Footer

Always include a footer with:
- Version info: `f"v{__version__} — {CODENAME}"`
- Or action hints: `"Use /reminder_edit <id> to edit or /reminder_delete <id> to delete"`
- Or module identification: `f"reminders | Guild: {guild_id}"`

#### Examples

**Reminder List:**
```python
embed = discord.Embed(
    title="📋 Active Reminders",
    description=f"Found **{len(rows)}** reminder{'s' if len(rows) != 1 else ''}",
    color=discord.Color.blue(),
    timestamp=datetime.now(BRUSSELS_TZ)
)
embed.add_field(
    name=f"🔄 Recurring ({len(recurring)})",
    value="\n\n".join(formatted_reminders),
    inline=False
)
embed.set_footer(text="Use /reminder_edit <id> to edit or /reminder_delete <id> to delete")
```

**Command Statistics:**
```python
embed = discord.Embed(
    title="📊 Command Usage Statistics",
    color=discord.Color.blue(),
    timestamp=datetime.now(BRUSSELS_TZ)
)
embed.add_field(name="📅 Period", value=f"Last {days} day{'s' if days != 1 else ''}", inline=True)
embed.add_field(name="🌐 Scope", value=scope_text, inline=True)
embed.set_footer(text=f"v{__version__} — {CODENAME}")
```

#### Best practices

1. **Consistency**: Always use the same emojis for the same concepts
   - ⏰ for time
   - 📅 for dates/days
   - 📍 for locations
   - 📺 for channels
   - 🔄 for recurring items
   - 📌 for one-off items

2. **Readability**:
   - Use `**bold**` for important information
   - Use `\n` for clear separation between items
   - Limit field values to max 1024 characters (Discord limit)

3. **Context**:
   - Always add timestamp for time-sensitive information
   - Footer with relevant actions or version info

4. **Empty states**:
   - Use orange color for "no results" states
   - Clear description: "No reminders found." instead of empty fields

5. **Grouping**:
   - Group related information in fields
   - Use section headers with counts: `🔄 Recurring (5)`

---

## Database Architecture

### Connection Pools

All database operations use `asyncpg` connection pools for better concurrency and resource management:

- **FastAPI (`api.py`)**: Main pool for API endpoints
- **Command Tracker**: Dedicated pool in bot's event loop (min_size=1, max_size=5)
- **Reminders Cog**: Pool for reminder operations (max_size=10)
- **Ticket Bot**: Pool for ticket operations (max_size=10)
- **FAQ Cog**: Pool for FAQ operations (max_size=5)
- **Embed Watcher**: Pool for embed parsing (max_size=10)
- **Premium Guard** (`utils/premium_guard.py`): Dedicated pool for premium_subs lookups (min_size=1, max_size=5); registered for cleanup via `db_helpers.close_all_pools`

All pools include:
- Connection timeout handling
- Graceful shutdown on cog unload
- Error handling for connection failures
- Pool status checks for operations

### Command Tracking

- **Automatic tracking**: All command executions are tracked via event handlers in `bot.py`
- **Persistence**: Data is stored in the `audit_logs` table
- **Event loop isolation**: Command tracker uses its own pool in the bot's event loop to avoid conflicts
- **Initialization**: Initialized in the `on_ready()` event handler; keeps working after restarts
