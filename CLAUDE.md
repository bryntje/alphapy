# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Alphapy is a modular, multi-guild Discord bot for the Innersync • Alphapips community. It combines Discord slash commands, a FastAPI HTTP layer, PostgreSQL (via Supabase/asyncpg), Alembic migrations, and Grok/OpenAI AI features.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env   # set BOT_TOKEN, DATABASE_URL, and optional vars

# Apply database migrations
alembic upgrade head   # or: alembic stamp head if DB already has schema

# Run the bot
python bot.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_embed_watcher_parsing.py -v

# Run a single test function
pytest tests/test_sanitizer.py::test_function_name -v

# Create a new migration
alembic revision --autogenerate -m "description"
```

## Architecture

### Entry points
- **`bot.py`** — initializes the Discord bot, loads cogs via `utils/lifecycle.py` (phased startup: DB → settings → cogs → command sync), and starts background tasks
- **`api.py`** — FastAPI server for HTTP endpoints (reminders CRUD, dashboard metrics/logs, webhooks from Core-API)
- **`config.py`** — all environment variable loading; required vars are `BOT_TOKEN` and `DATABASE_URL`

### Core layers

**`cogs/`** — each file is a Discord Cog with slash commands. Key cogs:
- `configuration.py` — guild settings wizard (largest file, ~139KB)
- `ticketbot.py` — support tickets with Grok summaries and FAQ proposals
- `reminders.py` — manual reminder management
- `embed_watcher.py` — auto-detects event embeds and creates reminders from them
- `onboarding.py` — configurable multi-step onboarding flow
- `automod.py` — content moderation with rule engine
- `premium.py` — subscription tier management

**`utils/`** — shared infrastructure:
- `lifecycle.py` — phased startup manager
- `settings_service.py` — guild settings CRUD (channels, roles, feature flags)
- `db_helpers.py` — connection pool management; always use `acquire_safe` and parameterized queries
- `sanitizer.py` — sanitize user input before embedding in Discord messages (use `safe_embed_text()`)
- `premium_guard.py` — `is_premium()` with Core-API fallback, local cache, TTL; use `invalidate_premium_cache()` on webhook
- `logger.py` — centralized logging; use `from utils.logger import logger`, never `print()` for operational logging

**`gpt/`** — AI integration: `helpers.py` (Grok/OpenAI calls), `context_loader.py` (conversation context + user reflections), `dataset_loader.py` (learning data for `/learn_topic`)

**`webhooks/`** — inbound webhooks from Core-API (premium invalidation, reflections, founder DMs, Supabase events). All use HMAC via `X-Webhook-Signature`.

**`alembic/versions/`** — migration files. See `docs/migrations.md` for workflow.

### Multi-guild isolation

All data and configuration is scoped per guild (`guild_id`). `SettingsService` is the canonical way to read/write guild settings — do not bypass it with raw DB queries for config.

### Premium gating

Premium is per-user, applied to one guild. `utils/premium_guard.py` exposes `is_premium(user_id, guild_id)`. Some features are guild-level premium (`guild_has_premium`). Invalidation is webhook-driven from Core-API.

## Code conventions

- **Language**: All code, comments, docstrings, user-facing strings, and log messages must be in **English**. No Dutch anywhere, even if the user communicates in Dutch. Exception: intentional display labels like language names in onboarding ("Nederlands", "Español").
- **Logging**: `from utils.logger import logger`; use `log_with_guild` / `log_database_event` helpers where appropriate.
- **Embeds**: Follow embed styling from `AGENTS.md` (colors, timestamps, footers, field limits). Always pass user-supplied content through `safe_embed_text()`.
- **Database**: Use `acquire_safe` from `db_helpers.py`; parameterized queries only; no raw string interpolation in SQL.
- **Admin commands**: Use `validate_admin` / permission checks for any admin-only commands.
- **Branches**: `master` is protected — work on `feature/` or `fix/` branches and open PRs.

## Key reference docs

| Topic | Location |
|-------|----------|
| Agent manifest, embed style, DB overview | `AGENTS.md` |
| Slash command reference | `docs/commands.md` |
| Env vars and multi-guild config | `docs/configuration.md` |
| API endpoints | `docs/api.md` |
| Database schema | `docs/database-schema.md` |
| Migration workflow | `docs/migrations.md` |
| Security practices | `docs/SECURITY.md` |

When adding or changing commands, config, or API endpoints, update `AGENTS.md` and the relevant docs to keep them in sync.
