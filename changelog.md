# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- `ask_gpt()` now logs real token usage and latency.
- Persistent Google Drive authentication via service account.
- Logging of GPT calls now includes Discord username for traceability.

### Changed
- `log_gpt_error()` and `log_gpt_success()` now update shared status log without circular imports.
- Drive sync fallback added for missing topic context.

### Fixed
- 🐛 Fixed: Emoji logging crash on Windows console (UnicodeEncodeError).
- 🐛 Fixed: ImportError `cannot import name 'gpt_logs'` by decoupling `status.py`.
- 🐛 Fixed: OpenAI `400 Bad Request` when passing plain string instead of message array.

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
