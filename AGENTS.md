# AGENTS.md

## 🧠 Alphapips Bot – AI Agent Manifest

Dit document beschrijft de actieve AI-agents en modulaire functies van de Alphapips Discord Bot.

---

## 📣 Agent: EmbedReminderWatcher

- **Doel**: Detecteert nieuwe embeds in het announcements-kanaal en genereert automatisch reminders.
- **Triggers**: `on_message` → embed parsing
- **Opslag**: PostgreSQL (reminders table)
- **Speciale parsing**: Titel, tijd, dagen, locatie via NLP
- **Helper functie**: `parse_embed_for_reminder()`

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

## 🌐 API Agent: FastAPI Reminder Endpoint

- **Doel**: Toegang geven tot reminderdata via HTTP endpoint
- **Gebruik**: Voor dashboards of externe tools