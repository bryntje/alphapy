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

settings_service = SettingsService(getattr(config, "DATABASE_URL", None))
settings_service.register(
    SettingDefinition(
        scope="system",
        key="log_channel_id",
        description="Kanaal voor status- en foutmeldingen.",
        value_type="channel",
        default=getattr(config, "WATCHER_LOG_CHANNEL", 0),
    )
)
settings_service.register(
    SettingDefinition(
        scope="embedwatcher",
        key="announcements_channel_id",
        description="Kanaal dat gecontroleerd wordt op auto-reminder embeds.",
        value_type="channel",
        default=getattr(config, "ANNOUNCEMENTS_CHANNEL_ID", 0),
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
        description="Categorie waarin nieuwe ticketkanalen worden aangemaakt.",
        value_type="channel",
        default=getattr(config, "TICKET_CATEGORY_ID", 1416148921960628275),
    )
)
settings_service.register(
    SettingDefinition(
        scope="ticketbot",
        key="staff_role_id",
        description="Rol die toegang krijgt tot ticketkanalen.",
        value_type="role",
        default=getattr(config, "TICKET_ACCESS_ROLE_ID", None),
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="ticketbot",
        key="escalation_role_id",
        description="Rol voor escalatie van tickets.",
        value_type="role",
        default=getattr(config, "TICKET_ESCALATION_ROLE_ID", None),
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="gpt",
        key="model",
        description="Standaard OpenAI-model voor GPT commando's.",
        value_type="str",
        default="gpt-3.5-turbo",
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
        default=getattr(config, "INVITE_ANNOUNCEMENT_CHANNEL_ID", 0),
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
        default=getattr(config, "GDPR_CHANNEL_ID", 0),
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
        default=0,
        allow_null=True,
    )
)
settings_service.register(
    SettingDefinition(
        scope="reminders",
        key="allow_everyone_mentions",
        description="Sta @everyone toe bij reminders.",
        value_type="bool",
        default=getattr(config, "ENABLE_EVERYONE_MENTIONS", False),
    )
)

# Event: Bot is klaar
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    logger.info(f"{bot.user} is online! ✅ Intents actief: {bot.intents}")

    logger.info("📡 Bekende guilds:")
    for guild in bot.guilds:
        logger.info(f"🔹 {guild.name} (ID: {guild.id})")

    logger.info(f"✅ Bot is succesvol opgestart en verbonden met {len(bot.guilds)} server(s)!")
    
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
Thread(target=start_api, daemon=True).start()


# Bot starten
token: Optional[str] = getattr(config, "BOT_TOKEN", None)
if not token:
    raise RuntimeError("BOT_TOKEN is niet ingesteld in de config.")
bot.run(token)
