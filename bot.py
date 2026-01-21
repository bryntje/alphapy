import discord
import asyncio
import time
from discord.ext import commands
from discord import app_commands
from cogs.gdpr import GDPRView
from utils.logger import logger
from gpt.helpers import set_bot_instance
from utils.settings_service import SettingsService, SettingDefinition
import config
from typing import Optional

from threading import Thread
import uvicorn

def start_api():
    uvicorn.run("api:app", host="0.0.0.0", port=8000)


# Intentions instellen
intents = discord.Intents.default()
intents.messages = True
intents.reactions = True  # ✅ Nodig voor reaction roles
intents.guilds = True
intents.members = True  # ✅ Nodig om leden te herkennen
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Set start_time for uptime tracking
setattr(bot, "start_time", time.time())

settings_service = SettingsService(getattr(config, "DATABASE_URL", None))
settings_service.register(
    SettingDefinition(
        scope="system",
        key="log_channel_id",
        description="Kanaal voor status- en foutmeldingen.",
        value_type="channel",
        default=0,  # Moet per guild geconfigureerd worden
    )
)
settings_service.register(
    SettingDefinition(
        scope="system",
        key="rules_channel_id",
        description="Channel for rules and onboarding (#rules).",
        value_type="channel",
        default=0,  # Must be configured per guild
    )
)
settings_service.register(
    SettingDefinition(
        scope="system",
        key="onboarding_channel_id",
        description="Channel where onboarding takes place.",
        value_type="channel",
        default=0,  # Must be configured per guild
    )
)
settings_service.register(
    SettingDefinition(
        scope="onboarding",
        key="enabled",
        description="Whether onboarding is enabled for this guild.",
        value_type="boolean",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="onboarding",
        key="mode",
        description="Onboarding mode: 'disabled', 'rules_only', 'rules_with_questions', 'questions_only'",
        value_type="string",
        default="rules_with_questions",
    )
)
settings_service.register(
    SettingDefinition(
        scope="onboarding",
        key="completion_role_id",
        description="Role to assign after onboarding completion.",
        value_type="role",
        default=None,  # Optional - no role assigned if not set
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="announcements_channel_id",
        description="Kanaal dat gecontroleerd wordt op auto-reminder embeds.",
        value_type="channel",
        default=0,  # Moet per guild geconfigureerd worden
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="reminder_offset_minutes",
        description="Aantal minuten vóór het event dat de reminder gepland wordt.",
        value_type="int",
        default=60,
        min_value=0,
        max_value=4320,
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="gpt_fallback_enabled",
        description="Enable GPT fallback parsing when structured parsing fails.",
        value_type="bool",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="failed_parse_log_channel_id",
        description="Channel to log failed parse attempts (optional, defaults to log channel).",
        value_type="channel",
        default=0,
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="non_embed_enabled",
        description="Enable parsing of non-embed messages (plain text messages) for reminders.",
        value_type="bool",
        default=False,
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="process_bot_messages",
        description="Enable processing of embeds/messages sent by the bot itself (e.g., from /embed command).",
        value_type="bool",
        default=False,
    )
)
settings_service.register(
    SettingDefinition(
        scope="ticketbot",
        key="category_id",
        description="Category where new ticket channels are created.",
        value_type="channel",
        default=0,  # Must be configured per guild
    )
)
settings_service.register(
    SettingDefinition(
        scope="ticketbot",
        key="staff_role_id",
        description="Role that gets access to ticket channels.",
        value_type="role",
        default=None,  # Must be configured per guild
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="ticketbot",
        key="escalation_role_id",
        description="Rol voor escalatie van tickets.",
        value_type="role",
        default=None,  # Must be configured per guild
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="ticketbot",
        key="idle_days_threshold",
        description="Days of inactivity before sending idle reminder (default: 5).",
        value_type="int",
        default=5,
        min_value=1,
        max_value=30,
    )
)
settings_service.register(
    SettingDefinition(
        scope="ticketbot",
        key="auto_close_days_threshold",
        description="Days of inactivity before auto-closing ticket (default: 14).",
        value_type="int",
        default=14,
        min_value=1,
        max_value=90,
    )
)
# Default model depends on LLM_PROVIDER (grok-3 for Grok, gpt-3.5-turbo for OpenAI)
_default_llm_model = "grok-3" if getattr(config, "LLM_PROVIDER", "grok").strip().lower() == "grok" else "gpt-3.5-turbo"
settings_service.register(
    SettingDefinition(
        scope="gpt",
        key="model",
        description="Standaard AI-model voor GPT commando's (grok-3 voor Grok, gpt-3.5-turbo/gpt-4 voor OpenAI).",
        value_type="str",
        default=_default_llm_model,
    )
)
settings_service.register(
    SettingDefinition(
        scope="gpt",
        key="temperature",
        description="Temperatuur (creativiteit) voor GPT antwoorden.",
        value_type="float",
        default=0.7,
        min_value=0.0,
        max_value=2.0,
    )
)
settings_service.register(
    SettingDefinition(
        scope="invites",
        key="enabled",
        description="Schakel de invite tracker functionaliteit in.",
        value_type="bool",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="invites",
        key="announcement_channel_id",
        description="Kanaal voor automatische invite meldingen.",
        value_type="channel",
        default=0,  # Moet per guild geconfigureerd worden
    )
)
settings_service.register(
    SettingDefinition(
        scope="invites",
        key="with_inviter_template",
        description="Berichttemplate wanneer een inviter gevonden is.",
        value_type="str",
        default="{member} joined! {inviter} now has {count} invites.",
    )
)
settings_service.register(
    SettingDefinition(
        scope="invites",
        key="no_inviter_template",
        description="Berichttemplate wanneer geen inviter gevonden is.",
        value_type="str",
        default="{member} joined, but no inviter data found.",
    )
)
settings_service.register(
    SettingDefinition(
        scope="gdpr",
        key="enabled",
        description="Schakel GDPR handler in voor command en button.",
        value_type="bool",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="gdpr",
        key="channel_id",
        description="Kanaal waarin het GDPR-document gepost wordt.",
        value_type="channel",
        default=0,  # Moet per guild geconfigureerd worden
    )
)
settings_service.register(
    SettingDefinition(
        scope="reminders",
        key="enabled",
        description="Schakel de reminders functionaliteit in.",
        value_type="bool",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="reminders",
        key="default_channel_id",
        description="Standaard kanaal voor nieuwe reminders (optioneel).",
        value_type="channel",
        default=0,  # Moet per guild geconfigureerd worden
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="reminders",
        key="allow_everyone_mentions",
        description="Sta @everyone toe bij reminders.",
        value_type="bool",
        default=False,  # Moet per guild geconfigureerd worden
    )
)
settings_service.register(
    SettingDefinition(
        scope="system",
        key="log_level",
        description="Log verbosity level: verbose (all), normal (no debug), critical (errors + config only).",
        value_type="string",
        default="verbose",
        choices=["verbose", "normal", "critical"],
    )
)

# Event: Bot is klaar
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    # Set start_time for uptime tracking if not already set
    if not hasattr(bot, "start_time"):
        import time
        setattr(bot, "start_time", time.time())  # pyright: ignore[reportGeneralTypeIssues]
    
    # Initialize command tracker with database pool in bot's event loop
    # Note: on_ready() can be called multiple times (e.g., on reconnect),
    # so set_db_pool() handles closing any existing pool before setting a new one
    try:
        import asyncpg
        from utils.command_tracker import set_db_pool, _db_pool
        # Only create new pool if we don't have one or it's closing
        if _db_pool is None or _db_pool.is_closing():
            command_tracker_pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=1,
                max_size=5,
                command_timeout=10.0
            )
            set_db_pool(command_tracker_pool)
            logger.info("✅ Command tracker: Database pool initialized in bot event loop")
        else:
            logger.debug("Command tracker: Database pool already initialized, skipping")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize command tracker pool: {e}")
    
    # Start GPT retry queue task now that event loop is running
    from gpt.helpers import _retry_task, _retry_gpt_requests
    import gpt.helpers as gpt_helpers
    if gpt_helpers._retry_task is None or gpt_helpers._retry_task.done():
        gpt_helpers._retry_task = asyncio.create_task(_retry_gpt_requests())
        logger.info("🔄 GPT retry queue task started")
    
    logger.info(f"{bot.user} is online! ✅ Intents actief: {bot.intents}")


    logger.info("📡 Known guilds:")
    for guild in bot.guilds:
        logger.info(f"🔹 {guild.name} (ID: {guild.id})")

    logger.info(f"✅ Bot has successfully started and connected to {len(bot.guilds)} server(s)!")
    
    bot.add_view(GDPRView(bot))


set_bot_instance(bot)  # This also starts the GPT retry queue task


@bot.event
async def on_command_error(ctx, error):
    logger.error(f"⚠️ Error in command '{ctx.command}': {error}")
    
    # Track command error
    try:
        from utils.command_tracker import log_command_usage
        command_name = ctx.command.name if ctx.command else "unknown"
        guild_id = ctx.guild.id if ctx.guild else None
        await log_command_usage(
            guild_id=guild_id,
            user_id=ctx.author.id,
            command_name=command_name,
            command_type="text",
            success=False,
            error_message=str(error)[:500]
        )
    except Exception:
        pass  # Don't break error handling if tracking fails
    
    await ctx.send("❌ Oops! An error occurred. Please try again later.")


@bot.event
async def on_command_completion(ctx):
    """Track successful text command execution."""
    try:
        from utils.command_tracker import log_command_usage
        command_name = ctx.command.name if ctx.command else "unknown"
        guild_id = ctx.guild.id if ctx.guild else None
        await log_command_usage(
            guild_id=guild_id,
            user_id=ctx.author.id,
            command_name=command_name,
            command_type="text",
            success=True
        )
    except Exception:
        pass  # Don't break command execution if tracking fails


@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command: discord.app_commands.Command):
    """Track successful slash command execution."""
    try:
        from utils.command_tracker import log_command_usage
        guild_id = interaction.guild.id if interaction.guild else None
        await log_command_usage(
            guild_id=guild_id,
            user_id=interaction.user.id,
            command_name=command.name,
            command_type="slash",
            success=True
        )
    except Exception:
        pass  # Don't break command execution if tracking fails


@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Track failed slash command execution."""
    try:
        from utils.command_tracker import log_command_usage
        command_name = interaction.command.name if interaction.command else "unknown"
        guild_id = interaction.guild.id if interaction.guild else None
        await log_command_usage(
            guild_id=guild_id,
            user_id=interaction.user.id,
            command_name=command_name,
            command_type="slash",
            success=False,
            error_message=str(error)[:500]
        )
    except Exception:
        pass  # Don't break error handling if tracking fails


async def setup_hook():
    await settings_service.setup()
    setattr(bot, "settings", settings_service)

    await bot.load_extension("cogs.onboarding")
    await bot.load_extension("cogs.reaction_roles")
    await bot.load_extension("cogs.slash_utils")
    await bot.load_extension("cogs.dataquery")
    await bot.load_extension("cogs.reload_commands")
    await bot.load_extension("cogs.gdpr")
    await bot.load_extension("cogs.inviteboard")
    await bot.load_extension("cogs.clean")
    await bot.load_extension("cogs.importdata")
    await bot.load_extension("cogs.importinvite")
    await bot.load_extension("cogs.migrate_gdpr")
    await bot.load_extension("cogs.lotquiz")
    await bot.load_extension("cogs.leadership")
    await bot.load_extension("cogs.status")
    await bot.load_extension("cogs.growth")
    await bot.load_extension("cogs.learn")
    await bot.load_extension("cogs.contentgen")
    await bot.load_extension("cogs.configuration")
    await bot.load_extension("cogs.reminders")
    await bot.load_extension("cogs.embed_watcher")
    await bot.load_extension("cogs.ticketbot")
    await bot.load_extension("cogs.faq")
    await bot.load_extension("cogs.exports")
    await bot.load_extension("cogs.migrations")



bot.setup_hook = setup_hook
# API server DRAIT WEL MEE voor health checks en monitoring data naar Mind
Thread(target=start_api, daemon=True).start()


# Start bot
token: Optional[str] = getattr(config, "BOT_TOKEN", None)
if not token:
    raise RuntimeError("BOT_TOKEN is not set in the config.")
bot.run(token)
