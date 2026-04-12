# AGENTS.md

## 🧠 Innersync • Alphapy Bot – AI Agent Manifest

This document describes the active AI agents and modular features of the Innersync • Alphapy Discord Bot.

### Default branch: `main` (not `master`)

All PRs target `main`. The `master` branch exists but is not the default.

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
- **Purpose**: Personal growth guidance via Grok, with optional community sharing
- **Command**: `/growthcheckin`
- **Premium**: Mockingbird spicy mode for premium users
- **Reflection context**: Past reflections (Supabase `reflections_shared` + `app_reflections`) are automatically injected into the Grok prompt via `ask_gpt(include_reflections=True)`. The prompt explicitly instructs Grok to reference recurring patterns and progress.
- **Sharing**: After the AI response, users see a `GrowthShareView` (ephemeral) with three options: share anonymously, share with display name, or keep private. The share posts a Discord embed (goal / obstacle / feeling / Grok response) to the configured `growth.log_channel_id`. If no channel is configured, the share option is not shown.
- **Admin config**: `/config growth set_channel [#channel]` — omit `#channel` to get a picker (select existing or create new `#growth-checkins`). `/config growth reset_channel` removes the setting.

---

## ⚡ Agent: Premium
- **Path**: `cogs/premium.py`, `utils/premium_guard.py`, `utils/premium_tiers.py`, `webhooks/premium_invalidate.py`, `webhooks/founder.py`
- **Purpose**: Tier UX and access control (used by reminders, growth, embed watcher, onboarding)
- **Model**: One active subscription per user, applied to one guild, transferable via `/premium_transfer`
- **Tiers**: `free` (0) → `monthly` (1) → `yearly` (2) → `lifetime` (3). Constants in `utils/premium_tiers.py`: `TIER_RANK`, `GPT_DAILY_LIMIT` (free: 5, monthly: 25, yearly/lifetime: unlimited), `REMINDER_LIMIT` (free: 10, others: unlimited)
- **Commands**: `/premium`, `/premium_check`, `/my_premium`, `/premium_transfer`
- **Guard**: `is_premium()` with Core-API fallback + local cache + TTL; `invalidate_premium_cache(user_id, guild_id?)` for webhook-driven invalidation. New helpers: `get_user_tier()`, `user_has_tier()`, `check_and_increment_gpt_quota()` (tracks daily GPT calls in `gpt_usage` table, fails open on DB error)
- **Quota enforcement**: GPT daily limit checked in `gpt/helpers.py:ask_gpt()` for user-initiated calls; reminder limit checked in `cogs/reminders.py` before insert; ticket GPT summaries gated on `guild_has_premium()`
- **Expiry warnings**: `check_expiry_warnings` background task (24h loop) sends DM 7 days before expiry; tracks `expiry_warning_sent_at` on `premium_subs` to avoid duplicates
- **Early bird**: `/premium` embed checks `POST /billing/early-bird/validate` on Core-API (cached 5 min, fails open) via `CORE_API_PAYMENTS_TOKEN`; shows early bird prices while spots remain, regular prices after sellout
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
- **Flow**: Screenshot → vision JSON (`can_verify` / `needs_manual_review`) → auto-approve via `_resolve_verification` OR manual review embed with Approve/Reject buttons (`ManualReviewView`). All resolution paths go through `_resolve_verification`, which assigns roles, updates the DB (including `resolved_by_user_id`), sends a standardised log summary, and deletes the channel after 5 seconds.
- **Manual review**: When AI is uncertain, a `ManualReviewView` embed is posted with admin-only Approve (green) and Reject (red) buttons. Reject opens a modal (`RejectReasonModal`) for an optional reason shown to the user.
- **AI context**: Admins can configure `verification.ai_prompt_context` via `/config verification set_ai_prompt_context` to tell the AI what a valid payment looks like for their community. This text is appended to the base vision prompt.
- **Key**: Conservative vision model, no screenshots stored; log summaries contain no payment details (user, outcome, resolver, timestamp only)
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

## 💬 Agent: Custom Commands
- **Path**: `cogs/custom_commands.py`
- **Purpose**: Guild-defined automated message responses triggered by message patterns
- **Triggers**: `on_message` → trigger evaluation → response send + optional message delete
- **Storage**: PostgreSQL (`custom_commands` table)
- **Trigger types**: `exact`, `starts_with`, `contains`, `regex`
- **Response variables**: `{user}`, `{user.name}`, `{server}`, `{channel}`, `{uses}`, `{random:a|b|c}`
- **Caching**: Per-guild TTL cache (60 s) to avoid per-message DB hits; invalidated on add/edit/delete/toggle
- **Limits**: Max 50 commands per guild; trigger max 200 chars; response max 1900 chars; regex validated at creation
- **Management Commands** (`/cc`):
  - `add` — create a command (trigger type, pattern, response, options)
  - `edit` — edit trigger/response via Discord Modal
  - `delete` — delete with confirmation button
  - `list` — paginated list with status, type, trigger preview, use count
  - `view` — full detail embed for one command
  - `toggle` — enable / disable
- **Permissions**: All `/cc` commands require Administrator

---

## ⚖️ Agent: Legal Update Notifications
- **Path**: `webhooks/legal_update.py`, `.github/workflows/notify-legal-update.yml`
- **Purpose**: Automatically notify the main guild when Terms of Service or Privacy Policy documents change on main. A GitHub Action detects changes to `docs/terms-of-service.md` or `docs/privacy-policy.md`, extracts version dates, and fires `POST /webhooks/legal-update`.
- **Webhooks**:
  - `POST /webhooks/legal-update`: payload `documents` (array of `"tos"` / `"pp"`), `tos_version`, `pp_version`. Posts rich embeds in the configured channel. HMAC via `X-Webhook-Signature`; optional `LEGAL_UPDATE_WEBHOOK_SECRET`.
- **Channel resolution**: uses `LEGAL_UPDATES_CHANNEL_ID` env var; falls back to `system.log_channel_id` for `MAIN_GUILD_ID`.
- **Config**: `LEGAL_UPDATE_WEBHOOK_SECRET`, `LEGAL_UPDATES_CHANNEL_ID` (see `docs/configuration.md`)

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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **alphapy** (3045 symbols, 10490 relationships, 262 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/alphapy/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/alphapy/context` | Codebase overview, check index freshness |
| `gitnexus://repo/alphapy/clusters` | All functional areas |
| `gitnexus://repo/alphapy/processes` | All execution flows |
| `gitnexus://repo/alphapy/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
