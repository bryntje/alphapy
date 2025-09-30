# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Automatische metriek-snapshots bij het sluiten van een ticket met onderwerp-inschatting (laatste ticket + top 30 dagen).

### Fixed
- Auto-reminder parser herkent nu datums die in de `Time:`-regel staan (bv. "Wednesday, October 01/10/25 – 19:30"), waardoor eenmalige evenementen correct worden opgeslagen.
- Ticket panel knoppen blijven actief na een bot-restart dankzij registratie van de persistente view tijdens initialisatie.

### Changed
- Ticket "Delete" knop archiveert tickets (status `archived`) en behoudt summaries voor rapportering.

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
