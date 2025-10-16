# Credentials Directory

Store private service credentials in this folder, such as `credentials.json` for Google integrations. These files should never be committed to version control.

Recommended workflow:

1. Copy the required credential file into this directory on your local machine.
2. Keep the original filename (e.g., `credentials.json`) so the bot can load it.
3. If you need to share defaults, create a sanitized template like `credentials.example.json` instead of the real file.

> Reminder: `.gitignore` already excludes this directory, but if a secret was committed earlier you must rotate that credential because it may exist in Git history.
