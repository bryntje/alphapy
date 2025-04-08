import sys
import logging
from logging.handlers import RotatingFileHandler

# Configure logging with rotation
log_handler = RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3)  # 5MB per file, keep 3 backups
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        log_handler,
        logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))  # ✅ fix UnicodeEncodeError
    ]
)


from datetime import datetime

class GPTStatusLogs:
    def __init__(self):
        self.last_success_time = None
        self.last_error_type = None
        self.average_latency_ms = 0
        self.total_tokens_today = 0
        self.rate_limit_reset = "~"
        self.current_model = "gpt-3.5-turbo"
        self.last_user = None
        self.success_count = 0
        self.error_count = 0

gpt_logs = GPTStatusLogs()

def get_gpt_status_logs():
    return gpt_logs

def log_gpt_success(user_id=None, tokens_used=0, latency_ms=0):
    gpt_logs.last_success_time = datetime.utcnow()
    gpt_logs.last_user = user_id
    gpt_logs.success_count += 1
    gpt_logs.total_tokens_today += tokens_used
    gpt_logs.average_latency_ms = latency_ms  # of maak hier een rolling average van

def log_gpt_error(error_type="unknown", user_id=None):
    gpt_logs.last_error_type = error_type
    gpt_logs.last_user = user_id
    gpt_logs.error_count += 1


logger = logging.getLogger("bot")
