import os
from dotenv import load_dotenv
import warnings

# Suppress dotenv warnings about empty lines or trailing newlines in .env file
# These are harmless and common in .env files
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*dotenv.*")
    load_dotenv()  # Load variables from .env file

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Optional: use a separate bot token for local testing (e.g. a dev bot). Set USE_TEST_BOT=1 to use this.
BOT_TOKEN_TEST = os.getenv("BOT_TOKEN_TEST")
# Token actually used to run the bot: BOT_TOKEN_TEST when USE_TEST_BOT=1 and BOT_TOKEN_TEST is set, else BOT_TOKEN.
BOT_TOKEN_ACTIVE = (BOT_TOKEN_TEST if os.getenv("USE_TEST_BOT") == "1" and BOT_TOKEN_TEST else None) or BOT_TOKEN
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
# App reflections webhook (Core-API → Alphapy). Optional; falls back to WEBHOOK_SECRET / SUPABASE_WEBHOOK_SECRET
APP_REFLECTIONS_WEBHOOK_SECRET = os.getenv("APP_REFLECTIONS_WEBHOOK_SECRET")

# Google Cloud Secret Manager configuration
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GOOGLE_SECRET_NAME = os.getenv("GOOGLE_SECRET_NAME", "alphapy-google-credentials")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # Fallback for local development

# Telemetry ingest configuration
TELEMETRY_INGEST_INTERVAL = int(os.getenv("TELEMETRY_INGEST_INTERVAL", "45"))  # seconds

# Core-API ingress (neural plane centralisation)
# When set, telemetry and operational events are sent to Core instead of direct Supabase.
# Use the Core API origin (e.g. https://core.innersync.tech), not a Next.js site such as api.innersync.tech.
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
# Webhook secrets for Core → Alphapy callbacks (optional; fall back to APP_REFLECTIONS_WEBHOOK_SECRET / WEBHOOK_SECRET)
PREMIUM_INVALIDATE_WEBHOOK_SECRET = os.getenv("PREMIUM_INVALIDATE_WEBHOOK_SECRET")
FOUNDER_WEBHOOK_SECRET = os.getenv("FOUNDER_WEBHOOK_SECRET")

# Alphapy dashboard (separate Next.js control panel for bot configuration)
DASHBOARD_BASE_URL = (os.getenv("DASHBOARD_BASE_URL") or "").rstrip("/")
# HMAC secrets for outbound signed webhooks from bot → dashboard
REFLECTION_WEBHOOK_SECRET = os.getenv("REFLECTION_WEBHOOK_SECRET")
GDPR_WEBHOOK_SECRET = os.getenv("GDPR_WEBHOOK_SECRET")

# GitHub (for /release notes and "read full" link). Optional; when unset, /release uses local changelog.
GITHUB_REPO = (os.getenv("GITHUB_REPO") or "").strip().rstrip("/")
# Optional: token for GitHub API (e.g. /release, repo links) to avoid rate limits
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Admin And Owner
OWNER_IDS = [367270193585455104]
ADMIN_ROLE_ID = [1160511689289125925]

# Image reminder rate limiting
IMAGE_REMINDER_RATE_LIMIT_WINDOW = int(os.getenv("IMAGE_REMINDER_RATE_LIMIT_WINDOW", "3600"))  # seconds
IMAGE_REMINDER_RATE_LIMIT_COUNT = int(os.getenv("IMAGE_REMINDER_RATE_LIMIT_COUNT", "100"))  # max entries per user/guild
