import os
from dotenv import load_dotenv

load_dotenv()  # Laad variabelen uit .env bestand

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# # GUILD_ID = int(os.getenv("GUILD_ID", "1160511689263947796"))  # Deprecated - bot detecteert guilds automatisch
ROLE_ID = int(os.getenv("ROLE_ID", "0"))  # Legacy - wordt niet meer gebruikt in multi-guild setup
# LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1338611872299090092"))  # Deprecated - gebruik /config system set_log_channel per guild
# ONBOARDING_CHANNEL_ID = int(os.getenv("ONBOARDING_CHANNEL_ID", "1336039005917155510"))  # Deprecated - gebruik /config system set_onboarding_channel per guild
# RULES_CHANNEL_ID = int(os.getenv("RULES_CHANNEL_ID", "1336039005917155510"))  # Deprecated - gebruik /config system set_rules_channel per guild
# GDPR_CHANNEL_ID = int(os.getenv("GDPR_CHANNEL_ID", "1338623097175146638"))  # Deprecated - gebruik /config gdpr channel_id per guild
# INVITE_ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("INVITE_ANNOUNCEMENT_CHANNEL_ID", "1336041753966416026"))  # Deprecated - gebruik /config invites announcement_channel_id per guild
# Database & API security
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")
DEFAULT_ALLOWED_ORIGINS = [
    "https://app.innersync.tech",
    "https://mind.innersync.tech",
    "https://alphapy.innersync.tech",
]
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
] or DEFAULT_ALLOWED_ORIGINS
APP_BASE_URL = os.getenv("APP_BASE_URL", DEFAULT_ALLOWED_ORIGINS[0])
MIND_BASE_URL = os.getenv("MIND_BASE_URL", DEFAULT_ALLOWED_ORIGINS[1])
ALPHAPY_BASE_URL = os.getenv("ALPHAPY_BASE_URL", DEFAULT_ALLOWED_ORIGINS[2])
SERVICE_NAME = os.getenv("SERVICE_NAME", "alphapy-service")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL") or (
    f"{SUPABASE_URL}/auth/v1/certs" if SUPABASE_URL else None
)
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
SUPABASE_ISSUER = os.getenv(
    "SUPABASE_ISSUER",
    f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else None,
)
SUPABASE_WEBHOOK_SECRET = os.getenv("SUPABASE_WEBHOOK_SECRET")
# ENABLE_EVERYONE_MENTIONS = os.getenv("ENABLE_EVERYONE_MENTIONS", "false").strip().lower() == "true"  # Deprecated - gebruik /config reminders allow_everyone_mentions per guild
# WATCHER_LOG_CHANNEL = int(os.getenv("WATCHER_LOG_CHANNEL", "1336042713459593337"))  # Deprecated - gebruik /config system set_log_channel per guild
# ANNOUNCEMENTS_CHANNEL_ID = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID", "1336038676727206030"))  # Deprecated - gebruik /config embedwatcher announcements_channel_id per guild



# Admin And Owner
OWNER_IDS = [367270193585455104]
ADMIN_ROLE_ID = [1160511689289125925]
