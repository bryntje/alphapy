# 🧬 Innersync • Alphapy Architecture

## High-level overview
- Discord bot (discord.py) with modular cogs + FastAPI layer (`api.py`)
- PostgreSQL + Alembic migrations for all persistent data
- Supabase for telemetry (Mind dashboard) and auth
- Closed loop: Alphapy catches input → Core-API processes → Mind monitors → App reflects

## Key modules
- `cogs/onboarding.py` + `reaction_roles.py`: configurable onboarding + rules
- `cogs/reminders.py` + `embed_watcher.py`: manual + auto reminders (NLP parsing)
- `cogs/verification.py`: AI vision payment verification
- `cogs/ticketbot.py`: support tickets with GPT summary + FAQ proposal
- `cogs/premium.py`: tier guard + transfer
- `api.py`: dashboard endpoints + telemetry ingest job (subsystem='alphapy')
- `utils/`: lifecycle, db_helpers, sanitizer, embed_builder, command_tracker, fyi_tips

## Database Architecture
- Multiple asyncpg pools (FastAPI + per-cog dedicated)
- Central `bot_settings` + `audit_logs` + feature tables (reminders, onboarding, support_tickets, etc.)
- Command tracking via batch queue in the bot event loop
- See `docs/database-schema.md` for full tables

## Secrets & Infrastructure
- GCP Secret Manager (`utils/gcp_secrets.py`) with cache + env fallback
- All credentials via environment variables or Secret Manager, zero hard-coded values

## Control flow
1. Startup → `StartupManager` (phased: DB → settings → cogs → sync → background tasks)
2. New guild / reconnect → minimal resync of commands
3. User input → cog → sanitizer → database and/or GPT
4. Background jobs → reminders, telemetry push to Supabase, cleanup tasks
5. Observability → operational logs + `/api/dashboard/*` for Mind

## Observability, Security & Testing
- Operational logs (in-memory buffer) + telemetry to Mind dashboard
- Input sanitization via `utils/sanitizer.py` to guard against injection/spam
- Rate limiting on Discord side and FastAPI IP middleware
- 50+ pytest tests covering parsing, security, and edge cases

## Shared References
- Full schema: `docs/database-schema.md`
- Detailed changes: `docs/CHANGELOG.md` (or `docs/DETAILS.md`)
- Tests: `tests/`
- Embed guide: `EMBEDS.md`