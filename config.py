import os
from dotenv import load_dotenv

load_dotenv()  # Laad variabelen uit .env bestand

BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = 1160511689263947796
ROLE_ID = 1336043451489452144
LOG_CHANNEL_ID = 1336042713459593337
ONBOARDING_CHANNEL_ID = 1336039005917155510  # Kanaal waar onboarding plaatsvindt
RULES_CHANNEL_ID = 1336039005917155510
SEND_CHANNEL_ID = 1336039715320889407  # Vervang dit door het gewenste kanaal-ID
