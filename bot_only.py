import discord
import asyncio
from discord.ext import commands
from discord import app_commands
from cogs.gdpr import GDPRView
from utils.logger import logger
from gpt.helpers import set_bot_instance
from utils.settings_service import SettingsService, SettingDefinition
import config
from typing import Optional


# Intentions instellen
intents = discord.Intents.default()
intents.messages = True
intents.reactions = True  # ✅ Nodig voor reaction roles
intents.guilds = True
intents.members = True  # ✅ Nodig om leden te herkennen
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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
        scope="gpt",
        key="model",
        description="Standaard AI-model voor GPT commando's (grok-beta voor Grok, gpt-3.5-turbo/gpt-4 voor OpenAI).",
        value_type="str",
        default="grok-beta",
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

# Event: Bot is klaar
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    logger.info(f"{bot.user} is online! ✅ Intents actief: {bot.intents}")

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



bot.setup_hook = setup_hook
# API server wordt apart gedraaid in de dashboard service


# Start bot
token: Optional[str] = getattr(config, "BOT_TOKEN", None)
if not token:
    raise RuntimeError("BOT_TOKEN is not set in the config.")
bot.run(token)
