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
cd alphapips-bot
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
```

> The AI layer is modular and optional — for teams that want to deepen reflection, personalize learning, or co-create content using GPT.

---

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
