# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **`/growthcheckin`**: Grok prompt now explicitly instructs the AI to reference past reflection patterns, recurring themes, and progress across sessions
- **`/growthcheckin`**: Optional community sharing via `GrowthShareView` — after the AI response, users can share anonymously, share with display name, or keep private; posts a styled embed (goal / obstacle / feeling / Grok response) to the configured growth channel
- **`/config growth set_channel [#channel]`**: Admin command to configure the growth check-in channel; omitting the channel argument opens a picker to select an existing channel or create a new `#growth-checkins` channel
- **`/config growth reset_channel`**: Removes the growth channel configuration
- **`growth.log_channel_id`**: New `SettingDefinition` registered in `bot.py`
- **Context loader**: Discord check-ins (Supabase `reflections` table) are now loaded as a third Grok context source alongside `reflections_shared` and `app_reflections`
- **`/growthhistory`**: New command — view your last 15 Growth Check-ins in a paginated embed (3 per page, Previous/Next navigation); select a check-in from the dropdown to see the full detail including Grok's reflection; delete individual check-ins with confirmation step

### Fixed
- **`/growthcheckin`**: Grok response length now controlled via prompt instruction (max 250 words) with `max_tokens=500` as API safety net — prevents mid-sentence cutoffs and Discord's 2000-char message limit errors
- **`ask_gpt`**: Added `max_tokens` parameter (propagated through retry queue) for callers that need response length control
- **Embed timestamps**: Replaced `datetime.utcnow()` with `datetime.now(timezone.utc)` in `gpt/helpers.py` — fixes 2-hour timezone display offset in Grok log embeds

---

## [3.2.0] - 2026-04-08

### Added
- **Premium system**: Full tier differentiation — free/monthly/yearly/lifetime tiers with GPT daily quotas (free: 5, monthly: 25, yearly/lifetime: unlimited), reminder limits (free: 10, others: unlimited), and ticket GPT summary gating (guild-level premium required)
- **Premium system**: `utils/premium_tiers.py` — central tier constants (`TIER_RANK`, `GPT_DAILY_LIMIT`, `REMINDER_LIMIT`)
- **Premium system**: `utils/premium_guard.py` — `get_user_tier()`, `user_has_tier()`, `check_and_increment_gpt_quota()` helpers; quota tracking in `gpt_usage` table
- **Premium system**: Expiry warning DMs — `check_expiry_warnings` background task sends a DM 7 days before premium expires; tracks `expiry_warning_sent_at` to avoid duplicates
- **Premium system**: `/my_premium` embed extended with tier badge, expiry countdown, GPT calls today (X/Y), and active reminder count (X/Y)
- **Premium system**: `/premium` embed now includes a feature comparison table and live early bird availability — checks `POST /billing/early-bird/validate` on Core-API (cached 5 min, fails open); buttons show early bird prices (Annual €29, Lifetime €49) while spots remain, regular prices (Annual €59.99, Lifetime €99.99) after sellout
- **DB migration 014**: `gpt_usage` table for per-user daily GPT call tracking
- **DB migration 015**: `expiry_warning_sent_at` column on `premium_subs`
- **Config**: `CORE_API_PAYMENTS_TOKEN`, `EARLY_BIRD_CODE`, `EARLY_BIRD_TOTAL_SPOTS`, `PRICE_MONTHLY`, `PRICE_YEARLY_EARLY_BIRD`, `PRICE_YEARLY_REGULAR`, `PRICE_LIFETIME_EARLY_BIRD`, `PRICE_LIFETIME_REGULAR` env vars
- **set_model / reset_model**: Restricted to bot owner only (billing protection); added optional `guild_id` parameter so the owner can set a per-guild model override without being a member of that guild
- **`/gptstatus`**: New **Rate limits (session)** field — tracks 429 hits since last restart, auto-detected from error type string (`429`, `rate limit`, `ratelimit`); shows count + time of last hit
- **`/gptstatus`**: New **Retry queue** field — live count of requests currently buffered in `_gpt_retry_queue` waiting to be retried after a rate limit or API error
- **`GPTStatusLogs`**: Added `rate_limit_hits` counter and `last_rate_limit_time` timestamp fields

### Changed
- **`/gptstatus`**: API health is now derived from own in-memory logs (last success age) instead of polling `status.openai.com` — which was wrong since the bot uses Grok (xAI), not OpenAI
- **`/gptstatus`**: Average latency is now a proper rolling average over the last 25 success events instead of overwriting with the last value each time
- **`/gptstatus`**: `total_tokens_today` renamed to `total_tokens_session` — clarifies the counter is in-memory and resets on restart; same rename in `api.py` (`GPTMetrics`) and `docs/api.md`
- **`/gptstatus`**: `rate_limit_reset` field removed — was always `"~"` and never tracked anywhere
- **`/gptstatus`**: `last_error_time` field added to embed and `GPTMetrics` API model; replaces the meaningless rate limit reset field
- **`/gptstatus`**: `last_user` field no longer renders as `<@->` or `<@None>` when no user has triggered Grok yet
- **`GPTStatusLogs`**: `success_events` and `error_events` deques are now populated in `gpt/helpers.py` — previously they were only populated in dead-code functions in `utils/logger.py` that were never called

### Fixed
- **Premium checkout buttons**: Fixed 404 error — bot was calling non-existent `POST /api/premium/checkout`; now reads `PREMIUM_CHECKOUT_URL` directly (no query params appended; pricing site handles tier selection)
- **GPT retry queue**: Initialise `_retry_lock` to `None` instead of a bare type annotation — fixes `NameError: name '_retry_lock' is not defined` raised on every retry queue task run

### Removed
- **`utils/logger.py`**: Dead `log_gpt_success` and `log_gpt_error` functions removed — all cogs import these from `gpt/helpers.py`; the `utils/logger.py` copies were never called

---

## [3.1.2] - 2026-04-05

### Performance
- **Premium guard**: Reuse a persistent `httpx.AsyncClient` for Core-API calls instead of opening a new TCP connection per cache miss; client is cleanly closed on shutdown
- **GPT retry queue**: Replaced serial per-item backoff with concurrent `asyncio.gather`; added `asyncio.Lock` to eliminate TOCTOU race — a full queue now drains in ~16s instead of ~25 minutes
- **GPT retry queue**: Fire-and-forget `create_task` calls in `log_gpt_success`/`log_gpt_error` are now tracked in a `_background_tasks` set so exceptions surface instead of being silently dropped
- **Settings**: `set_bulk` rewritten to use a single `acquire_transactional` + `executemany` — N sequential DB roundtrips reduced to 1 transaction
- **Premium guard**: `_stats_*` counters in `is_premium` now incremented under `_cache_lock` (thread-safety)

### Fixed
- **Onboarding**: Prevent `TypeError` when `view` is `None` on summary send — occurs when user is already premium or `PREMIUM_CHECKOUT_URL` is unset (#184)
- **Configuration**: Translate remaining Dutch error message ("Je hebt onvoldoende rechten voor dit commando.") to English (#185)
- **Settings**: Suppress `UNKNOWN_SETTING` log noise for `fyi.*` keys — these are intentionally stored via `set_raw` without a `SettingDefinition`
- **Migration 013**: Remove stale `bot_settings` rows leftover from renamed/removed settings (`embedwatcher.embed_watcher_offset_hours`, `guild.module_status`, `module_status.gdpr`, `system.onboarding_channel_id`)

---

## [3.1.1] - 2026-04-03

### Added
- **`AlphaCog` base class** (`utils/cog_base.py`): all cogs now extend `AlphaCog` which auto-wires `self.settings` and `self.settings_helper` in `__init__`, eliminating ~25 lines of boilerplate per cog
- **`acquire_transactional` context manager** (`utils/db_helpers.py`): atomic multi-step DB operations with automatic rollback on failure
- **API endpoint test suite** (`tests/test_api_endpoints.py`): 17 tests covering reminders CRUD, dashboard settings, and automod rules endpoints (auth, DB availability, admin access, and response shape)

### Changed
- **Codebase refactoring** — internal improvements, no breaking changes to slash commands or API:
  - Extracted embed date/text parsing into `utils/embed_parser.py` (testable, decoupled from the watcher cog)
  - Extracted all reminder SQL into `utils/reminder_repository.py` (repository pattern)
  - Split `cogs/configuration.py`: UI components moved to `cogs/configuration_ui.py`, automod helpers to `cogs/configuration_automod.py`
  - Migrated 9 cogs (`automod`, `configuration`, `embed_watcher`, `gdpr`, `inviteboard`, `join_roles`, `reminders`, `ticketbot`, `verification`) to `AlphaCog`
- **Default branch clarified**: `main` is the default branch (not `master`) — documented in `CLAUDE.md` and `AGENTS.md`

### Fixed
- **Security**: Dashboard settings and onboarding endpoints (`GET/POST /api/dashboard/settings/{guild_id}`, all `/api/dashboard/{guild_id}/onboarding/*`) now require guild admin access via `verify_guild_admin_access()` — previously any authenticated user could read or modify another guild's settings
- **GDPR**: Implemented user data erasure on Supabase `USER_DELETED` event — purges rows from `reminders`, `support_tickets`, `onboarding_answers`, `automod_user_history`, and `gdpr_terms_acceptance` for the deleted user
- **reminder_repository**: `create()` was missing the `location` parameter — location data extracted from event embeds was silently discarded; added `location` to the INSERT and pass it from `embed_watcher`
- **Onboarding modal**: Truncate question title/label to 45 chars to stay within Discord's API limit (was raising `400 Bad Request`)
- **Onboarding modal**: Handle modal→modal chaining (Discord API forbids responding to a modal submit with another modal); added `TextInputTriggerView` bridge so each modal opens from a fresh button interaction
- **Embed watcher**: Corrected one-off vs recurring detection and T-60/T0 log display
- **Embed watcher**: Clean event title extraction, move auto-indicator to footer, delete T-60 notification when T0 fires
- **Embed watcher**: Renamed local variable `safe_embed_text` that was shadowing the `utils.sanitizer` import
- **Performance**: Added `guild_id` indexes on `reminders`, `support_tickets`, `automod_logs`, and `automod_user_history` tables (Alembic migration 012) — eliminates full-table scans on all guild-scoped queries
- **Reminders**: Move success log inside the try block so it only fires on confirmed deletion (not on missing reminders)
- **Logging**: Replace `print()` calls with `logger` in utility import scripts (`migrate_gdpr.py`, `importinvite.py`, `importdata.py`)

---

## [3.1.0] - 2026-03-31

### Added
- **Auto-Moderation System**: Comprehensive automated content moderation with configurable rules and actions
  - **Database**: Migration 009 adds 5 tables (`automod_actions`, `automod_rules`, `automod_logs`, `automod_stats`, `automod_user_history`) with indexes for performance
  - **Rule Types**: Spam detection (frequency, duplicates, caps), content filtering (bad words, links, mentions), regex patterns (premium), AI-powered analysis with Grok (premium)
  - **Actions**: Message deletion, warnings, mutes, timeouts (premium), bans (premium)
  - **Configuration Commands** (`/config automod`): `show`, `enable`, `disable`, `set_log_channel`, `reset_log_channel`, `add_spam_rule`, `add_badwords_rule`, `add_links_rule`, `add_mentions_rule`, `add_caps_rule`, `add_duplicate_rule`, `add_regex_rule`, `add_ai_rule`, `rules`, `edit_rule`, `delete_rule`, `enable_rule`, `disable_rule`, `set_severity`, `logs` (with filters: user_id, rule_id, action_type, days)
  - **Status Command**: `/automod status` shows current configuration and active rules count
  - **Premium Gating**: Advanced actions (timeout, ban), regex rules, and AI moderation require guild premium subscription
  - **Logging**: DB-backed violation logging with context, appeal system (scaffolding), performance metrics via `AutoModLogger`, and AI analysis results
  - **Analytics**: `AutoModAnalytics` service for rule effectiveness and guild overview metrics (low-priority scaffolding)
  - **Integration**: Works with existing premium guard system, settings service, and operational logs; event type normalization prevents Core ingress 422 errors
  - **Testing**: Automated tests in `tests/test_automod_rules.py` for evaluators and CRUD operations
  - **Modules**: `cogs/automod.py`, `cogs/configuration.py` (automod_group), `utils/automod_rules.py`, `utils/automod_logging.py`, `utils/automod_analytics.py`
- **App Reflections (plaintext from Core)**: Webhooks `POST /webhooks/app-reflections` and `POST /webhooks/revoke-reflection` to receive and revoke plaintext reflections from the App via Core-API; stored in `app_reflections` and used in `/growthcheckin` (user-self context only; not used for ticket "Suggest reply" for privacy).
- **Legal page**: `docs/legal.md` (docs.alphapy.innersync.tech/legal/) with company details, enterprise number, and registered office; linked from Terms of Service and Privacy Policy footers.
- **Config**: `APP_REFLECTIONS_WEBHOOK_SECRET` and `GITHUB_TOKEN` environment variables; documented in [Configuration](docs/configuration.md).
- **New `/innersync` Command**: Informational command showing Innersync platform details and official links (Core, App, Pricing) with ephemeral response
- **Legal Update Notifications**: Automated Discord notifications when Terms of Service or Privacy Policy documents change on main. A GitHub Action (`notify-legal-update.yml`) detects changes to `docs/terms-of-service.md` / `docs/privacy-policy.md`, extracts version dates, and triggers `POST /webhooks/legal-update`. The bot posts a rich embed in the configured channel of the main guild (`LEGAL_UPDATES_CHANNEL_ID`, falls back to `system.log_channel_id`). HMAC-secured via `LEGAL_UPDATE_WEBHOOK_SECRET`.

### Changed
- **Privacy**: Reflection context (Supabase + app_reflections) is no longer included in ticket "Suggest reply"; only used for user-self flows (e.g. `/growthcheckin`). (No leaks of user-data have occurred, this was caught before any tickets got made.)
- **Removed**: Release guard (GitHub 3.0.0 check) from app-reflections webhook; it was a personal sanity check, not needed in production.
- **Auto-Moderation**: Removed duplicate `cogs/automod_config.py` (modal-based approach) in favor of unified `/config automod` command structure

### Fixed
- (No changes yet)

## [3.0.0] - 2026-03-09

### Added
- **Complete Premium Monetization Ecosystem**: Full-featured subscription platform (payment provider subject to change), multi-tier pricing (€4.99/mo, €29/year, €49/lifetime), and automated guild assignment
- **Universal Database Helpers Architecture**: Centralized `DatabaseManager` class used across all 14 out of 27 cogs for consistent, safe database operations with automatic pool management and error recovery
- **Advanced Security Framework**: HMAC webhook validation, configurable admin roles via environment variables, OAuth credential security, and comprehensive rate limiting across all endpoints
- **GDPR Compliance Suite**: Terms acceptance flow with database persistence, data retention policies (7 years for tax compliance), and user data export capabilities
- **Database / GDPR**: New `terms_acceptance` table (Alembic 006) to track user consent for Terms of Service and Privacy Policy, including version and timestamp, for GDPR compliance.
- **Performance & Observability**: Extended dashboard metrics with premium usage tracking, cache size monitoring, system performance metrics (CPU/memory), and detailed operational logging
- **API Metrics**: Dashboard metrics endpoint `/api/dashboard/metrics` now includes an optional `premium_metrics` block with counters for premium checks, cache hits, transfers, and cache size.
- **Early Bird Founder Program**: Special lifetime tier recognition (€29 instead of €49) with automatic founder role assignment in Innersync guild and custom welcome messaging
- **Code Quality Assurance**: Automated syntax validation, comprehensive test coverage (15+ premium test cases), and consistent error handling patterns across entire codebase


### Changed
- **Database Operations**: 14 out of 27 cogs now use universal `DatabaseManager` with `acquire_safe()` for 100% safe database access, eliminating connection errors and improving reliability
- **Security Configuration**: Admin credentials moved from hardcoded values to environment variables (`OWNER_IDS`, `ADMIN_ROLE_IDS`), with proper separation between global owners and per-guild admin roles
- **Internationalization**: Complete codebase transition to English-only (removed all Dutch text from code, comments, logs, and user-facing strings)
- **Premium Architecture**: Core-API integration with HMAC validation, fallback mechanisms, and transfer synchronization across guild boundaries
- **Command Structure**: Enhanced permission validation with `requires_owner()` decorator for true owner-only commands vs admin-accessible features
- **Embed Consistency**: Unified embed styling and response helpers across all cogs for consistent user experience
- **Cache Management**: Intelligent cache size monitoring and automatic cleanup across all subsystems (settings, cooldowns, rate limits, command stats)
- **Premium UX**: After accepting Terms & Privacy in the `/premium` flow, users immediately see the full premium pricing embed with checkout buttons without having to rerun the command.
- **Exports & CSV helpers**: Ticket, FAQ, and onboarding exports now use shared CSV helpers and consistent English-only responses for a smoother admin experience.
- **Status: `/release` command** – Reads release notes from GitHub releases, truncates on markdown sections to stay within Discord embed limits, and includes a link to the full notes; base GitHub repo configurable via `GITHUB_REPO` env.

### Fixed
- **Database Connection Issues**: Resolved all connection pool errors, "Future exception was never retrieved" warnings, and connection timeout problems through universal helpers
- **Premium Flow Bugs**: Fixed guild assignment issues, checkout URL generation, transfer synchronization, and founder role assignment edge cases
- **Security Vulnerabilities**: Eliminated hardcoded credentials, improved OAuth handling, and added comprehensive input sanitization across all user inputs
- **Memory Leaks**: Implemented proper resource cleanup for all database pools, background tasks, and cache systems with size monitoring
- **Internationalization Errors**: Removed all Dutch text causing confusion and ensuring consistent English-only codebase
- **Command Permission Issues**: Corrected admin vs owner permission logic with proper environment-based configuration
- **Syntax Errors**: Fixed indentation issues, import problems, and structural errors introduced during large-scale refactoring
- **Internationalization cleanup**: Removed remaining Dutch user-facing strings and comments in `cogs/reminders.py`, `cogs/inviteboard.py`, `cogs/dataquery.py`, `cogs/embed_watcher.py`, and related helpers to fully enforce the English-only codebase rule.
- **Interaction flow in exports**: Fixed misuse of `ResponseHelper.send_error` before `defer()` in `/export_tickets` and `/export_faq`, preventing unnecessary followup errors and ensuring clean interaction handling.

### Security
- **Credential Management**: All sensitive data moved to environment variables with proper validation
- **API Security**: HMAC validation for webhooks, IP-based rate limiting, and guild-specific access controls
- **Input Sanitization**: Comprehensive protection against injection attacks, prompt jailbreaks, and malicious URLs
- **Data Isolation**: Complete guild data separation preventing cross-server information leakage
- **Audit Logging**: Enhanced operational logging for security monitoring and compliance

### Performance
- **Database Efficiency**: Connection pool recycling, automatic health checks, and optimized query patterns
- **Cache Optimization**: LRU cache implementation with size limits, TTL management, and cleanup automation
- **Resource Management**: Proper background task lifecycle, memory leak prevention, and graceful shutdown procedures
- **Concurrent Operations**: Parallel guild syncs, async database operations, and non-blocking command processing

### Developer Experience
- **Code Consistency**: DRY principle applied across all cogs with shared utility modules (database, embed, response, CSV helpers)
- **Error Handling**: Standardized error responses, logging patterns, and user-friendly error messages
- **Testing Framework**: Comprehensive test suite with syntax validation, import verification, and runtime testing
- **Documentation**: Updated all docs with new features, security practices, and configuration options

### Migration
- **Zero Downtime Deployment**: All changes designed for seamless upgrades without service interruption
- **Backwards Compatibility**: Existing configurations and data structures preserved where possible
- **Data Integrity**: Comprehensive validation ensuring no data loss during schema updates
- **Rollback Safety**: Clear migration paths and backup procedures for emergency rollbacks

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
