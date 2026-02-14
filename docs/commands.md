# Command Reference

Complete reference for all Discord slash commands available in the Alphapy bot.

## Command Categories

- [Core Utilities](#core-utilities)
- [Reminders](#reminders)
- [Tickets](#tickets)
- [Configuration](#configuration)
- [AI Features](#ai-features)
- [System](#system)
- [Admin](#admin)

---

## Core Utilities

### `/sendto`
Send a message to a specific channel with support for newlines.

**Parameters:**
- `channel` (required): The channel where the message should be sent
- `message` (required): The message to send. Use `\n` for a new line.

**Example:**
```
/sendto channel:#general message:"Hello\ncommunity!"
```

**Permissions:** Owner/Admin

---

### `/embed`
Create and send a simple embed to a channel.

**Parameters:**
- `channel` (required): The channel where the embed should be sent

**Behavior:** Opens a modal to create the embed with title, description, footer, and color fields.

**Permissions:** Owner/Admin

---

### `/clean`
Delete messages from a channel.

**Parameters:**
- `limit` (required): Number of messages to delete (max 100)

**Permissions:** Owner/Admin

---

## Reminders

### `/add_reminder`
Schedule a recurring or one-off reminder via form or message link.

**Parameters:**
- `name` (required): Name of the reminder
- `channel` (optional): Channel where reminder should be sent (uses default if not set)
- `time` (required): Time in HH:MM format
- `days` (optional): Days of the week (e.g., "Monday, Wednesday, Friday")
- `message` (optional): Reminder message content
- `location` (optional): Event location
- `message_link` (optional): Link to a message/embed to parse details from

**Examples:**
```
/add_reminder name:"Weekly Standup" time:"09:00" days:"Monday, Wednesday, Friday" message:"Daily standup meeting"
/add_reminder name:"Event" time:"19:30" message_link:"https://discord.com/channels/..."
```

---

### `/reminder_list`
View your active reminders.

**Parameters:**
- `user` (optional): View reminders for a specific user (admin only)

**Response:** Lists all active reminders with ID, name, time, days, and channel.

---

### `/reminder_edit`
Edit an existing reminder.

**Parameters:**
- `reminder_id` (required): ID of the reminder to edit

**Behavior:** Opens a modal with pre-filled fields (name, time, days, message, channel_id) that can be edited.

**Permissions:** Owner/Admin or reminder creator

---

### `/reminder_delete`
Delete a reminder by ID.

**Parameters:**
- `reminder_id` (required): ID of the reminder to delete

**Permissions:** Owner/Admin or reminder creator

---

## Tickets

### `/ticket`
Create a support ticket (private channel per ticket).

**Parameters:**
- `description` (required): Short description of your issue

**Behavior:** Creates a private channel under the configured ticket category with restricted access (requester + staff role). In the ticket channel, staff can use **Claim** and **Close** buttons (not slash commands) to manage the ticket.

---

### `/ticket_panel_post`
Post a persistent "Create ticket" panel (admins only).

**Behavior:** Posts an embed with a "Create ticket" button that users can click to create tickets.

**Permissions:** Owner/Admin

---

### `/ticket_stats`
Show ticket statistics (admins only).

**Behavior:** Shows interactive buttons to view stats for 7 days, 30 days, or all time.

**Permissions:** Owner/Admin

---

### `/ticket_status`
Update a ticket status (admins only).

**Parameters:**
- `ticket_id` (required): ID of the ticket
- `status` (required): New status (open, claimed, waiting_for_user, escalated, closed)

**Permissions:** Owner/Admin

---

## Configuration

### `/config`
Manage bot settings (multi-scope configuration system).

- **`/config start`** – Start the interactive server setup. The bot guides you step-by-step through the main settings (log channel, rules channel, onboarding, embed watcher, invites, GDPR, ticket category, staff role). Choose a channel or role from the dropdown or click **Skip**. All prompts in English.

**Subcommands:**

#### System Settings
- `/config system show` - Show current system settings
- `/config system set_log_channel <#channel>` - Set log channel
- `/config system set_rules_channel <#channel>` - Set rules channel
- `/config system set_onboarding_channel <#channel>` - Set onboarding channel
- `/config system reset_log_channel` - Reset log channel
- `/config system reset_rules_channel` - Reset rules channel
- `/config system reset_onboarding_channel` - Reset onboarding channel

#### Embed Watcher Settings
- `/config embedwatcher show` - Show current settings
- `/config embedwatcher announcements_channel_id <#channel>` - Set announcements channel
- `/config embedwatcher reminder_offset_minutes <minutes>` - Set reminder offset (default: 60)
- `/config embedwatcher process_bot_messages <true|false>` - Enable/disable processing bot messages

#### Reminder Settings
- `/config reminders show` - Show current settings
- `/config reminders enable|disable` - Enable/disable reminders
- `/config reminders set_default_channel <#channel>` - Set default reminder channel
- `/config reminders allow_everyone_mentions <true|false>` - Allow @everyone mentions

#### TicketBot Settings
- `/config ticketbot show` - Show current settings
- `/config ticketbot category_id <category-id>` - Set ticket category
- `/config ticketbot staff_role_id @<role>` - Set staff role
- `/config ticketbot escalation_role_id @<role>` - Set escalation role

#### GPT Settings
- `/config gpt show` - Show current settings
- `/config gpt model <model-name>` - Set AI model (e.g., "grok-3", "gpt-4")
- `/config gpt temperature <0.0-2.0>` - Set AI creativity level

#### Invites Settings
- `/config invites show` - Show current settings
- `/config invites enable|disable` - Enable/disable invite tracking
- `/config invites announcement_channel_id <#channel>` - Set announcement channel
- `/config invites with_inviter_template "<template>"` - Set template with inviter
- `/config invites no_inviter_template "<template>"` - Set template without inviter

#### GDPR Settings
- `/config gdpr show` - Show current settings
- `/config gdpr enable|disable` - Enable/disable GDPR features
- `/config gdpr channel_id <#channel>` - Set GDPR channel

#### Onboarding Settings
- `/config onboarding show` - Show current settings
- `/config onboarding enable|disable` - Enable/disable onboarding
- `/config onboarding mode <mode>` - Set onboarding mode
- `/config onboarding add_rule` - Add a rule (supports optional `thumbnail_url` and `image_url`)
- `/config onboarding delete_rule` - Delete a rule
- `/config onboarding reset_rules` - Reset to empty rules
- `/config onboarding set_role` - Set completion role
- `/config onboarding reset_role` - Remove completion role

**Permissions:** Administrator (all `/config` commands)

---

## AI Features

### `/growthcheckin`
GPT-powered check-in for goals, obstacles, and emotions.

**Behavior:** Opens a modal with questions about goals, obstacles, and feelings. Responses are processed by GPT and stored for reflection.

---

### `/learn_topic`
Hybrid topic search using local knowledge base + Drive content.

**Parameters:**
- `topic` (required): Topic to learn about

**Behavior:** Searches local `.md` files and Google Drive content, then generates a comprehensive explanation using GPT.

---

### `/create_caption`
Generate social media captions based on topic and style.

**Parameters:**
- `topic` (required): Topic for the caption
- `style` (optional): Caption style/tone

**Behavior:** Generates a caption using GPT based on the provided topic and style.

---

### `/lotquiz`
Test your risk management across 3 forex scenarios.

**Behavior:** Interactive quiz that presents 3 trading scenarios and evaluates risk management decisions.

---

### `/leaderhelp`
AI-powered leadership guidance for challenges, team growth, or doubts.

**Behavior:** Opens a view to choose a challenge type (e.g., disengaged team, burnout, dropoff, self-doubt) or ask a custom question. Responses are generated by GPT.

**Permissions:** Public (with cooldown)

---

## System

### `/gptstatus`
Check the status of the GPT API.

**Response:** Shows last success time, error count, average latency, token usage, and current model.

---

### `/version`
Show bot version and codename.

**Response:** Current version (e.g., "2.2.0 - Lifecycle Manager")

---

### `/release`
Show release notes for the current version.

**Response:** Release notes from `RELEASES.md`

---

### `/health`
Show system status and configuration.

**Response:** Bot status, database status, guild count, and configuration overview.

---

### `/commands`
List all available bot commands.

**Parameters:**
- `include_admin` (optional, default: False): Include admin-only commands in the list
- `public` (optional, default: False): Post in channel instead of ephemeral

**Response:** Nicely formatted embed listing commands by category.

---

### `/command_stats`
Show command usage statistics (admin only).

**Parameters:**
- `days` (optional, default: 7): Number of days to look back
- `limit` (optional, default: 10): Maximum number of commands to show
- `guild_only` (optional, default: True): Show stats for current server only, or all servers (owner only)

**Response:** Rich embed showing top commands by usage, total commands executed, period, and scope.

**Permissions:** Administrator (or bot owner for all-server stats)

**Example:**
```
/command_stats days:7 limit:10 guild_only:True
```

---

## Admin

### `/migrate`
Database migration management (admins only).

**Parameters:**
- `action` (required): Action to perform (`status`, `upgrade`, `downgrade`, `history`)

**Examples:**
```
/migrate action:status
/migrate action:upgrade
/migrate action:history
```

**Permissions:** Owner/Admin

---

### `/migrate_status`
Check database migration status (alias for `/migrate status`).

**Permissions:** Owner/Admin

---

### `/reload`
Reload a specific extension (owner only).

**Parameters:**
- `extension` (required): Name of the extension to reload (e.g., "cogs.reminders")

**Permissions:** Owner only

---

### `/export_onboarding`
Export onboarding data as CSV (owner only).

**Response:** CSV file download with all onboarding responses.

**Permissions:** Owner only

---

### `/export_tickets`
Export tickets as CSV (admins only).

**Response:** CSV file download with all ticket data.

**Permissions:** Owner/Admin

---

### `/export_faq`
Export FAQ entries as CSV (admins only).

**Response:** CSV file download with all FAQ entries.

**Permissions:** Owner/Admin

---

### `/inviteleaderboard`
Show invite leaderboard.

**Response:** Leaderboard of users with highest invite counts.

---

### `/setinvites`
Manually set invite count for a user.

**Parameters:**
- `user` (required): User to set invites for
- `count` (required): Number of invites

**Permissions:** Owner/Admin

---

### `/resetinvites`
Reset invite count for a user to 0.

**Parameters:**
- `user` (required): User to reset invites for

**Permissions:** Owner/Admin

---

### `/debug_parse_embed`
Parse the last embed in the channel for testing.

**Behavior:** Attempts to parse the last embed message in the channel and shows the parsed result.

**Permissions:** Owner/Admin

---

## Permission Levels

- **Public**: Available to all users
- **Admin**: Requires administrator permissions or admin role
- **Owner**: Bot owner only (configured in `config.py`)

Most commands respect Discord's permission system and guild-specific admin roles configured via `/config` commands.
