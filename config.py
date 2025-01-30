import os
from dotenv import load_dotenv

load_dotenv()  # Laad variabelen uit .env bestand

BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = 1330201976717312081
ROLE_ID = 1330471273364721664
LOG_CHANNEL_ID = 1330492696078319696
ONBOARDING_CHANNEL_ID = 1330219239252037653  # Kanaal waar onboarding plaatsvindt
RULES_CHANNEL_ID = 1330219239252037653