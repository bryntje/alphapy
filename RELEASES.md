# Release Notes

All notable releases of Alphapy will be documented in this file.

---

## [1.9.0] - 2026-01-21 - "Enhanced Reminders"

### 🎉 Major Feature: Reminder Management & Embed Watcher Improvements

This release focuses on enhancing reminder functionality with editing capabilities, improved embed parsing, and better error handling.

#### What's New
- **Reminder Edit Command:** `/reminder_edit` with full modal interface for editing existing reminders
  - Edit name, time, days, message, and channel ID
  - Pre-fills with current reminder values including event time (T0)
  - Channel ID editing support in modal
- **Embed Watcher Enhancements:**
  - Footer text extraction and inclusion in reminder parsing
  - Bot message processing toggle via `embedwatcher.process_bot_messages` setting
  - Rich Discord embed logging for better visibility
  - Smart duplicate detection to prevent content overlap
  - Full day name display in logs
  - One-off event weekday storage for informational display
- **GPT Retry Queue System:**
  - Automatic retry queue for rate-limited or failed GPT API requests
  - Exponential backoff retry mechanism
  - Fallback message for degraded AI service scenarios
  - Background task for processing queued requests

#### Internationalization
- **Complete English Translation:** All Dutch user-facing text replaced with English
  - Command descriptions and parameter descriptions
  - Error messages and success notifications
  - Log messages and embed content
  - GPT system prompts

#### Technical Improvements
- **Logging Improvements:**
  - Converted plain text logs to structured Discord embeds
  - Reduced console verbosity by removing excessive debug statements
  - Enhanced log formatting with proper day names and structured fields
- **Message Content Handling:**
  - Smart duplicate detection prevents title/description overlap
  - Footer handling in embed watcher for consistent formatting
  - Name field sanitization for Discord modal compliance

#### Bug Fixes
- **Reminder Edit Modal:**
  - Fixed `HTTPException: 400 Bad Request` error caused by newlines in name field
  - Corrected time display to show event time (T0) instead of reminder time (T-60)
  - Fixed message duplication issue when editing reminders
  - Resolved Discord modal field limit by optimizing field usage
- **Embed Watcher:**
  - Fixed footer not being stored correctly in reminders
  - Fixed one-off events missing weekday information
  - Fixed bot message processing loop protection
  - Improved parsing failure logging with detailed error information
- **GPT Integration:**
  - Fixed `RuntimeError: no running event loop` when starting retry queue task
  - Corrected linter error for `status_code` attribute access
  - Improved error handling for rate limits and API failures

---

## [1.7.0] - 2025-11-16 - "Multi-Guild Horizon"

### 🎉 Major Feature: Complete Multi-Guild Support + Advanced Onboarding

Alphapy now supports unlimited Discord servers with complete data isolation, independent configuration, and a comprehensive onboarding system.

#### What's New
- **Guild Isolation**: All features (reminders, tickets, invites, settings, onboarding) work independently per server
- **Modular Onboarding**: Fully configurable onboarding flows with custom questions, rules, and completion roles
- **Onboarding Panels**: Admin commands to post onboarding start buttons in any channel
- **Email/Text Support**: Modal-based input handling for all question types including optional fields
- **Database Schema**: Added `guild_id` columns to all tables with composite primary keys for data separation
- **API Security**: Dashboard endpoints with optional `guild_id` filtering to prevent cross-guild data leakage
- **Migration Tools**: Safe database migration scripts with backup/restore capabilities
- **Error Handling**: Comprehensive guild validation and duplicate record handling

#### Migration Summary
- ✅ **All tables migrated** with `guild_id` support and composite primary keys
- ✅ **Zero downtime** deployment with full backup verification
- ✅ **Complete backwards compatibility** maintained
- ✅ **Security hardening** - no cross-guild data leakage possible

#### Onboarding System Features
- **Question Types**: Support for select, multiselect, text, and email input types
- **Optional Questions**: Users can skip optional fields (like email addresses)
- **Custom Rules**: Guild admins can define custom server rules during onboarding
- **Completion Roles**: Automatic role assignment upon onboarding completion
- **Panel Management**: `/config onboarding panel_post` to place onboarding buttons anywhere
- **Re-onboarding**: Users can update their responses and redo onboarding

#### Technical Improvements
- **Type Safety**: Zero pyright errors with complete type checking
- **Settings Service**: Guild-scoped configuration with per-server overrides
- **Code Architecture**: All cogs updated with `interaction.guild.id` validation
- **Database**: Composite primary keys `(guild_id, user_id)` or `(guild_id, id)` across all tables
- **API Endpoints**: Guild filtering implemented for security in dashboard metrics
- **Modal Handling**: Robust text input modals with optional field support
- **Error Recovery**: Graceful handling of duplicate records and migration edge cases

#### Security Enhancements
- **Data Isolation**: Complete separation between guild data preventing unauthorized access
- **Input Validation**: Guild existence checks prevent DM usage errors
- **API Filtering**: Dashboard endpoints properly filter by guild context
- **Migration Safety**: Backup verification and rollback capabilities

#### Bug Fixes
- **Onboarding Flow**: Fixed crashes when processing email/text questions
- **Database Constraints**: Resolved duplicate key violations in onboarding records
- **Modal Handling**: Added support for optional text input fields
- **Type Checking**: Eliminated all pyright errors across the codebase
- **Syntax Errors**: Fixed import and compilation issues

---

## [1.6.0] - 2025-10-17 - "Dashboard Foundations"

### Added
- FastAPI dashboard endpoint `/api/dashboard/metrics` exposing live bot telemetry
- Service health probe `/health` returning service status and database connectivity
- Supabase Auth integration with automatic profile bootstrap and OAuth flows

### Changed
- Project branding updated to **Innersync • Alphapy** across all documentation
- CORS origins and base URLs aligned with Innersync domain suite
- Supabase JWT validation moved to server-side verification

---

## [1.5.0] - 2025-10-04 - "Dynamic Config"

### Added
- Runtime configuration system with per-guild settings management
- Settings commands: `/config system show`, `/config embedwatcher show`, etc.
- Invite tracker with enable/disable toggle and customizable templates
- GDPR announcements with runtime settings control

### Changed
- Bot startup validation improved with early token checks
- Import flows made more robust with embed existence checks

---

## [1.4.0] - 2025-09-13 - "TicketBot & FAQ"

### Added
- Complete TicketBot system with private channels, status management, and AI assistance
- FAQ search system with autocomplete and admin management tools
- Ticket statistics and export functionality
- AI-assisted reply suggestions for support tickets

---

## Previous Releases

See [CHANGELOG.md](changelog.md) for detailed change history of all versions.
