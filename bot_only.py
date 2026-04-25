
from typing import cast

import discord
from discord.ext import commands

import config
from bot_types import AlphapyBot
from cogs.gdpr import GDPRView
from gpt.helpers import set_bot_instance
from utils.logger import logger
from utils.settings_service import SettingDefinition, SettingsService

# Set intents
intents = discord.Intents.default()
intents.messages = True
intents.reactions = True  # Required for reaction roles
intents.guilds = True
intents.members = True  # Required to recognize members
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
typed_bot = cast(AlphapyBot, bot)

settings_service = SettingsService(getattr(config, "DATABASE_URL", None))
settings_service.register(
    SettingDefinition(
        scope="system",
        key="log_channel_id",
        description="Channel for status and error messages.",
        value_type="channel",
        default=0,  # Must be configured per guild
    )
)
settings_service.register(
    SettingDefinition(
        scope="system",
        key="rules_channel_id",
        description="Channel for rules and onboarding (welcome message + Start button).",
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
        scope="onboarding",
        key="join_role_id",
        description="Temporary role to assign immediately when a user joins (removed after onboarding/verification).",
        value_type="role",
        default=None,  # Optional - no role assigned if not set
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="announcements_channel_id",
        description="Channel monitored for auto-reminder embeds.",
        value_type="channel",
        default=0,  # Must be configured per guild
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="reminder_offset_minutes",
        description="Number of minutes before the event that the reminder is scheduled.",
        value_type="int",
        default=60,
        min_value=0,
        max_value=4320,
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
        description="Role for ticket escalation.",
        value_type="role",
        default=None,  # Must be configured per guild
        allow_null=True,
    )
)
# Default model depends on LLM_PROVIDER (grok-3 for Grok, gpt-3.5-turbo for OpenAI)
_default_llm_model = "grok-3" if getattr(config, "LLM_PROVIDER", "grok").strip().lower() == "grok" else "gpt-3.5-turbo"
settings_service.register(
    SettingDefinition(
        scope="gpt",
        key="model",
        description="Default AI model for Grok commands (e.g. grok-3).",
        value_type="str",
        default=_default_llm_model,
    )
)
settings_service.register(
    SettingDefinition(
        scope="gpt",
        key="temperature",
        description="Temperature (creativity) for Grok responses.",
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
        description="Enable the invite tracker feature.",
        value_type="bool",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="invites",
        key="announcement_channel_id",
        description="Channel for automatic invite notifications.",
        value_type="channel",
        default=0,  # Must be configured per guild
    )
)
settings_service.register(
    SettingDefinition(
        scope="invites",
        key="with_inviter_template",
        description="Message template when an inviter is found.",
        value_type="str",
        default="{member} joined! {inviter} now has {count} invites.",
    )
)
settings_service.register(
    SettingDefinition(
        scope="invites",
        key="no_inviter_template",
        description="Message template when no inviter is found.",
        value_type="str",
        default="{member} joined, but no inviter data found.",
    )
)
settings_service.register(
    SettingDefinition(
        scope="gdpr",
        key="enabled",
        description="Enable GDPR handler for command and button.",
        value_type="bool",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="gdpr",
        key="channel_id",
        description="Channel where the GDPR document is posted.",
        value_type="channel",
        default=0,  # Must be configured per guild
    )
)
settings_service.register(
    SettingDefinition(
        scope="reminders",
        key="enabled",
        description="Enable the reminders feature.",
        value_type="bool",
        default=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="reminders",
        key="default_channel_id",
        description="Default channel for new reminders (optional).",
        value_type="channel",
        default=0,  # Must be configured per guild
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="reminders",
        key="allow_everyone_mentions",
        description="Allow @everyone in reminders.",
        value_type="bool",
        default=False,  # Must be configured per guild
    )
)

# Event: Bot is ready
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    logger.info(f"{bot.user} is online! Intents active: {bot.intents}")

    logger.info("📡 Known guilds:")
    for guild in bot.guilds:
        logger.info(f"🔹 {guild.name} (ID: {guild.id})")

    logger.info(f"✅ Bot has successfully started and connected to {len(bot.guilds)} server(s)!")
    
    bot.add_view(GDPRView(bot))


set_bot_instance(bot)


@bot.event
async def on_command_error(ctx, error):
    logger.error(f"⚠️ Error in command '{ctx.command}': {error}")
    await ctx.send("❌ Oops! An error occurred. Please try again later.")


async def setup_hook():
    await settings_service.setup()
    typed_bot.settings = settings_service

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
    await bot.load_extension("cogs.premium")
    await bot.load_extension("cogs.reminders")
    await bot.load_extension("cogs.embed_watcher")
    await bot.load_extension("cogs.ticketbot")
    await bot.load_extension("cogs.faq")
    await bot.load_extension("cogs.exports")



bot.setup_hook = setup_hook
# API server is run separately in the dashboard service


# Start bot: uses BOT_TOKEN_ACTIVE (BOT_TOKEN_TEST when USE_TEST_BOT=1, else BOT_TOKEN)
token: str | None = getattr(config, "BOT_TOKEN_ACTIVE", None)
if not token:
    raise RuntimeError("BOT_TOKEN (or BOT_TOKEN_TEST when USE_TEST_BOT=1) is not set in the config.")
bot.run(token)
