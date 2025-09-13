# 🤖 Alphapips Discord Bot

A powerful, modular Discord bot built for conscious communities — blending practical server tools with AI-enhanced features.

---

## 🌱 Overview

**Alphapips Bot** is designed to support a value-driven trading community.
It combines essential Discord utilities (onboarding, leaderboards, quizzes, role logic) with an optional AI layer that adds depth and reflection.

This includes:

- 🧘‍♂️ Gentle growth coaching via `/growthcheckin`
- 🧠 Hybrid knowledge search via `/learn_topic`
- ✍️ Caption generation with tone via `/create_caption`

The bot is modular, scalable, and easy to expand — with clean architecture and clear intent.

---

## 📁 Project Structure

```plaintext
.
├── cogs/                 # AI command modules (growth, learn, leadership, quiz, etc.)
├── gpt/                  # GPT logic, prompt helpers, dataset loaders
│   ├── helpers.py        # Central GPT call + logging helpers
│   └── dataset_loader.py # Loads .md content for learn_topic
├── utils/                # Google Drive sync + general utilities
│   └── drive_sync.py     # Fetches and parses Drive-based PDFs
├── data/prompts/         # Local topic files (e.g. rsi.md, scalping.md)
├── requirements.txt      # All dependencies (GPT, Drive, PDF parser)
├── bot.py                # Main bot runner
├── .env / config.py      # Your API tokens, Discord settings, etc.
├── README.md             # This file
└── CHANGELOG.md          # Development log by branch & feature
```

---

## 🚀 Installation

1. **Clone the repository:**
```bash
git clone https://github.com/bryntje/alphapy.git
cd alphapy
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure the bot:**
- Add your Discord bot token to `.env`
- Add Google Drive OAuth `credentials.json` to `/credentials/`

4. **Run the bot:**
```bash
python bot.py
```

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

## 📊 Exports & Metrics

- `/ticket_stats` – interactive stats (7d/30d/all, refresh), embeds include version/codename
- `ticket_metrics` table stores snapshots (scope, counts, avg cycle seconds, triggered_by)
- `/export_tickets [scope]` – CSV export of tickets
- `/export_faq` – CSV export of FAQ entries


## 🤝 Contributing

We welcome devs, thinkers, and conscious builders.

- Fork the repo
- Create a new branch: `git checkout -b feature/your-feature`
- Commit your changes: `git commit -am 'Add new feature'`
- Push: `git push origin feature/your-feature`
- Open a Pull Request

Please follow the modular structure and keep the soul of the project intact 😌

---

## 📄 License

This project is licensed under the MIT License.

---

## 📬 Contact

Questions, dreams or collaborations?  
Reach out via `bryan.dhaen@gmail.com` or open an issue on GitHub.

---

## 🧭 Operational Playbook (Reminders & Logging)

Use this quick checklist after deploys or config changes to validate reminder behavior and logs.

1) Pre-flight
- Ensure env vars are set: `DATABASE_URL`, `WATCHER_LOG_CHANNEL`, `GUILD_ID`, `ENABLE_EVERYONE_MENTIONS`.
- Bot has permissions to read/send in announcement and log channels.

2) Startup verification
- Start the bot and watch the process logs; you should see DB connection OK.
- Confirm the `reminders` table includes `call_time` and `last_sent_at`.

3) One-off reminder test (embed-driven)
- Post an announcement embed with a concrete date/time.
- Expect two sends: at T−60 and at T0 (event time).
- After T0 send, the reminder should be deleted.
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
