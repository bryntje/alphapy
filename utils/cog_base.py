"""
AlphaCog — Base class for all Alphapy Discord cogs.

Centralises the SettingsService and CachedSettingsHelper wiring that was
previously copy-pasted into every cog __init__.  Subclasses call
``super().__init__(bot)`` and immediately have:

    self.bot            — the discord.py Bot instance
    self.settings       — SettingsService (raises RuntimeError if absent)
    self.settings_helper — CachedSettingsHelper wrapping self.settings
"""

from discord.ext import commands

from utils.settings_helpers import CachedSettingsHelper


class AlphaCog(commands.Cog):
    """Base cog that wires up SettingsService and CachedSettingsHelper."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        settings = getattr(bot, "settings", None)
        if settings is None or not hasattr(settings, "get"):
            raise RuntimeError("SettingsService not available on bot instance")
        self.settings = settings  # type: ignore[assignment]
        self.settings_helper = CachedSettingsHelper(settings)  # type: ignore[arg-type]
