import logging
from logging.handlers import RotatingFileHandler

# Configure logging with rotation
log_handler = RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3)  # 5MB per file, keep 3 backups
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[log_handler, logging.StreamHandler()]  # Log to file and console
)

from datetime import datetime

class GPTStatusLogs:
    def __init__(self):
        self.last_success_time = datetime.utcnow()
        self.last_error_type = None
        self.average_latency_ms = 420
        self.total_tokens_today = 3242
        self.rate_limit_reset = "~12 min"
        self.current_model = "gpt-3.5-turbo"
        self.last_user = 123456789012345678  # Discord user ID
        self.success_count = 8
        self.error_count = 3

def get_gpt_status_logs():
    return GPTStatusLogs()


logger = logging.getLogger("bot")
