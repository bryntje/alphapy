# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- `ask_gpt()` now logs real token usage and latency.
- Persistent Google Drive authentication via service account.
- Logging of GPT calls now includes Discord username for traceability.
- Onboarding: new 4-question flow with follow-ups and email validation.
- Onboarding: DRY helpers for answer formatting.
- ReactionRoles: onboarding message detection via button custom_id.
- Reminders: support for parsing embeds via link; call_time handling.
- Embed watcher: improved datetime parsing and timezone consistency.

### Changed
- `log_gpt_error()` and `log_gpt_success()` now update shared status log without circular imports.
- Drive sync fallback added for missing topic context.
- Config is fully env-driven; added ANNOUNCEMENTS_CHANNEL_ID.

### Fixed
- 🐛 Fixed: Emoji logging crash on Windows console (UnicodeEncodeError).
- 🐛 Fixed: ImportError `cannot import name 'gpt_logs'` by decoupling `status.py`.
- 🐛 Fixed: OpenAI `400 Bad Request` when passing plain string instead of message array.
- 🐛 Fixed: duplicate onboarding message by switching to button detection.
- 🐛 Fixed: reminders loop timezone and embed field robustness.

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
