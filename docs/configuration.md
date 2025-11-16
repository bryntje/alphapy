# Multi-Guild Configuration Guide

This document explains how to configure the Innersync • Alphapy bot for each Discord server (guild) where it's added.

## Important: Multi-Guild Architecture

**The bot is completely multi-guild capable.** Each server must be configured independently - there are no automatic fallbacks to hardcoded values. Every channel, role, and setting must be explicitly configured per server.

## First-Time Setup (Required for each new server)

When you add the bot to a new Discord server, run these commands in order:

### 1. System Configuration
```bash
# Set the log channel for bot messages and errors
/config system set_log_channel #logs

# Set the rules channel for onboarding
/config system set_rules_channel #rules

# Set the onboarding channel for welcome messages
/config system set_onboarding_channel #welcome
```

### 2. Feature-Specific Configuration

#### Embed Watcher (Auto-Reminders)
```bash
# Set channel to monitor for announcement embeds
/config embedwatcher announcements_channel_id #announcements
```

#### Invite Tracker
```bash
# Set channel for invite announcements
/config invites announcement_channel_id #invites
```

#### GDPR Compliance
```bash
# Set channel for GDPR documents
/config gdpr channel_id #gdpr
```

#### Ticket System
```bash
# Set category for ticket channels (required)
/config ticketbot category_id [category-id]

# Set staff role for ticket access
/config ticketbot staff_role_id @Staff

# Set escalation role for urgent tickets
/config ticketbot escalation_role_id @Moderators
```

### 3. Optional Settings

#### Reminders
```bash
# Allow @everyone mentions in reminders (use carefully!)
/config reminders allow_everyone_mentions true

# Set default channel for manual reminders
/config reminders default_channel_id #general
```

#### GPT Settings
```bash
# Choose AI model
/config gpt model gpt-4  # or gpt-3.5-turbo

# Set creativity level (0.0-2.0)
/config gpt temperature 0.7
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
/config system set_onboarding_channel <#channel>
/config system reset_onboarding_channel
```

### Embed Watcher Scope
```
/config embedwatcher show
/config embedwatcher announcements_channel_id <#channel>
/config embedwatcher reset_announcements_channel
/config embedwatcher reminder_offset_minutes <minutes>
```

### Reminders Scope
```
/config reminders show
/config reminders enable|disable
/config reminders set_default_channel <#channel>
/config reminders reset_default_channel
/config reminders allow_everyone_mentions <true|false>
```

### TicketBot Scope
```
/config ticketbot show
/config ticketbot category_id <category-id>
/config ticketbot reset_category
/config ticketbot staff_role_id @<role>
/config ticketbot reset_staff_role
/config ticketbot escalation_role_id @<role>
/config ticketbot reset_escalation_role
```

### GPT Scope
```
/config gpt show
/config gpt model <model-name>
/config gpt temperature <0.0-2.0>
```

### Invites Scope
```
/config invites show
/config invites enable|disable
/config invites announcement_channel_id <#channel>
/config invites reset_announcement_channel
/config invites with_inviter_template "<template>"
/config invites no_inviter_template "<template>"
```

### GDPR Scope
```
/config gdpr show
/config gdpr enable|disable
/config gdpr channel_id <#channel>
/config gdpr reset_channel
```

## Template Placeholders

For invite templates, you can use:
- `{member}` - Mention the new member
- `{member_name}` - Name of the new member
- `{inviter}` - Mention the inviter
- `{inviter_name}` - Name of the inviter
- `{count}` - Total invite count

Example:
```
/config invites with_inviter_template "{member} joined! {inviter} now has {count} invites."
```

## Troubleshooting

### "Channel not configured" errors
- Run the setup commands above for your server
- Check `/config system show` to verify settings

### Bot not responding to embeds/announcements
- Verify `/config embedwatcher announcements_channel_id` is set
- Ensure bot has read permissions in that channel

### Import commands failing
- Set appropriate channels first (log channel for imports)
- Owner permissions required for import commands

## Migration Notes

If upgrading from single-guild to multi-guild:
1. All old config.py values are now deprecated
2. Each server needs fresh `/config` setup
3. No automatic migration of old settings
4. Bot automatically detects all joined servers