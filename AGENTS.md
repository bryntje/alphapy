# AGENTS.md

## 🧠 Innersync • Alphapy Bot – AI Agent Manifest

This document describes the active AI agents and modular features of the Innersync • Alphapy Discord Bot.

### Codebase language: English only (no Dutch/NL)

**The entire codebase is in English.** Do not introduce Dutch in:
- Source code, comments, docstrings
- User-facing strings (embeds, buttons, commands, error messages)
- Log messages and operational logs

This applies even when the user speaks Dutch in chat or in instructions. Keep all code, comments, and in-app text in English. Exceptions: display labels that are intentionally in another language (e.g. language names like "Nederlands", "Español" in onboarding options) are allowed.

---

## 📣 Agent: EmbedReminderWatcher
- **Path**: `cogs/embed_watcher.py`
- **Purpose**: Detects new embeds in the announcements channel and automatically creates reminders
- **Triggers**: `on_message` → embed parsing
- **Storage**: PostgreSQL (reminders table)
- **Special parsing**: Title, time, days, location via NLP
- **Helper**: `parse_embed_for_reminder()` + `_short_title_for_reminder_name()`
- **Message formatting**: `_format_message_paragraphs()` for readable paragraphs + timezone bullet splits
- **Logging**: Guild log channel with `safe_embed_text(..., 1024)`
- **Known Issues**: Timezone parsing is critical

---

## 🧾 Agent: ReminderManager
- **Path**: `cogs/reminders.py`
- **Purpose**: Slash commands for manual reminder management
- **Commands**: `/add_reminder`, `/add_live_session`, `/reminder_list`, `/reminder_edit`, `/reminder_delete`
- **LiveSessionPresets**: `/add_live_session` creates a recurring live-session reminder (fixed message, optional image; premium for images)
- **Interaction**: Shares parser with EmbedReminderWatcher
- **Embeds**: Title max 240 chars, location max 1024 chars

---

## 🚀 Agent: GrokInteraction
- **Purpose**: AI functionality with Grok
- **Commands**: `/create_caption`, `/learn_topic`, `/gptstatus`

---

## 🌱 Agent: GrowthCheckIn
- **Purpose**: Personal growth guidance via Grok
- **Command**: `/growthcheckin`
- **Premium**: Mockingbird spicy mode for premium users

---

## ⚡ Agent: Premium
- **Path**: `cogs/premium.py`, `utils/premium_guard.py`
- **Purpose**: Tier UX and access control (used by reminders, growth, embed watcher, onboarding)
- **Model**: One active subscription per user, applied to one guild, transferable via `/premium_transfer`
- **Commands**: `/premium`, `/premium_check`, `/my_premium`, `/premium_transfer`
- **Guard**: `is_premium()` with Core-API fallback + local cache + TTL

---

## 🔐 Agent: GDPRHandler
- **Purpose**: Support for data rights
- **Command**: `/export_onboarding`
- **Future**: `/delete_my_data`

---

## 🧮 Agent: InviteTracker
- **Purpose**: Tracks Discord invites per user
- **Commands**: `/inviteleaderboard`, `/setinvites`, `/resetinvites`

---

## ✅ Agent: Verification
- **Path**: `cogs/verification.py`, `cogs/configuration.py`
- **Purpose**: AI-assisted payment verification via private channels
- **Flow**: Screenshot → vision JSON (`can_verify` / `needs_manual_review`) → auto-role or manual review
- **Key**: Conservative vision model, no screenshots stored
- **Premium**: Starting verification requires an active premium subscription for the user in that guild

---

## 📜 Agent: Onboarding
- **Path**: `cogs/onboarding.py` + reaction_roles + configuration
- **Purpose**: Configurable onboarding flow with rules, questions and personalization
- **Helper**: `get_user_personalization()` for opt-in + preferred language
- **API**: Dashboard endpoints ready (`/api/dashboard/{guild_id}/onboarding/*`)

---

## 🧩 Agent: JoinRole
- **Path**: `cogs/join_roles.py`, `cogs/configuration.py`, `cogs/onboarding.py`, `cogs/verification.py`
- **Purpose**: Assign a temporary join role to new members on guild join
- **Behavior**:
  - On join: assigns `onboarding.join_role_id` when onboarding is enabled
  - On completion: removes the join role after onboarding completion (after assigning the completion role, if configured)
  - On verification: removes the join role after successful payment verification (after assigning the verified role)

---

## 🔄 Agent: UtilityAdmin
- **Commands**: `/clean`, `/sendto`, `/reload`

---

## 💡 Contextual FYI tips
- **Path**: `utils/fyi_tips.py`
- **Purpose**: One-time context-sensitive tips on first events per guild (24h cooldown)
- **Phase 1 live**: `first_guild_join`, `first_onboarding_done`, `first_config_wizard_complete`, `first_reminder`, `first_ticket`

---

## 🌐 API Agent: FastAPI Dashboard Endpoint
- **Path**: `api.py`
- **Purpose**: Exposes reminders and realtime metrics for Mind/App
- **Endpoints**: `/api/reminders/*`, `/api/dashboard/metrics`, `/api/dashboard/logs`

---

## 📊 Agent: Telemetry Ingest Background Job
- **Path**: `api.py` (`_telemetry_ingest_loop()`)
- **Purpose**: Periodic push of Alphapy metrics to Supabase for Mind dashboard
- **Interval**: 30-60s, subsystem='alphapy'

---

## Shared References
- **Embed styling**: see `EMBEDS.md`
- **Database pools, command tracking & infra**: see `ARCHITECTURE.md`