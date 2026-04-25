
from discord.ext import commands

import config
from utils.cog_base import AlphaCog
from utils.gdpr_helpers import GDPRView
from utils.logger import logger


class GDPRAnnouncement(AlphaCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    def _is_enabled(self, guild_id: int) -> bool:
        if self.settings:
            try:
                return bool(self.settings.get("gdpr", "enabled", guild_id))
            except KeyError:
                pass
        return True

    def _get_channel_id(self, guild_id: int) -> int | None:
        if self.settings:
            try:
                value = self.settings.get("gdpr", "channel_id", guild_id)
                if value:
                    return int(value)
            except KeyError:
                pass
            except (TypeError, ValueError):
                logger.warning("GDPR: Invalid channel_id setting.")
        return getattr(config, "GDPR_CHANNEL_ID", 0)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GDPRAnnouncement(bot))
    bot.add_view(GDPRView(bot))
