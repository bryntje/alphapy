# 🤖 Alphapy Discord Bot

A powerful, modular Discord bot for conscious communities — practical server tools combined with AI features for growth coaching and knowledge sharing.

**🔗 Related repositories:**
- 🌐 **[alphapy-dashboard](https://github.com/bryntje/alphapy-dashboard)** - Next.js web interface for configuration

---

## 🌱 Overview

**Alphapy** is a Discord bot built for the Innersync • Alphapips community, focused on value-driven trading workflows and personal growth.

The bot combines essential Discord utilities with an optional AI layer:

- 🧘‍♂️ **Growth coaching** via `/growthcheckin`
- 🧠 **Hybrid knowledge search** via `/learn_topic`
- ✍️ **Caption generation** via `/create_caption`
- 🎫 **Ticket system** for support
- ⏰ **Smart reminders** with auto-detection from embeds
- 📊 **Metrics & dashboards** API with command analytics
- 🔄 **Database migrations** with Alembic
- 🧪 **Test infrastructure** with pytest

---

## 📁 Project Structure

```plaintext
alphapy/
├── bot.py                # Main Discord bot runner
├── api.py                # FastAPI server for metrics/dashboard API
├── cogs/                 # Bot command modules (30+ commands)
│   ├── growth.py         # AI growth coaching (/growthcheckin)
│   ├── learn.py          # Hybrid knowledge search (/learn_topic)
│   ├── ticketbot.py      # Support ticket system
│   ├── reminders.py      # Scheduled reminders with edit support
│   ├── embed_watcher.py  # Auto-reminder detection from embeds
│   ├── migrations.py     # Database migration management
│   └── ...               # 24+ other commands
├── utils/                # Core utilities (13 modules)
│   ├── supabase_client.py # Database connectivity
│   ├── runtime_metrics.py # Live bot metrics
│   ├── command_tracker.py # Command usage analytics
│   └── ...               # Logging, timezone, quiz state, etc.
├── gpt/                  # AI functionality
│   ├── helpers.py        # GPT API calls + retry queue
│   └── dataset_loader.py # Content loading for learn_topic
├── tests/                # Test suite
│   ├── test_embed_watcher_parsing.py
│   ├── test_reminder_parsing.py
│   └── conftest.py       # Test fixtures
├── alembic/              # Database migrations
│   ├── versions/         # Migration files
│   └── env.py            # Alembic configuration
├── data/prompts/         # Local knowledge base (.md files)
├── webhooks/             # Supabase webhooks
├── docs/                 # Documentation
├── requirements.txt      # Python dependencies
├── config.py             # Bot configuration
└── .github/workflows/    # CI/CD pipelines
```

**🎯 Clean separation:** Bot logic ↔ Web interface ↔ Database

---

## 🚀 Installation

### Prerequisites
- Python 3.9+
- Discord Bot Token
- PostgreSQL database (via Supabase or standalone)
- (Optional) OpenAI/Grok API key for AI features

### Setup Steps

1. **Clone deze repository:**
```bash
git clone https://github.com/bryntje/alphapy.git
cd alphapy
```

2. **Installeer dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure the bot:**
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials:
# - BOT_TOKEN=your_bot_token
# - DATABASE_URL=postgresql://user:pass@host:port/database
# - GROK_API_KEY=your_grok_key (or OPENAI_API_KEY)
# - (Optional) API_KEY=your_api_key
# - (Optional) GOOGLE_PROJECT_ID=your-gcp-project-id (for Secret Manager)
# - (Optional) GOOGLE_CREDENTIALS_JSON={"type":"service_account",...} (local dev fallback)
```

4. **Run database migrations (if needed):**
```bash
# For existing databases, mark baseline as applied:
alembic stamp head

# For new databases, apply all migrations:
alembic upgrade head
```

5. **Run the bot:**
```bash
python bot.py
```

### 🧪 Running Tests
```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_embed_watcher_parsing.py -v
```

### 🚀 Deployment
- **Local development:** `python bot.py`
- **Railway:** Configure a Python service running `python bot.py`
- **Environment variables:** All vars from `.env`
- **Database migrations:** Run `alembic upgrade head` on deployment

---

## 💡 Slash Commands

```plaintext
/growthcheckin     → GPT-coach for goals, obstacles and emotions
/learn_topic       → Hybrid topic search using local + Drive content
/leaderhelp        → AI-powered leadership guidance
/create_caption    → Generate 1-liner captions based on tone & topic
/ticket            → Create a support ticket (private channel per ticket)
/ticket_stats      → Show ticket statistics (admins)
/ticket_status     → Update ticket status (admins)
/ticket_panel_post → Post a persistent “Create ticket” panel (admins)
```

> Claim and Close tickets via **buttons** in the ticket channel, not slash commands.

> The AI layer is modular and optional — for teams that want to deepen reflection, personalize learning, or co-create content using GPT.

---

## ⏰ Reminders (one-off & recurring)

- One-off events (from embeds) store a concrete `event_time` and empty `days`.
  - Trigger at T−60 (scheduler `time`) and at T0 (`event_time::time`).
  - Embed displays the event clock via `call_time`.
  - Deleted after the T0 send.
- Recurring events store `days` (0=Mon..6=Sun) and a daily `time`.
  - Trigger when `current_day ∈ days` at `time`.
  - Not deleted.
- Idempotency: reminders won’t send twice in the same minute (tracked via `last_sent_at`).
- Logging: major events (created/sent/deleted/errors) are also posted to `WATCHER_LOG_CHANNEL`.

---

## 🎟️ TicketBot

- Per-ticket channels created under `TICKET_CATEGORY_ID` with restricted access (requester + support role)
- Interactive buttons in the ticket channel:
  - Claim ticket (staff only)
  - Close ticket (locks channel, optional rename, posts GPT summary)
  - Delete ticket (staff only; visible after close)
- GPT summary on close using `gpt/helpers.ask_gpt`; summaries are stored in `ticket_summaries`
- Repeated-topic detection proposes adding an FAQ entry; admins can click “Add to FAQ” (stored in `faq_entries`)
- Admins can post a persistent panel with `/ticket_panel_post` that includes a “Create ticket” button

### Usage: buttons in the ticket channel
- Claim ticket (staff only): assigns the ticket to the clicker; button becomes “Claimed”.
- Close ticket (staff only): locks channel for the requester, optionally renames to `ticket-<id>-closed`, posts a GPT summary embed, enables the Delete button.
- Delete ticket (staff only, visible after close): deletes DB records for the ticket and removes the channel.
- Wait for user (staff only): sets status to `waiting_for_user`.
- Escalate (staff only): sets status to `escalated` (optionally stores target role).
- 💡 Suggest reply (staff only): drafts an ephemeral assistant reply based on recent messages.

### FAQ workflow
- On close, the GPT summary is saved in `ticket_summaries` with a computed similarity key.
- If 3 or more similar summaries appear within 7 days, a proposal embed is posted to `WATCHER_LOG_CHANNEL` with an “Add to FAQ” button.
- Admins can click “Add to FAQ” to store an entry in `faq_entries` for later surfacing.

### Admin permissions
- “staff” checks rely on `is_owner_or_admin_interaction`:
  - Bot owner or IDs in `OWNER_IDS`, or users with `ADMIN_ROLE_ID` (or the configured `TICKET_ACCESS_ROLE_ID`).
- Staff-only actions: `/ticket_panel_post`, `/ticket_stats`, `/ticket_status`, plus Claim/Close/Delete buttons in the ticket channel.

### Env
- `TICKET_CATEGORY_ID`: category under which ticket channels are created
- `TICKET_ACCESS_ROLE_ID`: role with access to ticket channels (falls back to `ADMIN_ROLE_ID`)
- `TICKET_ESCALATION_ROLE_ID`: optional role used as escalation target

### Minimal test plan
1. Run `/ticket_panel_post` in a channel to publish the panel; click “Create ticket”
2. In the ticket channel, click Claim, then Close
3. Confirm summary embed posts; Delete button becomes available for admins
4. Repeat with similar issues to trigger FAQ proposal in `WATCHER_LOG_CHANNEL`

---

## 🧪 Testing

The project includes comprehensive test coverage:

- **Unit tests** for embed parsing (`tests/test_embed_watcher_parsing.py`)
- **Unit tests** for reminder logic (`tests/test_reminder_parsing.py`)
- **Test fixtures** for Discord objects and database mocks (`tests/conftest.py`)
- **53 tests** covering parsing, timing, and edge cases

Run tests with:
```bash
pytest tests/ -v
```

## 🔄 Database Migrations

The project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema management:

- **Baseline migration** (`001_initial_schema.py`) documents all existing tables
- **Migration commands** via `/migrate` and `/migrate_status` Discord commands
- **Migration guide** in `docs/migrations.md`

See [docs/migrations.md](docs/migrations.md) for complete migration workflow.

## 📊 Analytics & Monitoring

### Command Usage Analytics
- All commands are automatically tracked in `audit_logs` table
- View top commands via `/top-commands` API endpoint
- Command statistics included in dashboard metrics

### Health Monitoring
- Enhanced `/api/health` endpoint with detailed metrics
- Health check history stored in `health_check_history` table
- Historical trends available via `/api/health/history`

### Telemetry
- Background telemetry ingest job writes metrics to Supabase every 30-60 seconds
- Real-time bot status, latency, throughput, error rates
- Integrated with Mind dashboard for monitoring

---

## 🌐 API Endpoints

The bot includes a FastAPI server for metrics, health checks, and analytics:

### Health & Status
- `GET /api/health` – Enhanced health probe with uptime, database status, guild count, command usage, GPT status
- `GET /api/health/history` – Historical health check data for trend analysis

### Metrics & Analytics
- `GET /api/dashboard/metrics` – Live bot metrics (latency, guilds, commands, GPT stats, reminders, tickets)
- `GET /top-commands` – Command usage analytics (top commands by usage, filterable by guild and time period)

### Reminder Management
- `GET /api/reminders` – List reminders for a user (requires API key + `X-User-Id`)
- `POST /api/reminders` – Create a reminder (requires API key + `X-User-Id`)
- `PUT /api/reminders/{id}` – Update a reminder (requires API key + `X-User-Id`)
- `DELETE /api/reminders/{id}` – Delete a reminder (requires API key + `X-User-Id`)

### Exports
- `GET /export_tickets` – CSV export of tickets
- `GET /export_faq` – CSV export of FAQ entries

**⚠️ Important:** For the **full web dashboard** (charts, configuration UI), see:
**👉 [alphapy-dashboard repository](https://github.com/bryntje/alphapy-dashboard)**

### Environment Variables

```bash
# Discord Bot
DISCORD_TOKEN=your_bot_token_here

# Supabase Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_key

# Google Cloud (for Drive integration)
# Production: Use Secret Manager (recommended)
GOOGLE_PROJECT_ID=your-gcp-project-id
GOOGLE_SECRET_NAME=alphapy-google-credentials  # Optional, defaults to "alphapy-google-credentials"
# Local development: Fallback to environment variable
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}  # JSON string of service account credentials

# Optional API Security
API_KEY=optional_internal_key
```

**Note**: In production, credentials are stored in Google Cloud Secret Manager. The `GOOGLE_CREDENTIALS_JSON` environment variable is only used as a fallback for local development. See [docs/SECURITY.md](docs/SECURITY.md) for security best practices.


## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐
│   alphapy       │    │ alphapy-dashboard │
│   (Discord Bot) │    │  (Next.js Web)   │
├─────────────────┤    ├──────────────────┤
│ • 30+ Commands  │    │ • Config UI      │
│ • AI Features   │◄──►│ • Live Metrics   │
│ • Ticket System │    │ • Admin Panel    │
│ • Reminders     │    │ • Charts         │
│ • Analytics     │    │ • API Proxy      │
│ • Migrations    │    │                  │
│ • Tests         │    │                  │
│ • Database      │    │                  │
│ • Webhooks      │    │                  │
└─────────────────┘    └──────────────────┘
        │                       │
        └────── Supabase ───────┘
```

**Clean separation:** Bot logic ↔ Web interface ↔ Database

## 🤝 Contributing

We welcome devs, thinkers, and conscious builders.

- Fork this repo (of [alphapy-dashboard](https://github.com/bryntje/alphapy-dashboard))
- Create branch: `git checkout -b feature/your-feature`
- Commit changes: `git commit -am 'Add feature'`
- Push: `git push origin feature/your-feature`
- Open Pull Request

Houd de modulaire structuur en ziel van het project intact 😌

---

## 📄 License

This project is licensed under the Apache-2.0 License.

## 📜 Legal

- [Terms of Service](docs/terms-of-service.md)
- [Privacy Policy](docs/privacy-policy.md)

---

## 📬 Contact

Questions, dreams or collaborations?  
Reach out via `support@innersync.tech` or open an issue on GitHub.

---

## 🧭 Operational Playbook (Multi-Guild Setup & Reminders)

Use this quick checklist after adding the bot to a new server to configure it properly.

### Multi-Guild Configuration (Required for each server)

1) **System Configuration**
   ```bash
   # Set log channel for bot messages and errors
   /config system set_log_channel #logs

   # Set rules channel for onboarding
   /config system set_rules_channel #rules

   # Set onboarding channel for welcome messages
   /config system set_onboarding_channel #welcome
   ```

2) **Feature-Specific Configuration**
   ```bash
   # Embed watcher for auto-reminders
   /config embedwatcher announcements_channel_id #announcements

   # Invite tracker
   /config invites announcement_channel_id #invites

   # GDPR compliance
   /config gdpr channel_id #gdpr

   # Ticket system
   /config ticketbot category_id [ticket-category-id]
   /config ticketbot staff_role_id @Staff
   /config ticketbot escalation_role_id @Moderators
   ```

3) **Optional Settings**
   ```bash
   # Allow @everyone mentions in reminders (use carefully!)
   /config reminders allow_everyone_mentions true

   # Set default reminder channel
   /config reminders default_channel_id #general
   ```

### Pre-flight Checklist

- ✅ `DATABASE_URL` environment variable is set
- ✅ Bot has administrator permissions in the server
- ✅ All required channels exist and bot can read/send messages
- ✅ Bot can create channels and roles (for ticket system)

### Startup Verification

- Start the bot and watch the process logs; you should see:
  - ✅ "DB pool created"
  - ✅ "✅ audit_logs table created/verified"
  - ✅ "✅ health_check_history table created/verified"
  - ✅ "✅ Command tracker: Database pool set"
  - ✅ "Bot has successfully started and connected to X server(s)!"
  - ✅ Guild enumeration with server names and IDs

### Testing Functionality

1) **Embed-driven reminder test**
   - Post an embed in the announcements channel with date/time
   - Bot should detect it and schedule a reminder
   - Check `/config system show` to verify channel settings

2) **Manual reminder test**
   - Use `/add_reminder` command
   - Verify reminder appears in list and triggers at correct time
   - Test `/reminder_edit` to modify existing reminders

3) **Import functionality test**
   - Use `/import_onboarding` and `/import_invites` commands (owner only)
   - Ensure proper channels are configured first
- Check `WATCHER_LOG_CHANNEL` for “created”, “sent”, and “deleted” log embeds.

4) Recurring reminder test
- Create a recurring reminder (days + time).
- Expect send only on matching weekday at the configured time; not deleted afterward.

5) Idempotency test
- Restart the bot within the same minute window of a scheduled send.
- Verify that duplicates are prevented (only one send), thanks to `last_sent_at`.

6) Troubleshooting
- No sends? Verify time zone is Brussels and system clock is correct.
- Check that `time` in DB equals the intended trigger minute (HH:MM).
- Inspect logs in `WATCHER_LOG_CHANNEL` for parsing or SQL errors.
- Optional indexes for performance:
  - `CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders (time);`
  - `CREATE INDEX IF NOT EXISTS idx_reminders_reminder_date ON reminders ((event_time - interval '60 minutes')::date);`

