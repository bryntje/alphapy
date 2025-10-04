# helpers.py

import logging
import asyncio
import time
from datetime import datetime
from typing import Optional
import discord
from discord import Embed
from discord.ext import commands
from openai import AsyncOpenAI, OpenAIError

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

logger = logging.getLogger("bot")

SYSTEM_PROMPT = """
Je bent een betrokken en bewust AI-assistent met expertise in mindset, leiderschap, trading, zelfbewustzijn en emotionele intelligentie.

Je antwoorden zijn steeds afgestemd op die thema’s.  
Als een vraag buiten dit kader valt — zoals koken, huishoudelijke taken of irrelevante technologie — dan beantwoord je ze niet, maar verwijs je de gebruiker vriendelijk terug naar waar je wél bij kan helpen.

Je doel is niet om *alles* te weten, maar om diepgang te brengen waar het telt.

Gebruik steeds dezelfde taal als de gebruiker.  
Je antwoord is helder, menselijk, en raakt zacht waar het mag — scherp waar het moet.
"""



# Bot instance wordt later gezet
bot_instance: Optional[commands.Bot] = None
LOG_CHANNEL_ID = 1336042713459593337

def set_bot_instance(bot: commands.Bot) -> None:
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
    logs = get_gpt_status_logs()
    logs.last_error_type = error_type
    logs.last_user = user_id
    logs.error_count += 1

    log_message = f"❌ GPT error [{error_type}] by {user_id}"
    logger.error(log_message)
    if bot_instance:
        asyncio.create_task(log_to_channel(log_message, level="error"))

def is_allowed_prompt(prompt: str) -> bool:
    # Voeg hier woorden of zinnen toe die je wil blokkeren
    blocked_keywords = [
        "how to tie", "joke", "how to whistle", "useless", "unrelated", 
        "fart", "how to dance", "how to sleep", "funny story", "pick up line"
    ]
    return not any(bad in prompt.lower() for bad in blocked_keywords)


async def log_to_channel(message: str, level: str = "info"):
    if bot_instance is None:
        logger.warning("⚠️ Tried to log to Discord channel, but bot_instance is None")
        return

    channel = bot_instance.get_channel(LOG_CHANNEL_ID)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
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
_api_key = getattr(config, "OPENAI_API_KEY", None)
_api_key_missing = not _api_key
if _api_key_missing:
    logger.warning(
        "⚠️ OPENAI_API_KEY ontbreekt. Stel deze in je .env of config_local.py om GPT-commando's te gebruiken."
    )
    openai_client = None
else:
    openai_client = AsyncOpenAI(api_key=_api_key)

def _get_settings_values(default_model: str) -> tuple[str, Optional[float]]:
    if bot_instance is None:
        return default_model, None

    settings = getattr(bot_instance, "settings", None)
    if not settings:
        return default_model, None

    model_value = default_model
    temperature_value: Optional[float] = None

    try:
        fetched_model = settings.get("gpt", "model")
        if isinstance(fetched_model, str) and fetched_model.strip():
            model_value = fetched_model.strip()
    except KeyError:
        pass

    try:
        fetched_temp = settings.get("gpt", "temperature")
        if fetched_temp is not None:
            temperature_value = float(fetched_temp)
    except KeyError:
        pass
    except (TypeError, ValueError):
        logger.warning("⚠️ GPT temperature setting ongeldig — fallback naar API default.")
        temperature_value = None

    return model_value, temperature_value


async def ask_gpt(messages, user_id=None, model: Optional[str] = None):
    start = time.perf_counter()

    try:
        if _api_key_missing or openai_client is None:
            raise RuntimeError(
                "OPENAI_API_KEY ontbreekt. Stel de sleutel in (.env of config_local.py) en herstart de bot."
            )

        # 👉 Check of messages een string is (oude stijl prompt)
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        assert isinstance(messages, list) and all(isinstance(m, dict) for m in messages), "❌ Invalid messages format"

        resolved_model, temperature = _get_settings_values(model or "gpt-3.5-turbo")
        chat_kwargs = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *messages
            ],
        }
        if temperature is not None:
            chat_kwargs["temperature"] = temperature

        response = await openai_client.chat.completions.create(**chat_kwargs)
        latency = (time.perf_counter() - start) * 1000 if response else 0  # in ms
        tokens = response.usage.total_tokens if response.usage else 0

        log_gpt_success(user_id=user_id, tokens_used=tokens, latency_ms=int(latency))
        return response.choices[0].message.content

    except Exception as e:
        error_type = f"{type(e).__name__}: {str(e)}"
        log_gpt_error(error_type=error_type, user_id=user_id)
        raise
