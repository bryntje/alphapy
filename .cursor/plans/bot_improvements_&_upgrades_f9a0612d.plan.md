---
name: Bot Improvements & Upgrades
overview: "Implement 7 critical improvements: reminder editing, embed watcher GPT fallback, ticket auto-close, telemetry retry queue, onboarding reorder, GPT fallback handling, and per-guild log levels."
todos:
  - id: reminder_edit
    content: Add /reminder_edit command with modal for all fields (name, time, days, message, channel)
    status: completed
  - id: log_levels
    content: Implement per-guild log levels (verbose/normal/critical) with filtering in log_with_guild
    status: completed
  - id: gpt_fallback
    content: Add GPT fallback message cache and retry queue for rate limits/API errors
    status: completed
  - id: telemetry_queue
    content: Add retry queue for telemetry snapshots with exponential backoff
    status: completed
  - id: embed_gpt_fallback
    content: Add GPT natural language parsing fallback for embed watcher + failed parse logging
    status: completed
  - id: ticket_auto_close
    content: Add idle ticket detection (5d DM reminder, 14d auto-close) with background task
    status: completed
  - id: onboarding_reorder
    content: Add /config onboarding reorder command with numbered list modal
    status: completed
---

# Bot Improvements & Upgrades Plan

## Overview

Implement 7 critical improvements identified from the bot overview document. All new features will be in English to match existing bot language.

## 1. Reminder Editing Command

**File:** `cogs/reminders.py`

**Changes:**

- Add `/reminder_edit <reminder_id>` command
- Create `EditReminderModal` class with fields: name, time, days, message, channel (optional)
- Fetch existing reminder from database
- Pre-fill modal with current values
- Update database row on submit
- Validate ownership (user can only edit their own reminders, admins can edit any)

**Implementation:**

```python
@app_commands.command(name="reminder_edit", description="Edit an existing reminder")
async def reminder_edit(self, interaction: discord.Interaction, reminder_id: int):
    # Fetch reminder, check ownership, show modal
```

**Database:** No schema changes needed (UPDATE existing row)

## 2. Embed Watcher GPT Fallback + Logging

**File:** `cogs/embed_watcher.py`

**Changes:**

- Add `_parse_with_gpt_fallback()` method that calls GPT when structured parsing fails
- GPT prompt: "Extract date, time, days, and location from this event description: {embed_text}. Return JSON: {date, time, days, location}"
- If GPT parsing succeeds, use result; if it also fails, log to admin channel
- Add new setting: `embedwatcher.gpt_fallback_enabled` (default: True)
- Add new setting: `embedwatcher.failed_parse_log_channel_id` (optional, defaults to log_channel_id)

**Implementation:**

- Modify `parse_embed_for_reminder()` to call GPT fallback when `dt is None`
- Add `_log_failed_parse()` method that sends embed to admin channel with original embed content
- Use low temperature (0.1) for GPT parsing to get structured output

**Settings:** Add to `bot.py` settings registration

## 3. Ticket Auto-Close & Idle Detection

**File:** `cogs/ticketbot.py`

**Changes:**

- Add background task `check_idle_tickets()` that runs daily
- Query tickets with status 'open' or 'claimed' where `updated_at < NOW() - INTERVAL '5 days'`
- For idle tickets (5+ days): Send DM to ticket creator and staff with "Ticket idle for 5 days. Close it?" buttons
- For very old tickets (14+ days): Auto-close with summary, post message in channel
- Add new setting: `ticketbot.idle_days_threshold` (default: 5)
- Add new setting: `ticketbot.auto_close_days_threshold` (default: 14)

**Database:** No schema changes (uses existing `updated_at` column)

**Implementation:**

- Add `@tasks.loop(hours=24)` task in `TicketBot.__init__`
- Create `IdleTicketView` with "Close" and "Keep Open" buttons
- Auto-close uses existing `_post_summary()` method

## 4. Telemetry Retry Queue

**File:** `api.py`

**Changes:**

- Add in-memory queue: `_telemetry_queue: List[Dict[str, Any]] = []`
- Modify `_persist_telemetry_snapshot()` to catch exceptions and add to queue
- Add `_flush_telemetry_queue()` method that retries queued items with exponential backoff
- Call `_flush_telemetry_queue()` in `_telemetry_ingest_loop()` after each successful write
- Limit queue size to 100 items (drop oldest if full)
- Add retry counter per item (max 5 retries, then drop)

**Implementation:**

- Use `asyncio.Queue` or simple list with lock
- Exponential backoff: 1s, 2s, 4s, 8s, 16s
- Log queue size in debug logs

## 5. Onboarding Questions Reorder

**File:** `cogs/configuration.py`

**Changes:**

- Add `/config onboarding reorder` command
- Create `ReorderQuestionsModal` with numbered text inputs (one per question)
- User enters question IDs in desired order (e.g., "1, 3, 2, 4")
- Parse input, validate IDs exist, update `step_order` in database
- Show preview before applying changes

**Implementation:**

- Fetch all questions for guild
- Display current order in modal description
- Update `guild_onboarding_questions` table with new `step_order` values
- Clear cache after update

**Database:** No schema changes (uses existing `step_order` column)

## 6. GPT Fallback & Rate Limit Handling

**File:** `gpt/helpers.py`

**Changes:**

- Add cached fallback message: "I'm temporarily unavailable. Please try again in a few minutes."
- Detect rate limit errors (429 status) and API errors (500, 503)
- On error: Return cached message immediately, queue request for retry
- Add `_gpt_retry_queue: List[Dict[str, Any]] = []` for failed requests
- Add background task `_retry_gpt_requests()` that processes queue every 5 minutes
- Limit retry queue to 50 items

**Implementation:**

- Modify `ask_gpt()` to catch specific exceptions (RateLimitError, APIError)
- Return cached message on error, add original request to queue
- Retry queue processes with exponential backoff
- Log retry attempts

## 7. Per-Guild Log Levels

**File:** `utils/logger.py`, `cogs/configuration.py`

**Changes:**

- Add new setting: `system.log_level` (values: "verbose", "normal", "critical")
- Modify `log_with_guild()` to check guild log level before sending to Discord
- Log level mapping:
  - `verbose`: All logs (current behavior)
  - `normal`: info, warning, error, critical (exclude debug)
  - `critical`: Only error and critical + config changes
- Add `/config system set_log_level <level>` command
- Update `_send_audit_log()` in configuration.py to always log (config changes are always critical)

**Settings:** Add to `bot.py`:

```python
SettingDefinition(
    scope="system",
    key="log_level",
    value_type="string",
    default="verbose",
    choices=["verbose", "normal", "critical"]
)
```

**Implementation:**

- Modify all `send_log_embed()` calls to check log level
- Add helper method `_should_log(level: str, guild_id: int) -> bool`

## Implementation Order

1. **Reminder edit** (highest user impact, simple implementation)
2. **Log levels** (reduces noise immediately)
3. **GPT fallback** (improves reliability)
4. **Telemetry queue** (improves data completeness)
5. **Embed watcher GPT fallback** (improves parsing success rate)
6. **Ticket auto-close** (reduces manual work)
7. **Onboarding reorder** (admin convenience)

## Testing Considerations

- Test reminder edit with invalid IDs, ownership checks
- Test GPT fallback with malformed embeds
- Test ticket auto-close with various ticket states
- Test telemetry queue with network failures
- Test log levels with different event types
- All new commands should have proper error handling and user feedback

## Notes

- All user-facing text in English
- Follow existing code patterns (async/await, error handling, logging)
- Use existing database schema where possible
- Add settings via SettingsService registration in `bot.py`
- Update `BOT_OVERVIEW.md` after implementation