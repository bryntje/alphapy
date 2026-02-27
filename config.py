import os
from dotenv import load_dotenv
import warnings

# Suppress dotenv warnings about empty lines or trailing newlines in .env file
# These are harmless and common in .env files
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*dotenv.*")
    load_dotenv()  # Load variables from .env file

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Legacy - kept for backwards compatibility
GROK_API_KEY = os.getenv("GROK_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "grok").strip().lower()  # "grok" or "openai"

ROLE_ID = int(os.getenv("ROLE_ID", "0"))  # Legacy - no longer used in multi-guild setup

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

# Google Cloud Secret Manager configuration
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GOOGLE_SECRET_NAME = os.getenv("GOOGLE_SECRET_NAME", "alphapy-google-credentials")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # Fallback for local development

# Telemetry ingest configuration
TELEMETRY_INGEST_INTERVAL = int(os.getenv("TELEMETRY_INGEST_INTERVAL", "45"))  # seconds

# Core-API ingress (neural plane centralisation)
# When set, telemetry and operational events are sent to Core instead of direct Supabase
CORE_API_URL = (os.getenv("CORE_API_URL") or "").rstrip("/")
ALPHAPY_SERVICE_KEY = os.getenv("ALPHAPY_SERVICE_KEY")

# Discord OAuth2 for Web Configuration Interface
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_OAUTH_REDIRECT_URI = os.getenv("DISCORD_OAUTH_REDIRECT_URI", f"{ALPHAPY_BASE_URL}/api/auth/discord/callback")


# Main Guild (Primary server where bot operates)
# This is used as default for API endpoints when no guild_id is specified
MAIN_GUILD_ID = int(os.getenv("MAIN_GUILD_ID", "0"))  # Set to 0 to disable filtering (show all guilds)

# Premium tier
PREMIUM_CHECKOUT_URL = os.getenv("PREMIUM_CHECKOUT_URL", "")
PREMIUM_CACHE_TTL_SECONDS = int(os.getenv("PREMIUM_CACHE_TTL_SECONDS", "300"))

# Admin And Owner
OWNER_IDS = [367270193585455104]
ADMIN_ROLE_ID = [1160511689289125925]
