import discord
import asyncio
from discord.ext import commands
from discord import app_commands
from cogs.gdpr import GDPRView
from utils.logger import logger
from gpt.helpers import set_bot_instance


try:
    import config_local as config
except ImportError:
    import config

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

# Event: Bot is klaar
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    
    logger.info(f"{bot.user} is online! ✅ Intents actief: {bot.intents}")
    logger.info(f"🔍 Ingeladen GUILD_ID vanuit config: {config.GUILD_ID}")

    logger.info("📡 Bekende guilds:")
    for guild in bot.guilds:
        logger.info(f"🔹 {guild.name} (ID: {guild.id})")

    if config.GUILD_ID not in [guild.id for guild in bot.guilds]:
        logger.error("❌ Error: De bot is NIET geconnecteerd aan de juiste server! Controleer of je hem correct hebt gejoined.")
    
    bot.add_view(GDPRView())


set_bot_instance(bot)


@bot.event
async def on_command_error(ctx, error):
    logger.error(f"⚠️ Error in command '{ctx.command}': {error}")
    await ctx.send("❌ Oops! An error occurred. Please try again later.")


async def setup_hook():
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
    await bot.load_extension("cogs.reminders")
    await bot.load_extension("cogs.embed_watcher")




bot.setup_hook = setup_hook
Thread(target=start_api, daemon=True).start()


# Bot starten
bot.run(config.BOT_TOKEN)
