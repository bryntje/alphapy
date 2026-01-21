# Changelog

All notable changes to this project will be documented in this file.

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
