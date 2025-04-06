# 📦 Changelog

All notable changes to this project will be documented in this file.

---

## [Unreleased]
> Currently in active development on `dev/gpt_refactor`

### ✨ Added
- `/growthcheckin`: Soft GPT-powered coaching for goals, obstacles and emotions
- `/learn_topic`: Hybrid knowledge command (uses `.md` files or Drive PDFs as context)
- `/create_caption`: Style-based caption generator for social, based on GPT
- `gpt/helpers.py`: Central GPT logic (ask_gpt, log_gpt_success, log_gpt_error)
- `gpt/dataset_loader.py`: Loads topic data from local prompts folder
- `utils/drive_sync.py`: Fetches and parses PDFs from Google Drive

### ♻️ Changed
- Fully modular refactor: legacy files moved to `cogs/`, `gpt/`, `utils/`
- Updated `setup_hook()` to reflect new cog structure
- Imports cleaned and centralized across all modules
- `requirements.txt` updated with `pydrive2`, `PyMuPDF`

### 🧪 In Progress
- Drive integration expansion (DOCX, Google Docs)
- Caption batch generation & logging

---

## [feature/ai_lotquiz]
> Previous AI feature branch

### ✨ Added
- Initial GPT integration structure (lot size quiz logic)
- Logging and slash command framework

---

## [master]
> Original production state
