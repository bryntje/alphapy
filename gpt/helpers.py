# helpers.py

import logging
import asyncio
import time
from datetime import datetime
from discord import Embed
from openai import AsyncOpenAI, OpenAIError

logger = logging.getLogger("bot")

# Bot instance wordt later gezet
bot_instance = None
LOG_CHANNEL_ID = 1336042713459593337  # 👈 pas deze aan naar jouw Discord log kanaal ID

def set_bot_instance(bot):
    global bot_instance
    bot_instance = bot
    logger.info("🤖 Bot instance is now set in helpers.py")

def log_gpt_success(user_id=None, tokens_used=0, latency_ms=0):
    from utils.logger import get_gpt_status_logs
    logs = get_gpt_status_logs()
    logs.last_success_time = datetime.utcnow()
    logs.last_user = user_id
    logs.success_count += 1
    logs.total_tokens_today += tokens_used
    logs.average_latency_ms = latency_ms

    log_message = f"✅ GPT success by {user_id} – {tokens_used} tokens, {latency_ms}ms latency"
    logger.info(log_message)
    if bot_instance:
        asyncio.create_task(log_to_channel(log_message, level="info"))

def log_gpt_error(error_type="unknown", user_id=None):
    from utils.logger import get_gpt_status_logs
    logs = get_gpt_status_logs
    logs.last_error_type = error_type
    logs.last_user = user_id
    logs.error_count += 1

    log_message = f"❌ GPT error [{error_type}] by {user_id}"
    logger.error(log_message)
    if bot_instance:
        asyncio.create_task(log_to_channel(log_message, level="error"))

async def log_to_channel(message: str, level: str = "info"):
    if bot_instance is None:
        logger.warning("⚠️ Tried to log to Discord channel, but bot_instance is None")
        return

    channel = bot_instance.get_channel(LOG_CHANNEL_ID)
    if not channel:
        logger.warning(f"⚠️ Could not find log channel with ID {LOG_CHANNEL_ID}")
        return

    embed = Embed(
        description=message,
        timestamp=datetime.utcnow(),
        color=0x00BFFF if level == "info" else 0xFF0000
    )
    embed.set_author(name=f"{level.upper()} Log")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f"🚨 Failed to send log embed: {e}")

# --- GPT ask wrapper ---
openai_client = AsyncOpenAI()

async def ask_gpt(messages, user_id=None, model="gpt-3.5-turbo"):
    start = time.perf_counter()

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
        )
        latency = (time.perf_counter() - start) * 1000  # in ms
        tokens = response.usage.total_tokens

        log_gpt_success(user_id=user_id, tokens_used=tokens, latency_ms=int(latency))
        return response.choices[0].message.content

    except Exception as e:
        error_type = f"{type(e).__name__}: {str(e)}"
        log_gpt_error(error_type=error_type, user_id=user_id)
        raise
