import openai
import config
import logging
from utils.logger import logger

from openai import AsyncOpenAI, RateLimitError

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# ---------------- GPT Core Helper ------------------- #

async def ask_gpt(prompt: str, model="gpt-3.5-turbo", temperature=0.7, max_tokens=600) -> str:
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        reply = response.choices[0].message.content
        return reply.strip()
    except RateLimitError as e:
        logger.warning(f"⚠️ OpenAI rate limit: {e}")
        raise
    except Exception as e:
        logger.exception(f"❌ GPT error: {e}")
        raise

# ---------------- Logging ------------------- #

def log_gpt_success(user_id=None, tokens_used=0, latency_ms=0):
    logger.info(f"✅ GPT success by {user_id} – {tokens_used} tokens, {latency_ms}ms latency")

def log_gpt_error(error_type="unknown", user_id=None):
    logger.error(f"❌ GPT error [{error_type}] by {user_id}")
