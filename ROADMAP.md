# 🧬 Innersync • Alphapy Roadmap (Phase 2)

This document outlines the planned work after v1.3.0 (TicketBot). **Phase 1.5 (Multi-Guild Support) is now complete!** 🎉

## ✅ COMPLETED: Multi-Guild Architecture (Phase 1.5)

**Status:** ✅ **Fully Implemented & Deployed**

The bot now supports unlimited Discord servers with complete data isolation between guilds. All features (reminders, tickets, invites, settings, onboarding) work independently per server.

### What Was Implemented:
- **Database Schema:** Added `guild_id` columns to all tables with composite primary keys
- **Code Isolation:** Updated all cogs to use `interaction.guild.id` for guild-specific operations
- **Settings Service:** Guild-aware configuration with per-server overrides
- **API Security:** Dashboard endpoints now support optional `guild_id` filtering
- **Migration Tools:** Safe database migration scripts with backup/restore capabilities
- **Error Handling:** Guild validation checks across all commands

### Deployment Summary:
- ✅ **135 data entries** successfully migrated to guild `1160511689263947796`
- ✅ **Zero downtime** deployment with backup verification
- ✅ **Full backwards compatibility** maintained
- ✅ **Security hardening** - no cross-guild data leakage

---

## Themes
- Faster answers: FAQ search and autocomplete directly in Discord
- Better workflows: richer ticket statuses and handoffs
- Smarter support: AI-assisted replies grounded in your docs (light RAG)
- Human-first tone: empathetic responses on sensitive signals
- Visibility: export tools, metrics, and dashboards
- ✅ **Multi-tenant:** Complete guild isolation and per-server configuration

---

## Whitepaper Prep – Runtime Configuration Roadmap

| Phase | Status | Scope |
| --- | --- | --- |
| 0 | ✅ Done | Settings foundation (`SettingsService`, `/config` shell, embed watcher + reminders wired in) |
| 1 | ✅ Done | Expand setting registrations (reminder scheduler options, GPT throttles, invite templates, GDPR toggles) |
| 2 | 🔄 Next | Slashcommand UX polish: paginated `/config … show`, richer validation, autocomplete for channel/role targets |
| 3 | 🔄 Next | Service listeners + cache refresh so cogs react instantly without restart; unify DB connection pooling |
| 4 | 🔄 In progress | Observability & safety: FastAPI `/health` probe live; next up—config audit trail to DB and unit tests for coercion |
| 5 | 🔄 Next | Launch checklist + docs update: whitepaper excerpt, CHANGELOG, admin hand-off guide |

### Implementation Checklist
- [x] Create `SettingsService` with typed definitions and DB-backed overrides.
- [x] Register core settings (log channel, embed watcher channel + offset) and expose `/config` commands.
- [x] Refactor remaining cogs to consume `bot.settings` (TicketBot logs, GPT config, invite tracker templates, GDPR announcements).
- [x] Add onboarding helpers: `/config reminders set-default-channel`, `/config gpt set-model`, `/config invites set-message`.
- [x] Implement settings listeners for hot-reload behaviour (e.g., reminder interval, GPT rate limits).
- [x] Add tests (`tests/test_settings_service.py`) covering coercion, persistence and permission checks.
- [x] Document admin workflow in `docs/configuration.md` and surface summary in CHANGELOG.

### Key Decisions & Open Questions
- **Database migrations:** voorlopig blijven we bij cog-level `CREATE TABLE IF NOT EXISTS`; zodra we meer schemawijzigingen stapelen, herbekijken we een migrationtool.
- **Permission tiers:** geen extra rol nodig; owners/admins blijven de enige configuratiemanagers.
- **Secret storage:** secrets (`BOT_TOKEN`, `OPENAI_API_KEY`, DB credentials) blijven in `.env`/secrets manager; alles wat runtime bijsturing vereist (kanalen, offsets, toggles) gaat via de settings-service.
- **Rollout volgorde:** we houden de volgorde embed/reminders → ticketbot → GPT → invites → GDPR → overige utilities aan.

---

## Milestones

### M1 — FAQ Search & Autocomplete (Discord)
- Commands:
  - `/faq` root: subcommands
    - `/faq search query:<text>` – returns top 5 FAQ entries, link/embed
    - `/faq view id:<int>` – show single entry
    - `/faq list` – recent or pinned
- Autocomplete: suggest entries while typing `query` (based on title/keywords)
- Storage: reuse `faq_entries (id, similarity_key, summary, created_by, created_at)`
- Scoring: simple TF-IDF-like sim or token overlap; later pluggable for embeddings
- Observability: log searches (term, hit_count) for later analytics
- Risk/Notes: rate-limit safe, ephemeral responses for privacy

### M2 — Ticket Status Model & Workflows
- New statuses: `open`, `claimed`, `waiting_for_user`, `escalated`, `closed`
- UI:
  - Add “Wait for user” and “Escalate” buttons (staff-only)
  - Visual chip in the ticket embed to reflect status
  - Optional escalation target role/channel
- DB:
  - `support_tickets.status` (already exists)
  - Add `escalated_to BIGINT NULL` (role or user ID)
  - Add `updated_at TIMESTAMPTZ` for SLA/aging
- Commands:
  - `/ticket status <id> <status>` (admin)
- Notifications: optional ping on status change (configurable)

### M3 — AI Agent Replies (Light RAG)
- Goal: assistant provides draft replies in the ticket channel
- Source: small doc set (local `data/faq/*.md` + `faq_entries` + pinned context)
- Flow:
  - Button “💬 Suggest reply” (staff-only) → ephemeral draft
  - Staff can edit and post; bot never auto-sends without approval
- Implementation:
  - Add `gpt/rag_index.py` (build small in-memory index per boot)
  - Helper `generate_support_reply(context, question)` using `ask_gpt`
  - Safety: redact tokens/PII when echoing user text, respect blocked prompts
- Observability: track acceptance rate of suggestions, time saved proxy

### M4 — Exports, Metrics, Dashboards
- Exports:
  - `/export tickets <from> <to>` → CSV (id, user, status, age, claimed_by, timestamps)
  - `/export faq` → CSV of knowledge base entries
- Metrics & dashboards (first cut):
  - Ticket volume by day, avg time-to-claim/close, status distribution
  - FAQ coverage: top search terms without hits
  - Implementation path: simple FastAPI endpoints consumed by a lightweight dashboard (e.g., Observable/Streamlit) or CSVs to GDrive
  - ✅ Initial delivery: `/api/dashboard/metrics` serves live bot/GPT/reminder/ticket telemetry backed by `utils/runtime_metrics`
  - ✅ Infrastructure now has `/health` and shared `*.innersync.tech` base URLs exposed via `config.py`

---

## Detailed Specs & Changes

### Database
- `support_tickets`
  - Add `updated_at TIMESTAMPTZ DEFAULT NOW()` (update on any status change)
  - Add `escalated_to BIGINT NULL`
  - Indexes: `idx_support_tickets_status`, `idx_support_tickets_updated_at`
- `faq_entries`
  - Optional: add `title TEXT`, `keywords TEXT[]` for better UX
- New (optional later): `faq_search_logs(id, query, matched_ids INT[], created_at)`

### Commands & Permissions
- All admin/staff checks continue to use `is_owner_or_admin_interaction`
- New commands: `/faq search|view|list`, `/ticket status`, `/export tickets|faq`

### UI & UX
- Ticket embed shows status chip and last updated timestamp
- Buttons: Claim, Close, Delete (existing) + Wait for user, Escalate, Suggest reply
- Autocomplete: for `/faq search query` on keyup

### AI & RAG
- Docs: `data/faq/*.md` + DB entries
- Index: build on startup; reload via `/faq reload` (admin)
- Guardrails: never send replies automatically; always draft → confirm

### Observability
- Structured logs for `/faq` queries
- Simple counters per feature (prometheus-ready if needed later)
- Error reporting remains via `WATCHER_LOG_CHANNEL`

### Security & Privacy
- Ephemeral drafts for AI suggestions
- Respect `OWNER_IDS` and `ADMIN_ROLE_ID` for all staff operations
- PII redaction in prompts where feasible

---

## Rollout Plan
- Week 1–2: M1 (FAQ search/autocomplete) + storage and logs
- Week 3: M2 (status model + buttons + UI)
- Week 4: M3 (AI draft replies, light RAG)
- Week 5: M4 (exports + simple dashboard wiring)

Each milestone is releasable independently. Start with guild-scoped commands for fast iteration, then promote to global.

---

## Nice-to-haves (Backlog)
- Embedding-based search upgrade for FAQ (OpenAI embeddings or local)
- SLA timers and alerts (e.g., no reply in X hours)
- ✅ **Multi-tenant guild configuration and per-guild FAQ sets** - COMPLETED in Phase 1.5!
- Attachment ingestion (images/PDF) for RAG with safety checks
- Auto-translation layer (UI + summaries)
