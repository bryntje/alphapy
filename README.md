# 🤖 Alphapy Discord Bot

Een krachtige, modulaire Discord-bot voor bewuste communities — praktische servertools gecombineerd met AI-functies voor growth coaching en kennisdeling.

**🔗 Verwante repositories:**
- 🌐 **[alphapy-dashboard](https://github.com/bryntje/alphapy-dashboard)** - Next.js web interface voor configuratie

---

## 🌱 Overview

**Alphapy** is een Discord bot gebouwd voor de Innersync • Alphapips community, met focus op waarde-gedreven trading workflows en persoonlijke groei.

De bot combineert essentiële Discord utilities met een optionele AI laag:

- 🧘‍♂️ **Growth coaching** via `/growthcheckin`
- 🧠 **Hybride kennis search** via `/learn_topic`
- ✍️ **Caption generatie** via `/create_caption`
- 🎫 **Ticket systeem** voor support
- 📊 **Metrics & dashboards** API

Modulair, schaalbaar en eenvoudig uit te breiden — met schone architectuur en duidelijke intenties.

---

## 📁 Project Structure

```plaintext
alphapy/
├── bot.py                # Main Discord bot runner
├── api.py                # FastAPI server voor metrics/dashboard API
├── cogs/                 # Bot command modules (28 commands)
│   ├── growth.py         # AI growth coaching (/growthcheckin)
│   ├── learn.py          # Hybrid knowledge search (/learn_topic)
│   ├── ticketbot.py      # Support ticket system
│   ├── reminders.py      # Scheduled reminders
│   └── ...               # 24 andere commands
├── utils/                # Core utilities (12 modules)
│   ├── supabase_client.py # Database connectivity
│   ├── runtime_metrics.py # Live bot metrics
│   └── ...               # Logging, timezone, quiz state, etc.
├── gpt/                  # AI functionality
│   ├── helpers.py        # GPT API calls + logging
│   └── dataset_loader.py # Content loading voor learn_topic
├── data/prompts/         # Local knowledge base (.md files)
├── webhooks/             # Supabase webhooks
├── docs/                 # Documentation
├── requirements.txt      # Python dependencies
├── config.py             # Bot configuration
└── .github/workflows/    # CI/CD pipelines
```

**🎯 Schone scheiding:** Bot logica ↔ Web interface

---

## 🚀 Installation

### Prerequisites
- Python 3.8+
- Discord Bot Token
- Supabase project (voor database)

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

3. **Configureer de bot:**
```bash
# Kopieer environment template
cp .env.example .env

# Bewerk .env met je credentials:
# - DISCORD_TOKEN=your_bot_token
# - SUPABASE_URL=your_supabase_url
# - SUPABASE_ANON_KEY=your_anon_key
# - SUPABASE_SERVICE_ROLE_KEY=your_service_key
```

4. **Run de bot:**
```bash
python bot.py
```

### 🚀 Deployment
- **Lokale development:** `python bot.py`
- **Railway:** Configureer een Python service die `python bot.py` draait
- **Environment variables:** Alle vars uit `.env`

---

## 💡 Slash Commands

```plaintext
/growthcheckin     → GPT-coach for goals, obstacles and emotions
/learn_topic       → Hybrid topic search using local + Drive content
/create_caption    → Generate 1-liner captions based on tone & topic
/ticket            → Create a support ticket (private channel per ticket)
/ticket_list       → View open tickets (admins)
/ticket_claim      → Claim a ticket (admins)
/ticket_close      → Close a ticket (admins)
/ticket_panel_post → Post a persistent “Create ticket” panel (admins)
```

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
- Staff-only actions: `/ticket_list`, `/ticket_claim`, `/ticket_close`, `/ticket_panel_post`, Claim/Close/Delete buttons.

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

## 🛣️ Roadmap (Tickets)

- `/faq` command
  - `/faq list` to show recent/pinned entries
  - `/faq view <id|keyword>` to show a specific entry
  - Optional `/faq search <query>` (keyword match)
- Tests
  - Unit tests for summary prompt builder and storage
  - Interaction tests for claim/close/permissions
- CI (future)
  - Lightweight migration check (ensure tables/columns exist)
  - Lint and type checks on PRs

---

## 🌐 API Endpoints

De bot bevat een ingebouwde FastAPI server voor metrics en health checks:

- `GET /health` – JSON health probe met uptime, database status
- `GET /api/dashboard/metrics` – Live bot metrics (latency, guilds, commands)
- `GET /export_tickets` – CSV export van tickets
- `GET /export_faq` – CSV export van FAQ entries

**⚠️ Belangrijk:** Voor de **volledige web dashboard** (grafieken, configuratie UI), zie:
**👉 [alphapy-dashboard repository](https://github.com/bryntje/alphapy-dashboard)**

### Environment Variables

```bash
# Discord Bot
DISCORD_TOKEN=your_bot_token_here

# Supabase Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_key

# Optional API Security
API_KEY=optional_internal_key
```


## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐
│   alphapy       │    │ alphapy-dashboard │
│   (Discord Bot) │    │  (Next.js Web)   │
├─────────────────┤    ├──────────────────┤
│ • 28 Commands   │    │ • Config UI      │
│ • AI Features   │◄──►│ • Live Metrics   │
│ • Ticket System │    │ • Admin Panel    │
│ • Database      │    │ • Charts         │
│ • Webhooks      │    │ • API Proxy      │
└─────────────────┘    └──────────────────┘
        │                       │
        └────── Supabase ───────┘
```

**Schone scheiding:** Bot logica ↔ Web interface ↔ Database

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

This project is licensed under the MIT License.

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
  - ✅ "✅ Bot is succesvol opgestart en verbonden met X server(s)!"
  - ✅ Guild enumeration with server names and IDs

### Testing Functionality

1) **Embed-driven reminder test**
   - Post an embed in the announcements channel with date/time
   - Bot should detect it and schedule a reminder
   - Check `/config system show` to verify channel settings

2) **Manual reminder test**
   - Use `/reminder add` command
   - Verify reminder appears in list and triggers at correct time

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
