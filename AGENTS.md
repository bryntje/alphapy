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
- **Path**: `cogs/premium.py`, `utils/premium_guard.py`, `webhooks/premium_invalidate.py`, `webhooks/founder.py`
- **Purpose**: Tier UX and access control (used by reminders, growth, embed watcher, onboarding)
- **Model**: One active subscription per user, applied to one guild, transferable via `/premium_transfer`
- **Commands**: `/premium`, `/premium_check`, `/my_premium`, `/premium_transfer`
- **Guard**: `is_premium()` with Core-API fallback + local cache + TTL; `invalidate_premium_cache(user_id, guild_id?)` for webhook-driven invalidation
- **Webhooks (Core → Alphapy)**:
  - `POST /webhooks/premium-invalidate`: payload `user_id`, optional `guild_id`. Clears premium cache so next check refetches from Core/DB. HMAC via `X-Webhook-Signature`; optional `PREMIUM_INVALIDATE_WEBHOOK_SECRET`.
  - `POST /webhooks/founder`: payload `user_id`, optional `message`. Sends founder welcome DM. HMAC via `X-Webhook-Signature`; optional `FOUNDER_WEBHOOK_SECRET`.

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
- **Purpose**: Lets guilds run their own payment verification: a public area plus a paid area gated by a "verified" role. Members submit a payment screenshot (for the guild’s products, events, or access); after AI or manual review they receive the verified role and access. This is **not** for verifying Alphapy premium—it is a premium **feature** of Alphapy that guilds can use for their own payment gating.
- **Flow**: Screenshot → vision JSON (`can_verify` / `needs_manual_review`) → auto-role or manual review
- **Key**: Conservative vision model, no screenshots stored
- **Premium**: Only guilds with an active Alphapy premium subscription can use verification (`guild_has_premium`). The member clicking Start verification does not need Alphapy premium—they are proving payment to the guild to get the verified role.

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

## � Agent: Status
- **Path**: `cogs/status.py`
- **Purpose**: General information and status commands
- **Commands**: `/version`, `/gptstatus`, `/innersync`, `/release`, `/health`, `/commands`, `/command_stats`

---

## �💡 Contextual FYI tips
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

## 🛡️ Agent: AutoModeration
- **Path**: `cogs/automod.py`, `cogs/configuration.py`, `utils/automod_rules.py`, `utils/automod_logging.py`, `utils/automod_analytics.py`
- **Purpose**: Automated content moderation with configurable rules and actions
- **Triggers**: `on_message` → rule evaluation → action execution
- **Storage**: PostgreSQL (automod_rules, automod_actions, automod_logs, automod_stats, automod_user_history)
- **Rule Types**: 
  - Spam detection: frequency, duplicates, caps
  - Content filtering: bad words, links, mentions
  - Regex patterns (premium)
  - AI-powered analysis (premium, Grok integration)
- **Actions**: Message deletion, warnings, mutes, timeouts (premium), bans (premium)
- **Premium Features**:
  - Advanced actions (timeout, ban)
  - Regex rule patterns
  - AI-powered content analysis with Grok (custom policies, confidence thresholds)
  - Analytics dashboard (scaffolding)
- **Configuration Commands** (`/config automod`):
  - `show`, `enable`, `disable`
  - `set_log_channel`, `reset_log_channel`
  - `add_spam_rule`, `add_badwords_rule`, `add_links_rule`, `add_mentions_rule`, `add_caps_rule`, `add_duplicate_rule`, `add_regex_rule`, `add_ai_rule`
  - `rules`, `edit_rule`, `delete_rule`, `enable_rule`, `disable_rule`
  - `set_severity` (rule priority management, 1-10)
  - `logs` (with filters: user_id, rule_id, action_type, days)
- **Status Command**: `/automod status`
- **Logging**: Comprehensive violation logging with context, appeal system (scaffolding), and performance metrics
- **Analytics**: `AutoModAnalytics` service for rule effectiveness and guild overview metrics (low-priority scaffolding)
- **Integration**: Works with existing premium guard system, settings service, and operational logs

---

## �� Agent: App Reflections (Plaintext from Core)
- **Path**: `webhooks/app_reflections.py`, `webhooks/revoke_reflection.py`, `gpt/context_loader.py`
- **Purpose**: Receive plaintext reflections from App via Core-API webhook; store in `app_reflections`; use in `/growthcheckin` (and other user-self flows). Not used for ticket "Suggest reply" (privacy: reflections stay out of admin-only, ephemeral ticket actions).
- **Data flow**: Shared reflections are decrypted client-side in the App, then sent as plaintext to Core-API, which forwards them to Alphapy (and/or Supabase). Alphapy never receives or decrypts encrypted content.
- **Webhooks**:
  - `POST /webhooks/app-reflections`: payload `user_id` (Discord), `reflection_id`, `plaintext_content` (JSONB). Upsert into `app_reflections`. HMAC via `X-Webhook-Signature`; optional secret `APP_REFLECTIONS_WEBHOOK_SECRET`.
  - `POST /webhooks/revoke-reflection`: payload `user_id`, `reflection_id`. DELETE from `app_reflections`. Same signature pattern.
- **Integration**: `gpt/context_loader.load_user_reflections()` loads from Supabase `reflections_shared` (existing) and from `app_reflections` (last 30 days). Merged into Grok context only for user-self flows (e.g. `/growthcheckin`). Ticket "Suggest reply" calls `ask_gpt(..., include_reflections=False)` so no reflection context is sent there.

---

## Shared References
- **Embed styling**: see `EMBEDS.md`
- **Database pools, command tracking & infra**: see `ARCHITECTURE.md`
- **Auto-moderation implementation details**: see `changelog.md` (latest release notes)
