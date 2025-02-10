import discord
import asyncio
from discord.ext import commands
from onboarding import Onboarding  # ✅ Import the Onboarding Cog

import config

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
    
    print(f"{bot.user} is online! ✅ Intents actief: {bot.intents}")
    print(f"🔍 Ingeladen GUILD_ID vanuit config: {config.GUILD_ID}")

    print("📡 Bekende guilds:")
    for guild in bot.guilds:
        print(f"🔹 {guild.name} (ID: {guild.id})")

    if config.GUILD_ID not in [guild.id for guild in bot.guilds]:
        print("❌ Error: De bot is NIET geconnecteerd aan de juiste server! Controleer of je hem correct hebt gejoined.")



@bot.event
async def on_raw_reaction_add(payload):
    print(f"🔄 Reaction detected: {payload.emoji.name} door {payload.user_id}")  # ✅ Moet altijd zichtbaar zijn


# Cogs laden (extra functies)
extensions = ["slash_commands", "reaction_roles"]

async def setup_hook():
    await bot.load_extension("onboarding")
    await bot.load_extension("reaction_roles")
    await bot.load_extension("slash_commands")
    await bot.load_extension("dataquery")
    await bot.load_extension("reload_commands")


bot.setup_hook = setup_hook

# Bot starten
bot.run(config.BOT_TOKEN)
