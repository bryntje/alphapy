# Recovery after branch/restore (v3.0.0 work)

This document summarizes what was **not** lost and what **was** lost when uncommitted changes were reverted, and how to recover.

## Still present (do not lose)

### Untracked files (never reverted)

These were never committed, so `git restore` did not touch them. **Add and commit them as soon as possible.**

| File | Purpose |
|------|--------|
| `utils/database_helpers.py` | `DatabaseManager` + shared pool helpers (44 lines) |
| `utils/embed_helpers.py` | `create_success_embed`, `create_error_embed`, etc. (58 lines) |
| `utils/csv_helpers.py` | CSV export helpers (51 lines) |
| `utils/response_helpers.py` | Standard response helpers (65 lines) |
| `alembic/versions/006_terms_acceptance_gdpr.py` | Terms acceptance table for GDPR |
| `check_config.py` | Config validation script |
| `performance_test.py` | Performance test script |
| `docs/pricing.md` | Pricing page content |

### In working tree (modified, not committed)

- **changelog.md** – Full 3.0.0 section (Added, Changed, Fixed, Security, Performance, etc.) is your **spec** for what was implemented.
- **ROADMAP.md** – v3.0.0 "Enterprise Ready" header and wording.

### Reference (not code)

- **.cursor/plans/** – Plans that describe the v3.0.0 work:
  - `premium_tier_introduction_6cc3f514.plan.md` – Premium guard, `/premium`, gates, onboarding.
  - `replace_direct_database_connections_with_connection_pools_9bd448e0.plan.md` – Pool pattern per cog (ticketbot, embed_watcher, exports, faq, inviteboard, gdpr, status).
  - `zero-knowledge_cross-module_integration_54b782b9.plan.md` – Cross-module integration.
  - Others (verification, encrypted_reflections, etc.) as needed.

---

## Lost (reverted tracked files)

All **modifications** to already-tracked files were reverted to `master`. So the following no longer contain the v3.0.0 implementation (they are back to pre–v3.0.0 state):

- **AGENTS.md** – v3.0.0 agent updates
- **api.py** – Dashboard metrics, premium, telemetry, rate limiting
- **cogs/** – configuration, dataquery, embed_watcher, exports, faq, gdpr, migrate_gdpr, migrations, onboarding, premium, reload_commands, reminders, slash_utils, status, ticketbot, verification
- **utils/** – checks.py, checks_interaction.py, fyi_tips.py, guild_admin.py, premium_guard.py, validators.py
- **config.py** – New env vars (e.g. OWNER_IDS, ADMIN_ROLE_IDS, premium)
- **version.py**
- **docs/** – commands.md, configuration.md, database-schema.md, premium.md, privacy-policy.md, terms-of-service.md
- **tests/test_premium_guard.py**

So: **all code that used `DatabaseManager`, embed_helpers, response_helpers, and the security/GDPR/premium changes is gone** from those files; only the **new** (untracked) helper files and migration 006 remain.

---

## Recovery steps

1. **Secure untracked files**
   ```bash
   git add utils/database_helpers.py utils/embed_helpers.py utils/csv_helpers.py utils/response_helpers.py
   git add alembic/versions/006_terms_acceptance_gdpr.py docs/pricing.md check_config.py performance_test.py
   git commit -m "Add v3.0.0 helper modules and migration 006 (recovery)"
   ```

2. **Use Cursor Local History**  
   For each reverted file: right-click → **Local History** / **Timeline** and restore the last version that had your v3.0.0 edits (if still available).

3. **Re-apply from plans + changelog**
   - Use **changelog.md [3.0.0]** as the checklist of features.
   - Use **replace_direct_database_connections_with_connection_pools_9bd448e0.plan.md** to re-apply the pool pattern to each cog (ticketbot, embed_watcher, exports, faq, inviteboard, gdpr, status).
   - Use **premium_tier_introduction** and existing **premium** docs to re-apply premium guard, `/premium`, gates, and Core-API.
   - Use **legal-gdpr-audit** skill and **docs/privacy-policy.md** / **docs/terms-of-service.md** on the `docs/custom-domain-and-legal` branch for legal text and links.

4. **Branch strategy**
   - Keep **docs/custom-domain-and-legal** for the PR that only has CNAME + PP/ToS + premium links.
   - On this branch, re-apply code changes and commit in small, logical commits (e.g. “Use DatabaseManager in ticketbot”, “Add premium_required_message in premium_guard”, etc.) so nothing is lost again.

---

## Quick reference: what each plan covers

| Plan | Covers |
|------|--------|
| Replace direct DB connections | Pool pattern; which cogs; before/after code; order (ticketbot, embed_watcher, exports, faq, inviteboard, gdpr, status) |
| Premium tier introduction | premium_subs, premium_guard, Core-API, cache, gates (reminders image, growthcheckin spicy), `/premium`, onboarding |
| Changelog 3.0.0 | Full list: DatabaseManager, security env vars, GDPR suite, metrics, founder program, English-only, etc. |

If you want, we can re-apply one cog (e.g. **ticketbot** or **premium**) from the plan step-by-step and then repeat the pattern for the rest.
