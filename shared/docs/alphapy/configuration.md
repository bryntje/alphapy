# Runtime Configuration Guide

This document summarises how to inspect and update Innersync • Alphapy bot settings at runtime.

## Global pattern

All configuration commands live under `/config`. Every subcommand requires admin (same check as the bot's owner/admin roles).

```
/config scopes                      # list available scopes
/config <scope> show                # display current values and overrides
```

When you change a setting it is persisted in the `bot_settings` table so the new value survives restarts. Every change emits an audit embed to the configured log channel.

## Scopes

### `system`
- `log_channel_id` – channel used for audit embeds.

### `embedwatcher`
- `announcements_channel_id`
- `reminder_offset_minutes`

### `reminders`
- `enabled`
- `default_channel_id`
- `allow_everyone_mentions`

Commands:
```
/config reminders show
/config reminders enable|disable
/config reminders set_default_channel <#channel>
/config reminders reset_default_channel
/config reminders set_everyone <true|false>
```

### `ticketbot`
- `category_id`
- `staff_role_id`
- `escalation_role_id`

### `gpt`
- `model`
- `temperature`

### `invites`
- `enabled`
- `announcement_channel_id`
- `with_inviter_template`
- `no_inviter_template`

### `gdpr`
- `enabled`
- `channel_id`

## Notes

- Disable a feature (e.g. `/config invites disable`) to stop listeners without unloading cogs.
- Templates accept `{member}`, `{member_name}`, `{inviter}`, `{inviter_name}`, `{count}` placeholders.
- Settings fall back to values in `config.py` when no override is stored.
- The `SettingsService` supports listeners; cogs subscribe so updates take effect without restart.
