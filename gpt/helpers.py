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
You are an engaged and conscious AI assistant with expertise in mindset, leadership, trading, self-awareness, and emotional intelligence.

Your responses are always aligned with these themes.  
If a question falls outside this framework — such as cooking, household tasks, or irrelevant technology — you don't answer it, but politely redirect the user to where you *can* help.

Your goal is not to know *everything*, but to bring depth where it matters.

Always use the same language as the user.  
Your answer is clear, human, and touches softly where it can — sharp where it must.
"""

LEARN_TOPIC_PROMPT_TEMPLATE = """Gebruik de volgende contextuele informatie om de vraag te beantwoorden:

{context}

Vraag van de gebruiker: {topic}

Geef een duidelijke, uitgebreide uitleg gebaseerd op de context, maar voeg ook je eigen expertise toe over mindset, trading psychologie en praktische toepassingen."""



# Bot instance will be set later
bot_instance: Optional[commands.Bot] = None

# --- Grok Fallback & Retry Queue ---
FALLBACK_MESSAGE = "I'm temporarily unavailable. Please try again in a few minutes."
_gpt_retry_queue: list = []  # List of dicts: {messages, user_id, model, guild_id, retry_count, timestamp}
MAX_RETRY_QUEUE_SIZE = 50
MAX_RETRIES = 5
_retry_task: Optional[asyncio.Task] = None

def set_bot_instance(bot: commands.Bot) -> None:
    global bot_instance
    bot_instance = bot
    logger.info("🤖 Bot instance is now set in helpers.py")
    # Note: Grok retry queue task will be started in on_ready event when event loop is running

def log_gpt_success(user_id=None, tokens_used=0, latency_ms=0, guild_id: Optional[int] = None, model: Optional[str] = None):
    from utils.logger import get_gpt_status_logs
    logs = get_gpt_status_logs()
    logs.last_success_time = datetime.utcnow()
    logs.last_user = user_id
    logs.success_count += 1
    logs.total_tokens_today += tokens_used
    logs.average_latency_ms = latency_ms
    # Update current_model if provided (reflects actual model used)
    if model:
        logs.current_model = model

    log_message = f"✅ Grok success by {user_id} – {tokens_used} tokens, {latency_ms}ms latency"
    logger.info(log_message)
    if bot_instance and guild_id:
        asyncio.create_task(log_to_channel(log_message, level="info", guild_id=guild_id))

def log_gpt_error(error_type="unknown", user_id=None, guild_id: Optional[int] = None):
    from utils.logger import get_gpt_status_logs
    logs = get_gpt_status_logs()
    logs.last_error_type = error_type
    logs.last_user = user_id
    logs.error_count += 1

    log_message = f"❌ Grok error [{error_type}] by {user_id}"
    logger.error(log_message)
    if bot_instance and guild_id:
        asyncio.create_task(log_to_channel(log_message, level="error", guild_id=guild_id))

def is_allowed_prompt(prompt: str) -> bool:
    # Add words or phrases here that you want to block
    blocked_keywords = [
        "how to tie", "joke", "how to whistle", "useless", "unrelated", 
        "fart", "how to dance", "how to sleep", "funny story", "pick up line"
    ]
    return not any(bad in prompt.lower() for bad in blocked_keywords)


async def log_to_channel(message: str, level: str = "info", guild_id: Optional[int] = None):
    """
    Log Grok events to the configured log channel for the guild.
    Uses system.log_channel_id from settings (configured via /config system set_log_channel).
    """
    if bot_instance is None:
        logger.warning("⚠️ Tried to log to Discord channel, but bot_instance is None")
        return

    if guild_id is None:
        logger.debug("⚠️ Grok log called without guild_id - skipping Discord log")
        return

    # Get log channel from settings (system.log_channel_id)
    settings = getattr(bot_instance, "settings", None)
    if not settings:
        logger.debug("⚠️ Settings service not available - skipping Discord log")
        return

    try:
        channel_id = int(settings.get("system", "log_channel_id", guild_id))
        if channel_id == 0:
            logger.debug(f"⚠️ No log channel configured for guild {guild_id} - skipping Discord log")
            return
    except Exception as e:
        logger.debug(f"⚠️ Could not get log channel ID for guild {guild_id}: {e}")
        return

    channel = bot_instance.get_channel(channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        logger.warning(f"⚠️ Could not find log channel with ID {channel_id} for guild {guild_id}")
        return

    embed = Embed(
        description=message,
        timestamp=datetime.utcnow(),
        color=0x00BFFF if level == "info" else 0xFF0000
    )
    embed.set_author(name=f"Grok {level.upper()}")
    embed.set_footer(text=f"Grok | Guild: {guild_id}")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f"🚨 Failed to send Grok log embed: {e}")


def _add_to_retry_queue(messages, user_id, model, guild_id):
    """Add a failed Grok request to the retry queue."""
    global _gpt_retry_queue
    
    # Limit queue size (drop oldest if full)
    if len(_gpt_retry_queue) >= MAX_RETRY_QUEUE_SIZE:
        _gpt_retry_queue.pop(0)
    
    _gpt_retry_queue.append({
        "messages": messages,
        "user_id": user_id,
        "model": model,
        "guild_id": guild_id,
        "retry_count": 0,
        "timestamp": datetime.utcnow(),
    })


async def _retry_gpt_requests():
    """Background task that processes the Grok retry queue every 5 minutes."""
    global _gpt_retry_queue
    
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            
            if not _gpt_retry_queue:
                continue
            
            # Process queue (copy to avoid modification during iteration)
            queue_copy = _gpt_retry_queue.copy()
            _gpt_retry_queue.clear()
            
            for item in queue_copy:
                retry_count = item["retry_count"]
                if retry_count >= MAX_RETRIES:
                    logger.debug(f"⚠️ Dropping Grok retry after {MAX_RETRIES} attempts")
                    continue
                
                # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                backoff_seconds = 2 ** retry_count
                await asyncio.sleep(backoff_seconds)
                
                try:
                    # Retry the request (with _is_retry=True to prevent re-queuing)
                    result = await ask_gpt(
                        item["messages"],
                        user_id=item["user_id"],
                        model=item["model"],
                        guild_id=item["guild_id"],
                        _is_retry=True
                    )
                    logger.debug(f"✅ Grok retry succeeded for user {item['user_id']}")
                    # Success - don't re-queue
                except Exception as retry_error:
                    # Still failed - increment retry count and re-queue
                    item["retry_count"] += 1
                    item["timestamp"] = datetime.utcnow()
                    if len(_gpt_retry_queue) < MAX_RETRY_QUEUE_SIZE:
                        _gpt_retry_queue.append(item)
                    logger.debug(f"⚠️ Grok retry {item['retry_count']}/{MAX_RETRIES} failed: {retry_error}")
        
        except asyncio.CancelledError:
            logger.info("🛑 Grok retry queue task cancelled")
            raise
        except Exception as e:
            logger.error(f"❌ Error in Grok retry queue task: {e}")
            await asyncio.sleep(60)  # Wait before retrying the task itself


# --- LLM client setup (Grok or OpenAI) ---
_llm_provider = getattr(config, "LLM_PROVIDER", "grok").strip().lower()
_grok_api_key = getattr(config, "GROK_API_KEY", None)
_openai_api_key = getattr(config, "OPENAI_API_KEY", None)

# Determine which provider to use
if _llm_provider == "grok":
    _api_key = _grok_api_key
    _api_key_name = "GROK_API_KEY"
    _base_url = "https://api.x.ai/v1"
    _default_model = "grok-3"
else:
    _api_key = _openai_api_key
    _api_key_name = "OPENAI_API_KEY"
    _base_url = None  # OpenAI default
    _default_model = "gpt-3.5-turbo"

_api_key_missing = not _api_key
if _api_key_missing:
    logger.warning(
        f"⚠️ {_api_key_name} is missing. Set this in your .env or config_local.py to use AI commands."
    )
    llm_client = None
else:
    if _base_url:
        # Grok uses OpenAI-compatible API at api.x.ai
        llm_client = AsyncOpenAI(api_key=_api_key, base_url=_base_url)
        logger.info(f"✅ Grok client initialized (model: {_default_model})")
    else:
        # OpenAI
        llm_client = AsyncOpenAI(api_key=_api_key)
        logger.info(f"✅ OpenAI client initialized (model: {_default_model})")

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
        logger.warning("⚠️ Grok temperature setting invalid — fallback to API default.")
        temperature_value = None

    return model_value, temperature_value


async def ask_gpt(messages, user_id=None, model: Optional[str] = None, guild_id: Optional[int] = None, _is_retry: bool = False, include_reflections: bool = True):
    """
    Main Grok interaction function.
    
    Args:
        messages: List of message dicts or string prompt
        user_id: User ID for logging and reflection context loading (Discord ID)
        model: Model override
        guild_id: Guild ID for logging
        _is_retry: Internal flag to prevent re-queuing on retry attempts
        include_reflections: Whether to include user reflections as context (default: True)
    """
    start = time.perf_counter()

    try:
        if _api_key_missing or llm_client is None:
            raise RuntimeError(
                f"{_api_key_name} is missing. Set the key (.env or config_local.py) and restart the bot."
            )

        # 👉 Check if messages is a string (old style prompt)
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        assert isinstance(messages, list) and all(isinstance(m, dict) for m in messages), "❌ Invalid messages format"

        # Load reflection context if enabled and user_id provided
        reflection_context = ""
        if include_reflections and user_id:
            try:
                from gpt.context_loader import load_user_reflections
                reflection_context = await load_user_reflections(user_id, limit=5)
            except Exception as e:
                logger.debug(f"Failed to load reflection context: {e}")
                # Continue without context - non-critical

        # Build system prompt with optional reflection context
        system_content = SYSTEM_PROMPT
        if reflection_context:
            system_content = SYSTEM_PROMPT + "\n\n" + reflection_context

        resolved_model, temperature = _get_settings_values(model or _default_model)
        chat_kwargs = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_content},
                *messages
            ],
        }
        if temperature is not None:
            chat_kwargs["temperature"] = temperature

        response = await llm_client.chat.completions.create(**chat_kwargs)
        latency = (time.perf_counter() - start) * 1000 if response else 0  # in ms
        tokens = response.usage.total_tokens if response.usage else 0

        # Log success with the actual model used (updates current_model in status logs)
        log_gpt_success(user_id=user_id, tokens_used=tokens, latency_ms=int(latency), guild_id=guild_id, model=resolved_model)
        return response.choices[0].message.content

    except Exception as e:
        error_type = f"{type(e).__name__}: {str(e)}"
        
        # Check if this is a retryable error (rate limit or API error)
        is_retryable = False
        status_code = None
        
        # Check for rate limit (429) or server errors (500, 503)
        status_code = getattr(e, "status_code", None)
        if status_code is not None and isinstance(status_code, int):
            if status_code in [429, 500, 503]:
                is_retryable = True
        elif "rate limit" in str(e).lower() or "429" in str(e):
            is_retryable = True
        elif "503" in str(e) or "500" in str(e):
            is_retryable = True
        
        log_gpt_error(error_type=error_type, user_id=user_id, guild_id=guild_id)
        
        # If retryable and not already a retry attempt, add to queue and return fallback message
        if is_retryable and not _is_retry:
            _add_to_retry_queue(messages, user_id, model or _default_model, guild_id)
            logger.warning(f"⚠️ Grok error (retryable): {error_type}. Returning fallback message and queuing for retry.")
            return FALLBACK_MESSAGE
        
        # Non-retryable errors or retry attempts that fail: raise as before
        raise


async def ask_gpt_vision(
    prompt: str,
    image_url: str,
    *,
    user_id: Optional[int] = None,
    model: Optional[str] = None,
    guild_id: Optional[int] = None,
) -> str:
    """
    Vision-capable helper for image-based analysis.

    This uses the same client as `ask_gpt` but constructs a multi-part message
    with both text and an image URL. The caller is responsible for providing
    a safe image URL (typically a Discord CDN URL).
    """
    start = time.perf_counter()

    try:
        if _api_key_missing or llm_client is None:
            raise RuntimeError(
                f"{_api_key_name} is missing. Set the key (.env or config_local.py) and restart the bot."
            )

        # Resolve model and optional temperature from settings
        resolved_model, temperature = _get_settings_values(model or _default_model)

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                    {
                        "type": "input_image",
                        "image_url": {
                            "url": image_url,
                        },
                    },
                ],
            },
        ]

        chat_kwargs: dict = {
            "model": resolved_model,
            "messages": messages,
        }
        if temperature is not None:
            chat_kwargs["temperature"] = temperature

        response = await llm_client.chat.completions.create(**chat_kwargs)
        latency = (time.perf_counter() - start) * 1000 if response else 0  # in ms
        tokens = response.usage.total_tokens if response.usage else 0

        log_gpt_success(
            user_id=user_id,
            tokens_used=tokens,
            latency_ms=int(latency),
            guild_id=guild_id,
            model=resolved_model,
        )
        return response.choices[0].message.content or ""

    except Exception as e:
        error_type = f"{type(e).__name__}: {str(e)}"
        log_gpt_error(error_type=error_type, user_id=user_id, guild_id=guild_id)
        raise
