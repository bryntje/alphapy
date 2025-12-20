import sys
import logging
from logging.handlers import RotatingFileHandler
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional

# Configure logging with rotation
log_handler = RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3)  # 5MB per file, keep 3 backups
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        log_handler,
        logging.StreamHandler(sys.stdout)
    ]
)


MAX_EVENT_HISTORY = 25


class GPTStatusLogs:
    def __init__(self) -> None:
        self.last_success_time: Optional[datetime] = None
        self.last_error_type: Optional[str] = None
        self.average_latency_ms: int = 0
        self.total_tokens_today: int = 0
        self.rate_limit_reset: str = "~"
        self.current_model: str = "grok-beta"  # Default, will be updated from actual usage
        self.last_user: Optional[int] = None
        self.success_count: int = 0
        self.error_count: int = 0
        self.last_success_latency_ms: Optional[int] = None
        self.success_events: Deque[Dict[str, Any]] = deque(maxlen=MAX_EVENT_HISTORY)
        self.error_events: Deque[Dict[str, Any]] = deque(maxlen=MAX_EVENT_HISTORY)


gpt_logs = GPTStatusLogs()


def get_gpt_status_logs() -> GPTStatusLogs:
    return gpt_logs


def log_gpt_success(user_id: Optional[int] = None, tokens_used: int = 0, latency_ms: int = 0) -> None:
    now = datetime.utcnow()
    gpt_logs.last_success_time = now
    gpt_logs.last_user = user_id
    gpt_logs.success_count += 1
    gpt_logs.total_tokens_today += tokens_used
    gpt_logs.average_latency_ms = latency_ms  # TODO: make rolling average
    gpt_logs.last_success_latency_ms = latency_ms
    gpt_logs.success_events.appendleft(
        {
            "timestamp": now,
            "user_id": user_id,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
        }
    )


def log_gpt_error(error_type: str = "unknown", user_id: Optional[int] = None) -> None:
    now = datetime.utcnow()
    gpt_logs.last_error_type = error_type
    gpt_logs.last_user = user_id
    gpt_logs.error_count += 1
    gpt_logs.error_events.appendleft(
        {
            "timestamp": now,
            "user_id": user_id,
            "error_type": error_type,
        }
    )


logger = logging.getLogger("bot")


def log_with_guild(message: str, guild_id: int = None, level: str = "info", extra: dict = None) -> None:
    """Enhanced logging function with guild context"""
    if guild_id:
        message = f"[Guild:{guild_id}] {message}"

    if extra:
        message = f"{message} {extra}"

    if level == "debug":
        logger.debug(message)
    elif level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "critical":
        logger.critical(message)
    else:
        logger.info(message)


def log_guild_action(guild_id: int, action: str, user: str = None, details: str = None, level: str = "info") -> None:
    """Log guild-specific actions with structured format"""
    parts = [f"GUILD:{guild_id}"]
    if user:
        parts.append(f"USER:{user}")
    parts.append(f"ACTION:{action}")
    if details:
        parts.append(f"DETAILS:{details}")

    message = " | ".join(parts)
    log_with_guild(message, guild_id, level)


def log_database_event(event: str, guild_id: int = None, details: str = None, level: str = "info") -> None:
    """Log database-related events"""
    message = f"DATABASE: {event}"
    if details:
        message += f" - {details}"
    log_with_guild(message, guild_id, level)
