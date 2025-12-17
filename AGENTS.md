# AGENTS.md

## 🧠 Innersync • Alphapy Bot – AI Agent Manifest

Dit document beschrijft de actieve AI-agents en modulaire functies van de Innersync • Alphapy Discord Bot.

---

## 📣 Agent: EmbedReminderWatcher

- **Pad**: `cogs/embed_watcher.py`
- **Doel**: Detecteert nieuwe embeds in het announcements-kanaal en genereert automatisch reminders.
- **Triggers**: `on_message` → embed parsing
- **Opslag**: PostgreSQL (reminders table)
- **Speciale parsing**: Titel, tijd, dagen, locatie via NLP
- **Helper functie**: `parse_embed_for_reminder()`
- **Logging**: `WATCHER_LOG_CHANNEL`
- **Dependencies**: `discord.py`, `asyncpg`, `spaCy` (optioneel)
- **Known Issues**: Tijdzone parsing kritisch, NLP vereist juiste embed structuur.

---

## 🧾 Agent: ReminderManager

- **Doel**: Slashcommands voor handmatig toevoegen/beheren van reminders.
- **Commands**:
  - `/add_reminder` – reminder toevoegen (manueel of via messagelink)
  - `/reminder_list` – actieve reminders bekijken
  - `/reminder_delete` – reminder verwijderen
- **Interactie**: Gebruikt dezelfde parser als `EmbedReminderWatcher`.

---

## 🚀 Agent: GPTInteraction

- **Doel**: AI-functionaliteit met OpenAI.
- **Commands**:
  - `/create_caption` – caption genereren
  - `/learn_topic` – uitleg over een onderwerp
  - `/gptstatus` – status van GPT-API

---

## 🌱 Agent: GrowthCheckIn

- **Doel**: Begeleid persoonlijke groei van communityleden via GPT.
- **Command**:
  - `/growthcheckin`
- **Logging**: Opslag van antwoorden voor verwerking of follow-up.

---

## 🔐 Agent: GDPRHandler

- **Doel**: Ondersteuning voor gegevensrechten.
- **Command**:
  - `/export_onboarding` – exporteert onboardingdata als CSV
- **Toekomst**:
  - Mogelijkheid tot `/delete_my_data` (nog niet geïmplementeerd)

---

## 🧮 Agent: InviteTracker

- **Doel**: Volgt Discord invites per gebruiker.
- **Commands**:
  - `/inviteleaderboard`
  - `/setinvites`
  - `/resetinvites`

---

## 🔄 Agent: UtilityAdmin

- **Doel**: Ondersteunende taken.
- **Commands**:
  - `/clean` – berichten verwijderen
  - `/sendto` – bericht verzenden naar specifiek kanaal
  - `/reload` – herlaadt een extensie

---

## 🌐 API Agent: FastAPI Dashboard Endpoint

- **Pad**: `api.py`
- **Doel**: Exposeert reminders én realtime metrics voor dashboards
- **Endpoints**:
  - `/api/reminders/*` – CRUD voor gebruikersreminders (API key + `X-User-Id`)
  - `/api/dashboard/metrics` – live bot status, GPT-logstatistieken, reminder- en ticketcounts
- **Helpers**: `utils/runtime_metrics.get_bot_snapshot()` zorgt voor veilige cross-thread snapshots vanuit Discord

---

## 📊 Agent: Telemetry Ingest Background Job

- **Pad**: `api.py` (`_telemetry_ingest_loop()`)
- **Doel**: Automatische periodieke telemetry data ingest naar Supabase voor Mind dashboard
- **Functionaliteit**:
  - Draait continu als background task in FastAPI lifespan
  - Verzamelt metrics elke 30-60 seconden (configureerbaar via `TELEMETRY_INGEST_INTERVAL`)
  - Schrijft naar `telemetry.subsystem_snapshots` met subsystem='alphapy'
  - Verzamelt: bot status, uptime, latency, throughput, error rate, queue depth, active bots
  - Graceful error handling: fouten worden gelogd maar stoppen de task niet
- **Configuratie**:
  - `TELEMETRY_INGEST_INTERVAL` (default: 45 seconden) in `config.py`
- **Logging**: Info bij start, debug bij succesvolle ingest, warning bij fouten
- **Known Issues**: Geen - task start automatisch bij API server startup en stopt correct bij shutdown
