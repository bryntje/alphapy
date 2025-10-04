import discord
from discord.ext import commands
import asyncpg
import config
from typing import Any, Optional
from utils.logger import logger

class GDPRAnnouncement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = getattr(bot, "settings", None)

    @commands.command(name="postgdpr")
    @commands.is_owner()
    async def post_gdpr(self, ctx: commands.Context) -> None:
        """
        Post the GDPR Data Processing and Confidentiality Agreement in the designated channel and pin the message.
        """
        if not self._is_enabled():
            await ctx.send("⚠️ GDPR-functionaliteit is momenteel uitgeschakeld.")
            return

        channel_id = self._get_channel_id()
        if not channel_id:
            await ctx.send("⚠️ Geen GDPR kanaal ingesteld.")
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        if channel is None:
            await ctx.send("GDPR channel not found.")
            return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("GDPR channel moet een tekstkanaal zijn.")
            return

        gdpr_text = (
            "**Data Processing and Confidentiality Agreement for Server Members**\n\n"
            "**Effective Date:** 02/11/2025\n\n"
            "**1. Introduction**\n"
            "As a member of AlphaPips™ - The Next Chapter (\"the Server\"), you may be granted access to certain personal data collected "
            "through our onboarding process and other procedures. This document is intended to make you aware of your responsibilities "
            "regarding the processing, storage, and protection of such data in accordance with the General Data Protection Regulation (GDPR).\n\n"
            "**2. Definitions**\n"
            "- **Personal Data:** Any information relating to an identified or identifiable natural person, including but not limited to name, email address, and other contact or identification details.\n"
            "- **Processing:** Any operation or set of operations performed on personal data, whether or not by automated means, such as collection, recording, organization, storage, consultation, use, disclosure, or deletion.\n\n"
            "**3. Purpose and Scope**\n"
            "This Agreement applies to all members who are granted access to personal data within the Server by virtue of their role or specific access rights. "
            "By obtaining such access, you confirm that you will use this data solely for the purposes for which it was collected and that you will take "
            "all necessary measures to ensure the privacy and security of the data.\n\n"
            "**4. Responsibilities and Obligations**\n"
            "As a member with access to personal data, you agree to:\n"
            "- Treat the personal data confidentially and not disclose it to unauthorized third parties.\n"
            "- Use the data solely for the legitimate purposes defined by the Server.\n"
            "- Implement all necessary technical and organizational measures to prevent unauthorized access, loss, theft, or disclosure of the data.\n"
            "- Immediately report to the Server administrators if you suspect that the data is being processed in violation of the GDPR or if a data breach occurs.\n\n"
            "**5. Security**\n"
            "You commit to protecting the personal data provided using appropriate security measures (such as strong passwords, encryption, and secure storage) "
            "to minimize the risk of unauthorized access or misuse.\n\n"
            "**6. Retention and Deletion**\n"
            "Personal data will be retained only as long as necessary for the legitimate purposes of the Server. If you are responsible for processing data, "
            "you must ensure that any data no longer needed is securely deleted or anonymized.\n\n"
            "**7. Access and Rights**\n"
            "If you have access to personal data through your role or function, you confirm that you will not use this data for purposes inconsistent with the GDPR. "
            "Furthermore, you agree to cooperate with any requests from data subjects for access, correction, or deletion of their personal data.\n\n"
            "**8. Sanctions for Non-Compliance**\n"
            "In the event of a breach of this Agreement or the GDPR, disciplinary measures may be taken, ranging from revoking access to personal data to removal "
            "from the Server. Additionally, legal action may be pursued if the violation results in damage or data breaches.\n\n"
            "**9. Amendments to the Agreement**\n"
            "This Agreement may be amended periodically. All members will be notified of any changes. It is your responsibility to remain informed of the current terms.\n\n"
            "**10. Acceptance**\n"
            "By gaining access to personal data within the Server, you confirm that you have read, understood, and accept this Agreement. "
            "You acknowledge that you are responsible for protecting the personal data and that you will act in accordance with the GDPR."
        )

        embed = discord.Embed(
            title="GDPR Data Processing Agreement",
            description=gdpr_text,
            color=discord.Color.blue()
        )
        message = await channel.send(embed=embed, view=GDPRView(self.bot))
        await message.pin()
        await ctx.send("GDPR document posted and pinned.")

    def _is_enabled(self) -> bool:
        if self.settings:
            try:
                return bool(self.settings.get("gdpr", "enabled"))
            except KeyError:
                pass
        return True

    def _get_channel_id(self) -> Optional[int]:
        if self.settings:
            try:
                value = self.settings.get("gdpr", "channel_id")
                if value:
                    return int(value)
            except KeyError:
                pass
            except (TypeError, ValueError):
                logger.warning("⚠️ GDPR: channel_id setting ongeldig.")
        return getattr(config, "GDPR_CHANNEL_ID", 0)

class GDPRView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.settings = getattr(bot, "settings", None)
        self.add_item(GDPRButton(bot))

class GDPRButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot):
        super().__init__(label="I Agree", style=discord.ButtonStyle.success, custom_id="gdpr_agree")
        self.bot = bot
        self.settings = getattr(bot, "settings", None)
    
    async def callback(self, interaction: discord.Interaction) -> None:
        if not self._is_enabled():
            await interaction.response.send_message("⚠️ GDPR-functionaliteit is momenteel uitgeschakeld.", ephemeral=True)
            return
        await store_gdpr_acceptance(interaction.user.id)
        await interaction.response.send_message("Thank you for accepting the GDPR terms.", ephemeral=True)

    def _is_enabled(self) -> bool:
        if self.settings:
            try:
                return bool(self.settings.get("gdpr", "enabled"))
            except KeyError:
                pass
        return True

async def store_gdpr_acceptance(user_id: int) -> None:
    """Slaat de GDPR-acceptatie op in PostgreSQL."""
    try:
        conn = await asyncpg.connect(config.DATABASE_URL)
        await conn.execute(
            """
            INSERT INTO gdpr_acceptance (user_id, accepted, timestamp)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET accepted = $2, timestamp = CURRENT_TIMESTAMP;
            """,
            user_id, 1
        )
        await conn.close()
        logger.info(f"✅ GDPR-acceptatie opgeslagen voor {user_id}")
    except Exception as e:
        logger.exception(f"❌ Fout bij opslaan GDPR-acceptatie voor {user_id}: {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GDPRAnnouncement(bot))
    bot.add_view(GDPRView(bot))
