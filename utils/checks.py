from discord.ext import commands
import discord
import config

def is_owner_or_admin():
    async def predicate(ctx):
        # Controleer of de gebruiker de bot-owner is via de ingebouwde check
        if await commands.is_owner().predicate(ctx):
            return True
        # Controleer of de gebruiker in de extra owner-ID's zit
        if ctx.author.id in config.OWNER_IDS:
            return True
        # Controleer of de gebruiker de admin-rol heeft
        admin_role = discord.utils.get(ctx.author.roles, id=config.ADMIN_ROLE_ID)
        return admin_role is not None
    return commands.check(predicate)
