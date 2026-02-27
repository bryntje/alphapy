# 🎨 Embed Styling Guide

Centralized embed styling guidelines for the Innersync • Alphapy bot.

All informative embeds (e.g. `/reminder_list`, `/command_stats`, `/gptstatus`) should follow these patterns for consistency and readability.

## Basic structure

```python
embed = discord.Embed(
    title="📋 [Title with emoji]",
    description="[Short description or summary]",
    color=discord.Color.blue(),  # See colors below
    timestamp=datetime.now(BRUSSELS_TZ)  # Always timestamp for context
)
```

## Colors

Use the following colors for different types of information:

- **Blue (`discord.Color.blue()`)**: Default informative embeds  
  Examples: `/reminder_list`, `/command_stats`, general information
- **Orange (`discord.Color.orange()`)**: Warnings or empty states  
  Examples: "No reminders found", "No commands executed"
- **Green (`discord.Color.green()`)**: Successful actions or positive status  
  Examples: Successful operations, "All systems operational"
- **Red (`discord.Color.red()`)**: Errors or critical warnings  
  Examples: Errors, failed operations
- **Teal (`discord.Color.teal()`)**: Status information  
  Examples: `/gptstatus` (Grok/LLM status), system status

## Fields

- **Emojis for visual hierarchy**: `📅`, `⏰`, `📍`, `📺`, `🔄`, `📌`, etc.
- **Field names**: Short and descriptive with emoji prefix  
  Good: `📅 Period`, `🔄 Recurring (5)`, `📌 One-off (2)`  
  Avoid: `Period:`, `Recurring reminders:`
- **Field values**:
  - Use `\n` for multiple items
  - Format: `**Item Name**\nDetails...`
  - For lists: numbering with `1.`, `2.`, etc. or bullets with `•`
- **Inline fields**: Use `inline=True` for related information that can sit side by side (max 3 per row)
- **Max length**: Field values should not exceed 1024 characters.

## Footer

Always include a footer with at least one of:

- Version info: `f"v{__version__} — {CODENAME}"`
- Action hints: e.g. `"Use /reminder_edit <id> to edit or /reminder_delete <id> to delete"`
- Module identification: e.g. `f"reminders | Guild: {guild_id}"`

## Examples

### Reminder List

```python
embed = discord.Embed(
    title="📋 Active Reminders",
    description=f"Found **{len(rows)}** reminder{'s' if len(rows) != 1 else ''}",
    color=discord.Color.blue(),
    timestamp=datetime.now(BRUSSELS_TZ)
)
embed.add_field(
    name=f"🔄 Recurring ({len(recurring)})",
    value="\n\n".join(formatted_reminders),
    inline=False
)
embed.set_footer(text="Use /reminder_edit <id> to edit or /reminder_delete <id> to delete")
```

### Command Statistics

```python
embed = discord.Embed(
    title="📊 Command Usage Statistics",
    color=discord.Color.blue(),
    timestamp=datetime.now(BRUSSELS_TZ)
)
embed.add_field(name="📅 Period", value=f"Last {days} day{'s' if days != 1 else ''}", inline=True)
embed.add_field(name="🌐 Scope", value=scope_text, inline=True)
embed.set_footer(text=f"v{__version__} — {CODENAME}")
```

## Best practices

1. **Consistency**
   - ⏰ for time
   - 📅 for dates/days
   - 📍 for locations
   - 📺 for channels
   - 🔄 for recurring items
   - 📌 for one-off items

2. **Readability**
   - Use `**bold**` for important information
   - Use `\n` for clear separation between items

3. **Context**
   - Always add a timestamp for time-sensitive information
   - Include a footer with relevant actions or version info

4. **Empty states**
   - Use orange color for "no results" states
   - Prefer clear descriptions like "No reminders found."

