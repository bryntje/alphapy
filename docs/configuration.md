# Multi-Guild Configuration Guide

This document explains how to configure the Innersync • Alphapy bot for each Discord server (guild) where it's added.

## Important: Multi-Guild Architecture

**The bot is completely multi-guild capable.** Each server must be configured independently - there are no automatic fallbacks to hardcoded values. Every channel, role, and setting must be explicitly configured per server.

## First-Time Setup (Required for each new server)

**Quick start:** Use **`/config start`** for an interactive setup. The bot will ask for each important setting (log channel, rules and onboarding channel, embed watcher, invites, GDPR, ticket category, staff role); you choose a channel or role from the dropdown or click **Skip**. All prompts are in English.

Alternatively, run the following commands in order:

### 1. System Configuration
```bash
# Set the log channel for bot messages and errors
/config system set_log_channel #logs

# Set the rules and onboarding channel (welcome message + Start button)
/config system set_rules_channel #rules
```

### 2. Feature-Specific Configuration

#### Embed Watcher (Auto-Reminders)
```bash
# Set channel to monitor for announcement embeds
/config embedwatcher set_announcements #announcements
```

#### Invite Tracker
```bash
# Set channel for invite announcements
/config invites set_channel #invites
```

#### GDPR Compliance
```bash
# Set channel for GDPR documents
/config gdpr set_channel #gdpr
```

#### Ticket System
```bash
# Set category for ticket channels (required)
/config ticketbot set_category [category]

# Set staff role for ticket access
/config ticketbot set_staff_role @Staff

# Set escalation role for urgent tickets
/config ticketbot set_escalation_role @Moderators
```

### 3. Optional Settings

#### Reminders
```bash
# Allow @everyone mentions in reminders (use carefully!)
/config reminders set_everyone true

# Set default channel for manual reminders
/config reminders set_default_channel #general
```

#### GPT Settings
```bash
# Choose AI model
/config gpt set_model gpt-4  # or gpt-3.5-turbo

# Set creativity level (0.0-2.0)
/config gpt set_temperature 0.7
```

## Configuration Commands Reference

### Global Pattern
All commands require administrator permissions and are guild-specific:

```
/config scopes                    # List all available scopes
/config <scope> show              # Show current settings for this guild
```

### System Scope
```
/config system show
/config system set_log_channel <#channel>
/config system reset_log_channel
/config system set_rules_channel <#channel>
/config system reset_rules_channel
```

### Embed Watcher Scope
```
/config embedwatcher show
/config embedwatcher set_announcements <#channel>
/config embedwatcher reset_announcements
/config embedwatcher set_offset <minutes>
/config embedwatcher reset_offset
/config embedwatcher set_non_embed <true|false>
/config embedwatcher reset_non_embed
/config embedwatcher set_process_bot_messages <true|false>
/config embedwatcher reset_process_bot_messages
```

### Reminders Scope
```
/config reminders show
/config reminders enable|disable
/config reminders set_default_channel <#channel>
/config reminders reset_default_channel
/config reminders set_everyone <true|false>
```

### TicketBot Scope
```
/config ticketbot show
/config ticketbot set_category <#category>
/config ticketbot reset_category
/config ticketbot set_staff_role @<role>
/config ticketbot reset_staff_role
/config ticketbot set_escalation_role @<role>
/config ticketbot reset_escalation_role
```

### GPT Scope
```
/config gpt show
/config gpt set_model <model-name>
/config gpt reset_model
/config gpt set_temperature <0.0-2.0>
/config gpt reset_temperature
```

### Invites Scope
```
/config invites show
/config invites enable|disable
/config invites set_channel <#channel>
/config invites reset_channel
/config invites set_template <variant> <template>
/config invites reset_template <variant>
```
Variant is "with inviter" or "without inviter" (dropdown).

### GDPR Scope
```
/config gdpr show
/config gdpr enable|disable
/config gdpr set_channel <#channel>
/config gdpr reset_channel
```

### Onboarding Scope
```
/config onboarding show
/config onboarding enable|disable
/config onboarding set_mode <mode>
/config onboarding add_question <step> <question> [question_type] [required]
/config onboarding delete_question <step>
/config onboarding reset_questions
/config onboarding add_rule <rule_order> <title> <description> [thumbnail_url] [image_url]
/config onboarding delete_rule <rule_order>
/config onboarding reset_rules
/config onboarding set_role <#role>
/config onboarding reset_role
/config onboarding panel_post [channel]
/config onboarding reorder
```
`reorder` opens a modal to enter question IDs in the desired order. `panel_post` optionally takes a channel; otherwise posts in the current channel.

**Onboarding modes** (via `mode`):
- **Disabled** – No onboarding
- **Rules Only** – Role assigned when rules are accepted (no questions)
- **Rules + Questions** – Role assigned only after all questions (and personalization steps) are completed
- **Questions Only** – Role assigned only after all questions (and personalization steps) are completed

When questions are used, users also complete two fixed personalization steps: opt-in for personalized reminders and preferred language; stored in `onboarding.responses` as `personalized_opt_in` and `preferred_language`.

Rules support optional images: `thumbnail_url` (shown right) and `image_url` (shown at bottom). If no rules are configured, users see an error and a log is sent to the log channel.

### FYI (contextual tips – testing)
The bot sends short FYI tips when certain first-time events happen (e.g. first onboarding completed, first reminder, first ticket, bot joined server). Tips are sent at most once per guild per type and respect a 24h per-guild cooldown. For testing or to re-send a tip:
```
/config fyi reset <key>   # Clear the flag so the next trigger will send again
/config fyi send <key>    # Force-send the tip to the log channel now
```
Key is chosen from a dropdown (e.g. `first_onboarding_done`, `first_guild_join`). Administrator only.

## Template Placeholders

For invite templates, you can use:
- `{member}` - Mention the new member
- `{member_name}` - Name of the new member
- `{inviter}` - Mention the inviter
- `{inviter_name}` - Name of the inviter
- `{count}` - Total invite count

Example:
```
/config invites set_template "Met inviter" "{member} joined! {inviter} now has {count} invites."
```

## Troubleshooting

### "Channel not configured" errors
- Run the setup commands above for your server
- Check `/config system show` to verify settings

### Bot not responding to embeds/announcements
- Verify `/config embedwatcher set_announcements` is set to the correct channel
- Ensure bot has read permissions in that channel

### Import commands failing
- Set appropriate channels first (log channel for imports)
- Owner permissions required for import commands

## Environment Variables

The following environment variables are required/optional for bot operation:

### Required
- `BOT_TOKEN`: Discord bot token
- `DATABASE_URL`: PostgreSQL connection string

### Optional - Google Cloud (for Drive integration)
- `GOOGLE_PROJECT_ID`: GCP project ID for Secret Manager (production)
- `GOOGLE_SECRET_NAME`: Secret name in Secret Manager (default: "alphapy-google-credentials")
- `GOOGLE_CREDENTIALS_JSON`: Service account credentials JSON string (local dev fallback)

**Note**: In production, use Secret Manager (`GOOGLE_PROJECT_ID`). For local development, `GOOGLE_CREDENTIALS_JSON` can be used as fallback. See [docs/SECURITY.md](SECURITY.md) for security best practices.

### Optional - API & Authentication
- `API_KEY`: Internal API key for API endpoints
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_ANON_KEY`: Supabase anonymous key
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service role key

### Optional - AI/LLM
- `GROK_API_KEY`: Grok API key (or `OPENAI_API_KEY` for OpenAI)
- `LLM_PROVIDER`: "grok" or "openai" (default: "grok")

### Optional - Core API (telemetry / operational events)
- `CORE_API_URL`: Base URL of the Core API for centralised telemetry and operational event ingress. When set, operational events and telemetry are sent to Core instead of directly to Supabase.
- `ALPHAPY_SERVICE_KEY`: Service key for authenticating with the Core API.

## Migration Notes

If upgrading from single-guild to multi-guild:
1. All old config.py values are now deprecated
2. Each server needs fresh `/config` setup
3. No automatic migration of old settings
4. Bot automatically detects all joined servers