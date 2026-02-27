# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- **Premium**: `premium_required_message(feature_name)` now includes the feature name in the message so users see which feature requires upgrade (e.g. "Reminders with images is premium. Mature enough? Get power with /premium.").

### Improved
- **.gitignore**: Added `.venv/` so the alternate venv folder is not tracked.

---

## [2.4.0] - 2026-02-26

### Added
- **Premium tier**
  - New table `premium_subs` (Alembic 003) for local subscription status; GDPR: only access-control fields (user_id, guild_id, tier, status, optional stripe_subscription_id, expires_at, created_at). Migration 004 adds `image_url` to `reminders`.
  - `utils/premium_guard.py`: `is_premium(user_id, guild_id)` with optional Core-API `POST /premium/verify`, local DB fallback, in-memory cache (TTL configurable via `PREMIUM_CACHE_TTL_SECONDS`). `premium_required_message(feature_name)` for gated-feature replies (Mockingbird tone).
  - **Commands**: `/premium` – pricing embed (€4.99/mo, €29/year, €49 lifetime) and checkout button (or "Coming soon"); `/premium_check` (admin), `/my_premium`, `/premium_transfer` – move Premium to this server.
  - **Gates**: Reminders with image URL or attachment require premium; embed watcher stores image on reminders only when message author is premium; growthcheckin gets Mockingbird spicy mode (direct, sharp) for premium users.
  - **Onboarding**: Completion summary shows "Premium" field for premium users; non-premium users see "Upgrade to Premium" button when `PREMIUM_CHECKOUT_URL` is set.
  - **One server per subscription + transfer**: Migration 005 adds partial unique index on `premium_subs (user_id) WHERE status = 'active'`; `transfer_premium_to_guild` and `get_active_premium_guild` in premium_guard; `/premium` embed includes "How it works" (one server, pay once → choose server, switch later via command or dashboard).
  - Config: `PREMIUM_CHECKOUT_URL`, `PREMIUM_CACHE_TTL_SECONDS`. Docs: `docs/premium.md`, `docs/database-schema.md` (premium_subs), `docs/configuration.md`, AGENTS.md (Agent: Premium). Tests: `tests/test_premium_guard.py`.
- **Contextual FYI tips**
  - Short, contextual tips sent when certain first-time events happen per guild (e.g. first onboarding completed, first reminder, first ticket, bot joined server). Each tip is sent at most once per guild per type; per-guild 24h cooldown prevents spam when multiple first-time events occur in one day.
  - Phase 1 triggers: `first_guild_join` (welcome in system/first channel), `first_onboarding_done`, `first_config_wizard_complete`, `first_reminder`, `first_ticket`. Tips are sent to the log channel (or fallback channel on guild join). Copy and logic in `utils/fyi_tips.py`; state in `bot_settings` (scope `fyi`, keys `first_*`).
  - Admin/testing: `/config fyi reset <key>` and `/config fyi send <key>` (admin-only) to clear a flag or force-send a tip. `SettingsService.get_raw` / `set_raw` / `clear_raw` support internal fyi flags (scope `fyi` only; failures logged).
  - Tests: `tests/test_fyi_tips.py` (23 tests) for `_parse_last_sent`, `_build_fyi_embed`, `send_fyi_if_first` (unknown key, no get_raw, already sent, cooldown, send-and-mark), `force_send_fyi`, and `reset_fyi`.
- **Onboarding: personalization opt-in and language**
  - After guild questions, two fixed steps: (1) opt-in for personalized reminders (“Yes, please!” / “Only for events and sessions” / “No, thanks”), (2) if full or events_only, preferred language (Nederlands, English, Español, etc., or “Other language…” with free text). Stored in `onboarding.responses` as `personalized_opt_in` and `preferred_language`.
  - Helper `get_user_personalization(user_id, guild_id)` on Onboarding cog for use by reminders or other cogs; returns `{"opt_in", "language"}` with graceful fallback when no record or DB unavailable.
- **AGENTS.md: codebase language** – Explicit note that the entire codebase is English-only (no Dutch in code, comments, user-facing strings, or logs), even when the user communicates in Dutch.

### Changed
- **AI branding: GPT → Grok** – User-facing and documentation references updated from "GPT" to "Grok" (or "Grok/LLM" where generic): AGENTS.md (GPTInteraction → GrokInteraction, status/telemetry wording), `bot.py` setting descriptions, `gpt/` helpers and context loader, cogs (learn, leadership, contentgen, growth, ticketbot), docs (commands, configuration, api, privacy, README, ROADMAP), and `api.py` (health, telemetry, status logic). Command and config names (e.g. `/config gpt`, `gptstatus`) unchanged; only labels, comments, and docs updated.

### Documentation
- **changelog.md** – Unreleased section updated to include `bot.py` English-only changes (setting descriptions, comments, reconnect log).
- **docs/code-review-config-start.md** – Removed; it was a local review checklist for the `/config start` wizard and is no longer needed in the repository.
- **docs/configuration.md** – Invite template example uses English variant label "With inviter" instead of "Met inviter".

### Fixed
- **Embed watcher reminder title and description**
  - Short reminder name (~50 chars) derived from first line of description or start of title so the sent reminder embed has a clear title instead of the full announcement text.
  - When the stored message is one long block, paragraph breaks are added after sentences and time zones (“3 PM EST | 8 PM UK”) are split onto separate lines with bullets for a readable description.
- **Reminders: sent embed title** – Display title truncated to 240 chars so older reminders with long names stay within Discord’s embed title limit.
- **Embed watcher & reminders: embed safety** – Log embeds use `safe_embed_text(..., 1024)` for Title and Location fields; reminder Location field uses 1024-char limit for Discord field values.

### Improved
- **Codebase: English only** – Dutch comments and log messages in `cogs/onboarding.py`, `cogs/reminders.py`, and `bot.py` translated to English; all setting definitions in `bot.py` (log channel, embed watcher, reminders, invites, GDPR, ticket escalation, etc.) now use English descriptions; reconnect log message simplified; `core-api/` directory removed (deprecated README only).
- **Onboarding** – Uses `utils.logger`; personalization summary/log fields use human-readable labels and 1024-char truncation; footer on personalization step embeds; expanded `get_user_personalization` docstring.
- **Onboarding: single message flow** – Reaction roles: no defer before `send_next_question` on “Accept All Rules & Start Onboarding” so the rules message can be replaced with the first question via `response.edit_message`. Onboarding `_show_onboarding_step`: when response is already used, try `edit_original_response(embed=..., view=...)` before `followup.send` to reduce extra messages. Session is optional and used safely (e.g. `session.get("onboarding_message")` only when session is not None).
- **Onboarding: no text above embed** – Rules message is embed + view only (no “Please accept each rule one by one before proceeding:”). Every onboarding edit (`response.edit_message`, `msg.edit`, `edit_original_response`, completion-edit) passes `content=""` so existing text above the embed is cleared.
- **Onboarding: completion behavior** – On completion, both `interaction.message` and `session["onboarding_message"]` are edited to the “Onboarding complete” embed with `view=None` so buttons/dropdown disappear. If the user clicks opt-in or language after completion, reply is “Onboarding is already complete. Your preferences were saved.” (PersonalizationOptInView, PersonalizationLanguageView, OtherLanguageModal).

---

## [2.3.0] - 2026-02-14

### Added
- **`/config start` – interactive server setup wizard**
  - Step-by-step setup for main settings: log channel, rules channel, onboarding channel, embed watcher, invites, GDPR, ticket category, staff role
  - Per step: choose channel or role via Discord ChannelSelect/RoleSelect, or click Skip
  - All prompts in English; 5-minute timeout; same-user check; audit log and debug logging
  - `SetupWizardView` and `SETUP_STEPS` in `cogs/configuration.py`; tests in `tests/test_config_start_wizard.py`

### Documentation
- **Config start wizard:** `docs/configuration.md` quick start, `docs/commands.md` and `AGENTS.md` (Onboarding) updated; `docs/code-review-config-start.md` added for review checklist.

### Fixed
- **Python 3.12:** Upgraded Docker image from Python 3.9 to 3.12 to resolve Google library FutureWarnings (Python 3.9 is EOL; google-auth, google-api-core, google-cloud-secretmanager require 3.10+).

---

## [2.2.0] - 2026-02-11

### Added
- **API operational logs for Mind dashboard**
  - New endpoint `GET /api/dashboard/logs` exposing operational events with guild-specific filtering
  - Event types: `BOT_READY`, `BOT_RECONNECT`, `BOT_DISCONNECT`, `GUILD_SYNC`, `ONBOARDING_ERROR`, `SETTINGS_CHANGED`, `COG_ERROR`
  - Guild admin verification via Supabase profile's Discord ID (requires linked Discord account)
  - In-memory buffer `utils/operational_logs.py` with `log_operational_event()`
  - Instrumented in: `bot.py`, `utils/lifecycle.py`, `cogs/onboarding.py`, `cogs/reaction_roles.py`, `utils/settings_service.py`, `api.py`
  - Helper `get_discord_id_for_user()` in `utils/supabase_client.py` for admin check
- **Guild-specific operational events**
  - `GUILD_SYNC`: Command sync per guild (startup/reconnect/guild_join) with success/failure/cooldown tracking
  - `ONBOARDING_ERROR`: No rules configured, role assignment failures, member resolution failures
  - `SETTINGS_CHANGED`: Settings updates via commands or API (set/clear/bulk_update/rollback)
  - `COG_ERROR`: Slash command errors with command name, user ID, and error details
- **Onboarding rules: image support**
  - Rules can have a thumbnail (right/top-right) and/or an image (bottom)
  - `/config onboarding add_rule` now accepts optional `thumbnail_url` and `image_url`
  - Dashboard API: `OnboardingRule` model extended with `thumbnail_url` and `image_url`
  - Database: `guild_rules` table gets `thumbnail_url` and `image_url` columns (auto-migration on startup)
- **Onboarding: no default rules**
  - When no rules are configured, users see an error and admins get a log in the configured log channel
  - Rules must be explicitly configured per guild via `/config onboarding add_rule`
- **README restructure:** Shorter README with clear sections; Operational Playbook moved to `docs/OPERATIONAL_PLAYBOOK.md` with checklist and verification steps.

### Documentation
- **Google credentials docs:** Translated `GOOGLE_CREDENTIALS_SETUP.md`, `RAILWAY_SECRET_MANAGER_SETUP.md`, and `SECURITY.md` from Dutch to English.
- **Onboarding:** `docs/configuration.md` Onboarding scope with add_rule/delete_rule/reset_rules/set_role/reset_role and image parameters.
- **AGENTS.md:** New Onboarding agent section (rules, images, no default rules, logging).
- **ARCHITECTURE.md:** Onboarding updates (no default rules, guild_rules images, fetch_member for completion role).

### Fixed
- **BOT_READY vs BOT_RECONNECT:** `_mark_startup_complete()` was called at end of `startup()` in `setup_hook()`, which runs before Discord connection. When `on_ready()` fired, `is_first_startup()` already returned False, causing first startup to be logged as BOT_RECONNECT instead of BOT_READY and triggering redundant reconnect syncs (2× API calls per deploy, contributing to Discord rate limits). Fixed by moving `_mark_startup_complete()` to `on_ready()` when handling first startup.
- **Duplicate on_ready guard:** Discord.py can fire `on_ready()` multiple times during a single session (reconnects, RESUME failures). A second call after the first would see `_first_startup == False` and incorrectly run `reconnect_phase`. Now only runs reconnect phase when `on_disconnect` was seen beforehand, via `set_disconnect_seen()` / `consume_disconnect_seen()`.
- **EventType import:** Added missing `EventType` import to `bot.py` and `utils/lifecycle.py` to fix NameError at runtime when operational events are logged.
- **Tests:** MockSettingsService.get() accepts fallback param; url_filter avoids variable-width lookbehind (Python re); safe_prompt catches "forget all previous instructions"; safe_embed_text now filters URLs.
- **Code review fixes (API, guild admin):** Cap `limit` in `GET /api/dashboard/logs` to 100; cache `application_info` (60s TTL) in guild admin check; shared `utils/guild_admin.member_has_admin_in_guild()`; replace 9× `print()` with `logger.error()` in `api.py`.
- **Onboarding completion role:** Robust member resolution using `interaction.user` or `fetch_member()` so new members (not in cache) receive the completion role correctly.
- **`/learn_topic`:** Keep-alive during GPT call (edit every 10s) and reply via `edit_original_response` to avoid Discord interaction timeout when GPT latency is high (~20s+).
- **Onboarding DATABASE_URL:** Type-safe guard before pool creation.

### Improved
- **Import optimization:** All operational log imports moved to top-level (11 inline imports removed) for better performance and code consistency across `bot.py`, `cogs/onboarding.py`, `cogs/reaction_roles.py`, `utils/settings_service.py`, and `api.py`.
- **Error handling:** `bot.py` `on_app_command_error` now uses standard `exc_info=True` for proper traceback logging and eliminates duplicate variable assignments for cleaner code.
- **Code quality:** Refactored `on_app_command_error` to extract `guild_id` and `command_name` once at function start, improving readability and following DRY principle.
- **Type safety:** Added `EventType` enum to `utils/operational_logs.py` for type-safe event logging, preventing typos and providing self-documenting code. All operational log calls now use `EventType` enum values.
- **Security audit trail:** Admin access to guild-specific API endpoints now logged for compliance and security monitoring (`verify_guild_admin_access` logs successful access with user ID, Discord ID, and guild ID).
- **Event types validation:** `get_operational_events()` now validates `event_types` filter against known EventType values to prevent abuse; invalid types are filtered out; request with only invalid types returns empty result.

---

## [2.1.0] - 2026-02-09

### Added
- **Google Cloud Secret Manager Integration:**
  - New utility `utils/gcp_secrets.py` for secure secret management with caching and fallback
  - Google Drive credentials now load from Secret Manager in production (fallback to env var for local dev)
  - In-memory caching (1 hour TTL) to minimize Secret Manager API calls
  - New config variables: `GOOGLE_PROJECT_ID`, `GOOGLE_SECRET_NAME` (optional)
  - Security documentation: `docs/SECURITY.md` with Google Cloud best practices checklist
  - Tests: `tests/test_drive_sync.py` for Secret Manager integration and fallback behavior
- **Security Improvements:**
  - Migrated Google credentials from environment variables to Secret Manager (production)
  - Zero-code storage: credentials never committed to source code
  - Proper error handling and logging for Secret Manager operations
  - Documentation for infrastructure-level security configs (API restrictions, IAM, rotation policies)

### Fixed
- **GCP/Drive:** `get_secret()` env fallback uses `GOOGLE_CREDENTIALS_JSON` for default secret name; `get_secret(..., return_source=True)` and accurate logging in `drive_sync` (Secret Manager vs env); `_ensure_drive()` run via `asyncio.to_thread()` in lifecycle to avoid blocking event loop; thread-safe Drive init with `threading.Lock()`.
- Updated version references to 2.1.0 in documentation (`docs/api.md`, `docs/commands.md`); all API example responses in `docs/api.md` use version 2.1.0.


---

## [2.0.0] - 2026-01-22

### Added
- **Lifecycle Manager & Phased Startup/Shutdown:**
  - Centralized lifecycle management (`utils/lifecycle.py`) with `StartupManager` and `ShutdownManager` classes
  - Phased startup sequence: Database → Settings → Cogs → Command Sync → Background Tasks → Ready
  - Phased shutdown sequence: Cancel Tasks → Unload Cogs → Close Pools → Final Cleanup
  - Reconnect handling: Light resync phase for reconnects (only guild-only commands if intents missing) with humorous logging
  - Centralized database pool creation (`utils/db_helpers.create_db_pool()`) with automatic pool registry for cleanup
  - All cogs now use centralized pool creation (15 cogs updated: ticketbot, reminders, embed_watcher, faq, onboarding, dataquery, status, exports, inviteboard, gdpr, importdata, importinvite)
  - Proper dependency ordering: SettingsService initialized before cogs, cogs loaded before command sync
  - Graceful shutdown with complete resource cleanup (all pools, tasks, cogs)
  - Eliminates race conditions: Sequential phases ensure dependencies are ready before use
  - Better debugging: Phase-by-phase logging makes it clear where startup/shutdown fails
- **Startup/Shutdown Improvements:**
  - Fixed "Known guilds: 0" logging issue - guilds load after connect, now shows debug message if not yet available
  - Fixed python-dotenv warning about empty lines in .env file - warnings now suppressed (harmless trailing newlines)
  - Added shard ID logging - shows debug message for single-shard bots (normal), ready for future multi-shard support
- **Input Sanitization & Security:**
  - Centralized sanitization utility (`utils/sanitizer.py`) for protecting against injection attacks
  - `escape_markdown()`: Escapes Discord markdown characters to prevent injection
  - `strip_mentions()`: Removes user/role/channel mentions to prevent spam
  - `url_filter()`: Filters or sanitizes URLs to prevent exploits
  - `safe_embed_text()`: Combined sanitization for embed titles, descriptions, and fields (escapes markdown + strips mentions + truncates)
  - `safe_prompt()`: Blocks prompt injection/jailbreak attempts in GPT prompts with pattern detection
  - `safe_log_message()`: Sanitizes text for logging with length limits (max 200 chars) to prevent log spam
  - Applied sanitization to all user input flows:
    - Reminder messages (name, message, location) in embeds
    - Ticket descriptions and GPT-generated summaries
    - FAQ entries (title and summary fields)
    - Onboarding answers in summary and log embeds
    - GPT prompts in learn, leadership, growth, and contentgen commands
    - Embed text before sending to GPT for parsing
  - Comprehensive test suite (`tests/test_sanitizer.py`) with parametrized tests for:
    - Markdown injection attacks (15+ patterns)
    - Mention spam attempts
    - Prompt injection/jailbreak attempts (15+ patterns)
    - URL exploits
    - Length limit attacks
    - Edge cases (empty strings, control characters, unicode)
- **Memory Leak Fixes & Resource Management:**
  - Command tracker batching: In-memory queue (max 10k entries) with batch flush every 30s or at 1k entries threshold
  - Guild settings LRU cache: OrderedDict-based cache with max 500 entries and automatic eviction logging
  - IP rate limits cleanup: Periodic cleanup (every 10+ minutes) with max 1000 IP entries and LRU eviction
  - Command stats TTL cache: 30-second TTL cache with max 50 entries and automatic cleanup
  - Sync cooldowns cleanup: Periodic cleanup task (every 10 minutes) with max 500 entries
  - Ticket bot cooldowns cleanup: Max age (1 hour) cleanup on access with max 1000 entries
  - Cache size monitoring: New `CacheMetrics` model in dashboard metrics endpoint for monitoring all cache sizes
  - Size logging: All caches and dicts now log their size during cleanup operations
- **Command Tree Sync Refactoring:**
  - Centralized command sync utility (`utils/command_sync.py`) with cooldown protection
  - Automatic sync on bot startup (global commands once, then guild-only commands per guild)
  - Automatic sync when bot joins new guilds (`on_guild_join` handler)
  - Cooldown tracking: 60 minutes for global syncs, 30 minutes for per-guild syncs
  - Rate limit protection with graceful error handling and retry-after support
  - Parallel guild syncs for faster startup (multiple guilds synced simultaneously)
  - Guild-only command detection to optimize sync strategy
  - Manual sync command (`!sync`) with cooldown feedback and `--force` flag support
- **Rate Limiting & Abuse Prevention:**
  - Command cooldowns for high-risk operations:
    - `/add_reminder`: 5 per minute per guild+user (prevents reminder spam)
    - `/learn_topic`: 3 per minute per guild+user (cost control for GPT calls)
    - `/create_caption`: 3 per minute per guild+user (cost control for GPT calls)
    - `/growthcheckin`: 2 per 5 minutes per guild+user (growth check-ins are not frequent)
    - `/leaderhelp`: 3 per minute per guild+user (cost control for GPT calls)
  - In-memory cooldown for ticket "Suggest reply" button (5 seconds between clicks) with humorous error message
  - FastAPI IP-based rate limiting middleware:
    - 30 read requests per minute per IP
    - 10 write requests per minute per IP
    - Health/metrics endpoints excluded from rate limiting
    - Automatic cleanup of old rate limit entries

### Changed
- **Command Sync Architecture:**
  - Removed blocking `bot.tree.sync()` call from `cogs/dataquery.py` setup (was delaying startup by 30-60 seconds)
  - Command sync now happens in `on_ready()` hook after bot is fully initialized
  - Guild syncs run in parallel instead of sequentially for faster startup
  - Only guild-only commands are synced per-guild (not all commands, reducing API calls)
  - Manual sync command now uses centralized `safe_sync()` with proper error handling
- Rate limiting now protects against abuse and cost explosions for GPT-powered commands
- API endpoints now have IP-based rate limiting to prevent anonymous abuse

### Fixed
- **Documentation corrections:**
  - Removed non-existent slash commands `/ticket_list`, `/ticket_claim`, `/ticket_close` from docs (Claim/Close are buttons in ticket channel)
  - Corrected API reminders endpoint: `GET /api/reminders/{user_id}`, `PUT /api/reminders`, `DELETE /api/reminders/{reminder_id}/{created_by}`
  - Updated version references to 2.0.0 (Lifecycle Manager) in docs
  - Added missing `/commands` and `/leaderhelp` to docs/commands.md
  - Added `/reminder_edit` to AGENTS.md ReminderManager
  - Updated ARCHITECTURE.md and README.md ticket command listings

---

## [1.9.0] - 2026-01-21

### Added
- **Reminder Edit Command:** `/reminder_edit` command with modal interface for editing existing reminders
  - Edit name, time, days, message, and channel ID
  - Pre-fills modal with current reminder values including event time (T0)
  - Footer extraction from message field for cleaner editing experience
  - Channel ID editing support in modal
- **Embed Watcher Enhancements:**
  - Footer text extraction and inclusion in reminder parsing
  - Bot message processing toggle via `embedwatcher.process_bot_messages` setting
  - Rich Discord embed logging for reminder creation and parsing success/failure
  - Smart duplicate detection to prevent title/description overlap in reminder messages
  - Full day name display in logs (e.g., "Maandag" instead of "0")
  - One-off event weekday storage for informational display
- **GPT Retry Queue System:**
  - Automatic retry queue for rate-limited or failed GPT API requests
  - Exponential backoff retry mechanism
  - Fallback message for degraded AI service scenarios
  - Background task for processing queued requests
  - Graceful error handling that doesn't block user interactions
- **Command Usage Statistics:**
  - `/command_stats` Discord slash command for viewing command usage statistics (admin-only)
  - Filterable by time period (1-30 days) and scope (guild-specific or all servers)
  - Displays top commands and total command count
  - Persistent tracking across bot restarts
- **Database Connection Pool Architecture:**
  - All database operations now use `asyncpg` connection pools instead of direct connections
  - Improved concurrency and resource management
  - Each cog manages its own connection pool with appropriate size limits
  - Command tracker uses dedicated pool in bot's event loop to avoid event loop conflicts
  - Graceful error handling for connection errors (`ConnectionDoesNotExistError`, `InterfaceError`, `ConnectionResetError`)
  - Background tasks check pool status before operations and handle shutdown gracefully
- **Centralized Utility Modules:**
  - **`utils/db_helpers.py`**: Centralized database connection management
    - `acquire_safe()`: Async context manager for safe connection acquisition with error handling
    - `is_pool_healthy()`: Utility to check connection pool status before operations
    - Eliminates duplicate try/except blocks across all cogs
  - **`utils/validators.py`**: Centralized permission and ownership validation
    - `validate_admin()`: Unified admin/owner check replacing duplicate logic
    - Type-safe validation functions for consistent permission checks
  - **`utils/embed_builder.py`**: Consistent Discord embed creation
    - `EmbedBuilder` class with static methods: `info()`, `log()`, `warning()`, `success()`, `error()`, `status()`
    - Uniform styling with automatic timestamps and color coding
    - Reduces boilerplate embed creation code across all cogs
  - **`utils/settings_helpers.py`**: Cached settings wrapper
    - `CachedSettingsHelper`: Type-safe getters (`get_int()`, `get_bool()`, `get_str()`) with caching
    - `set_bulk()`: Batch settings updates for efficiency
    - Reduces repeated `SettingsService.get/put` calls with error handling
  - **`utils/parsers.py`**: Centralized string parsing utilities
    - `parse_days_string()`: Parse day strings (e.g., "ma,wo,vr") to day arrays
    - `parse_time_string()`: Parse time strings with timezone support
    - `format_days_for_display()`: Format day arrays for user-friendly display
    - Shared regex patterns and date functions used by embed watcher and reminders
  - **`utils/background_tasks.py`**: Robust background task management
    - `BackgroundTask` class: Manages asynchronous loops with graceful shutdown
    - Specific error handling for connection errors, pool shutdown, and Supabase edge cases
    - Replaces duplicate task loop setup code across cogs

### Changed
- **Internationalization:** All Dutch user-facing text replaced with English across all cogs
  - Command descriptions and parameter descriptions
  - Error messages and success notifications
  - Log messages and embed content
  - GPT system prompts
- **Logging Improvements:**
  - Converted plain text logs to structured Discord embeds for better readability
  - Reduced console verbosity by removing excessive debug statements
  - Enhanced log formatting with proper day names and structured fields
  - Improved command tracker error logging (warnings for table issues, debug for connection errors)
- **Message Content Handling:**
  - Smart duplicate detection prevents title/description overlap in reminder messages
  - Footer handling in embed watcher for consistent message formatting
  - Name field sanitization for Discord modal compliance (no newlines, max 100 chars)
- **Database Architecture:**
  - Migrated all cogs from direct `asyncpg.connect()` calls to connection pools
  - Improved connection lifecycle management with proper pool cleanup on cog unload
  - Enhanced error handling with connection status checks before operations
  - Telemetry ingest loop now checks pool status before database operations
  - Reminder loop checks pool status before fetching reminders
- **Code Refactoring & Boilerplate Removal:**
  - Refactored all cogs to use centralized utility modules, eliminating duplicate code
  - Replaced `async with pool.acquire()` patterns with `acquire_safe()` from `utils.db_helpers`
  - Replaced `is_owner_or_admin_interaction()` calls with `validate_admin()` from `utils.validators`
  - Replaced manual `discord.Embed()` construction with `EmbedBuilder` methods for consistency
  - Replaced direct `SettingsService.get/put` calls with `CachedSettingsHelper` where appropriate
  - Centralized parsing logic from embed watcher and reminders into `utils.parsers`
  - Standardized background task setup using `BackgroundTask` class
  - All cogs now use consistent error handling, embed styling, and database connection patterns

### Fixed
- **Reminder Edit Modal:**
  - Fixed `HTTPException: 400 Bad Request` error caused by newlines in name field
  - Corrected time display to show event time (T0) instead of reminder time (T-60)
  - Fixed message duplication issue when editing reminders
  - Resolved Discord modal field limit by optimizing field usage (removed footer field, kept channel ID)
- **Embed Watcher:**
  - Fixed footer not being stored correctly in reminders
  - Fixed one-off events missing weekday information
  - Fixed bot message processing loop protection
  - Improved parsing failure logging with detailed error information
  - Fixed `SyntaxError: invalid syntax` in `store_parsed_reminder()` method - logging code was incorrectly placed outside try/except block, causing orphaned except clause
- **GPT Integration:**
  - Fixed `RuntimeError: no running event loop` when starting retry queue task
  - Corrected linter error for `status_code` attribute access
  - Improved error handling for rate limits and API failures
- **Database Connection Issues:**
  - Fixed `ConnectionDoesNotExistError` errors caused by direct database connections
  - Resolved "Future exception was never retrieved" errors from background tasks
  - Fixed "attached to a different loop" error in command tracker by using bot's event loop
  - Improved error handling in telemetry ingest loop and reminder check loop
  - Fixed TicketBot setup database connection errors with proper async context management
  - Command tracker now correctly initializes in bot's event loop and persists across restarts

---

## [1.8.0] - 2025-12-17

### Added
- **Telemetry Ingest Background Job:** Automatic periodic telemetry data ingestion to Supabase
  - Background task runs every 30-60 seconds (configurable via `TELEMETRY_INGEST_INTERVAL`)
  - Continuously writes subsystem snapshots to `telemetry.subsystem_snapshots` table
  - Ensures Mind dashboard always has fresh data without requiring endpoint calls
  - Graceful error handling with automatic retry on failures
  - Comprehensive logging for monitoring and debugging
- **Configuration:** New `TELEMETRY_INGEST_INTERVAL` environment variable (default: 45 seconds)

### Changed
- **API Lifespan:** FastAPI lifespan context manager now starts background telemetry ingest task on startup
- **Telemetry Persistence:** `_persist_telemetry_snapshot()` now called automatically by background job instead of only on endpoint requests

### Fixed
- **Stale Dashboard Data:** Resolved issue where Mind dashboard showed "40+ days ago" due to missing telemetry updates
- **Data Freshness:** Telemetry data now updates continuously, ensuring dashboard always reflects current system state

---

## [1.7.0] - 2025-11-16

### Added
- **Complete Multi-Guild Support:** Guild isolation architecture allowing unlimited Discord servers with full data separation
- **Modular Onboarding System:** Configurable onboarding flows with custom questions, rules, and completion roles
- **Onboarding Panel Management:** `/config onboarding panel_post` command to place onboarding buttons in any channel
- **Advanced Question Types:** Support for select, multiselect, text, and email inputs with modal handling
- **Optional Field Support:** Users can skip optional questions like email addresses
- Database migration system with backup/restore capabilities (`backup_database.py`, `migrate_guild_settings.py`)
- Guild-aware settings service with per-server configuration overrides
- API security enhancements with optional `guild_id` filtering for dashboard endpoints
- Guild validation checks across all slash commands to prevent DM usage errors

### Changed
- **Database Schema:** Added `guild_id` columns to all tables (`reminders`, `support_tickets`, `invite_tracker`, `onboarding`, `bot_settings`) with composite primary keys
- **Code Architecture:** Updated all cogs with `interaction.guild.id` validation and type-safe implementations
- **Settings Service:** Enhanced to support guild-scoped configuration with zero pyright errors
- **API Endpoints:** Dashboard metrics now support guild filtering for security
- **Error Handling:** Comprehensive guild validation and duplicate record handling
- **Modal System:** Text input modals now support optional fields and different question types

### Fixed
- **Onboarding Flow:** Resolved crashes when processing email/text questions
- **Database Constraints:** Fixed duplicate key violations in onboarding records
- **Type Checking:** Eliminated all pyright errors across the codebase
- **Syntax Errors:** Fixed import and compilation issues
- **Modal Handling:** Added support for optional text input fields

### Security
- **Data Isolation:** Complete separation between guild data preventing cross-server leakage
- **API Security:** Dashboard endpoints now properly filter by guild context
- **Input Validation:** Guild existence checks prevent runtime errors in DM contexts
- **Migration Safety:** Backup verification and rollback capabilities

### Migration
- **Zero Downtime:** Database migration completed with full backup verification
- **Data Integrity:** All existing records successfully migrated with guild_id support
- **Backwards Compatibility:** Maintained for all existing functionality
- **Error Recovery:** Robust handling of migration edge cases and constraint conflicts

---

## [1.6.0] - 2025-10-17

### Added
- FastAPI dashboard endpoint `/api/dashboard/metrics` exposing live bot telemetry, GPT usage stats, and reminder/ticket counts via new helper `utils/runtime_metrics`.
- Service health probe `/health` returning service name, version, uptime, timestamp, and database status (with live DB ping) for Railway/K8s checks.
- Supabase Auth support: automatische profiel bootstrap, gedeelde configuratievelden en client-side OAuth flows voor alle Innersync apps.
- Webhook endpoint `/webhooks/supabase/auth` voor Supabase Auth lifecycle events (met optionele HMAC validatie).

### Changed
- Project branding updated to **Innersync • Alphapy** across README, roadmap, architecture notes, manifests, Discord embeds, and runtime copy.
- Legal documentation (Terms of Service, Privacy Policy, configuration guide) and GitHub Pages metadata now reference the Innersync umbrella naming.
- Default CORS origins and base URL settings now align with the Innersync domain suite (`app|mind|alphapy.innersync.tech`) via `config.py`.
- Documentation (`README.md`, `ARCHITECTURE.md`, `AGENTS.md`, `ROADMAP.md`) updated with dashboard metrics details and cross-service health notes.
- Supabase JWT-validatie hit nu rechtstreeks Supabase `/auth/v1/user` via `httpx`, waarbij `PyJWT` als dependency blijft voor toekomstige lokale verificatie.
- `requirements.txt` omvat `PyJWT[crypto]` en `httpx` voor Supabase token verificatie.

---

## [1.5.0] - 2025-10-04

### Added
- Runtime configuratie: GPT-, reminders-, invites- en GDPR-instellingen worden via SettingsService beheerd en `/config`-subcommands (audit logging).
- Invitetracker met enable-toggle, kanaaloverride en aanpasbare templates; reminders met standaardkanaal, @everyone-toggle en disable-optie.
- GDPR-post en “I Agree”-knop volgen runtime settings; `/health` slashcommand toont DB/feature status.
- Documentatie (`docs/configuration.md`) en pytest voor SettingsService.

### Changed
- Bot start faalt vroeg wanneer `BOT_TOKEN` ontbreekt; import-/slash-cogs gebruiken expliciete typeguards.

### Fixed
- Reminder scheduler gebruikt veilige reconnects (geen `None.execute`); import flows negeren ontbrekende embeds.

---

## [1.4.0] - 2025-09-13

### Added
- Phase 2 (TicketBot & FAQ)
  - FAQ module `/faq` with `search`, `view`, `list`, autocomplete, public toggle
  - Admin flows: `/faq add` (modal), `/faq edit` (prefilled modal)
  - Search scoring with simple normalization + synonyms
  - Ticket status workflows: Wait for user, Escalate buttons; `/ticket_status` admin command
  - AI assist: “💡 Suggest reply” button drafts an ephemeral response using GPT
  - Ticket statistics `/ticket_stats` with buttons (Last 7d / 30d / All / Refresh), versioned footer
  - Metrics persistence: `ticket_metrics` snapshots (scope, counts, avg_cycle_time, triggered_by)
  - Exports: `/export_tickets [scope]`, `/export_faq` (admin CSV exports)

### Changed
- Improved embeds and logging; status updates also write `updated_at`

### DB
- `support_tickets`: add `updated_at TIMESTAMPTZ`, `escalated_to BIGINT`
- `ticket_metrics`: structured fields (`scope`, `counts`, `average_cycle_time`, `triggered_by`) in addition to `snapshot`

---

## [1.3.0] - 2025-09-12

### Added
- TicketBot module:
  - `/ticket` command to create tickets with private channel per ticket
  - Interactive View in ticket channel with Claim/Close/Delete buttons (admin-gated)
  - GPT-generated summary on close; stored in `ticket_summaries`
  - Repeated-topic detection with proposal to add FAQ via button; `faq_entries` table
  - Admin command `/ticket_panel_post` to post a persistent “Create ticket” panel
  - Logging to `WATCHER_LOG_CHANNEL` for create/claim/close/delete
- Reminders: idempotency with `last_sent_at` to prevent duplicate sends per minute.
- Reminders: T0 support (event time) alongside T−60; one-offs dispatch twice by default.
- Reminders: richer logs to console and Discord `WATCHER_LOG_CHANNEL` (created/sent/deleted/errors).

### Changed
- Translated ticket UX to English and unified embeds/messages across flows
- Reminder scheduler SQL split logic consolidated to match T−60 (by date), T0, and recurring by `days`.
- Improved observability for reminder flow with structured info/debug messages.

### Fixed
- Avoid expression index error on reminders by using `event_time` index
- One-offs no longer become weekly due to weekday fallback; days remain empty for dated events.
- Embed watcher stores `event_time` (event) and `call_time` (display) correctly; `time` remains trigger time (T−60).

---

## [1.2.0] - 2025-09-09

### Added
- New onboarding flow (4 vragen) met follow-ups en e-mailvalidatie
- DRY `_value_to_label` en `_format_answer` voor embed rendering
- Reminder embed-link parsing + `call_time` ondersteuning
- `ANNOUNCEMENTS_CHANNEL_ID` in `config.py`

### Changed
- Onboarding multi-select: direct doorgaan na selectie (geen Confirm)
- Onboarding message-detectie: knop `custom_id="start_onboarding"`
- Env-gedreven configuratie, minder hardcoded waarden

### Fixed
- Tijdszoneconsistentie (`BRUSSELS_TZ`) in embed watcher en reminders
- Stabiliteit van parsing (fallbacks voor tijd/dagen/locatie)

---

## [1.1.0] - 2025-04-05

### Added
- `/growthcheckin` GPT reflection flow
- `/learn_topic` with context-aware PDF fetch
- `/create_caption` style-based content generator
- Google Drive integration via PyDrive2

### Changed
- Modular bot structure (`cogs/`, `gpt/`, `utils/`)
- Improved logging output and status embed

### Fixed
- Invite cache error on startup
- Duplicate onboarding message

---

## [1.0.0] - Initial Commit

- Discord bot scaffolding with onboarding
- Basic command structure
- PostgreSQL async onboarding logic
