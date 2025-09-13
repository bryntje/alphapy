import io
import csv
import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.checks_interaction import is_owner_or_admin_interaction


class Exports(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn: Optional[asyncpg.Connection] = None
        self.bot.loop.create_task(self._setup())

    async def _setup(self) -> None:
        try:
            self.conn = await asyncpg.connect(config.DATABASE_URL)
        except Exception:
            self.conn = None

    @app_commands.command(name="export_tickets", description="Export tickets as CSV (admin)")
    @app_commands.describe(scope="Optional: 7d, 30d, all (default: all)")
    async def export_tickets(self, interaction: discord.Interaction, scope: Optional[str] = "all"):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not self.conn:
            await interaction.followup.send("❌ Database not connected.", ephemeral=True)
            return
        where = ""
        if scope == "7d":
            where = "WHERE created_at >= NOW() - INTERVAL '7 days'"
        elif scope == "30d":
            where = "WHERE created_at >= NOW() - INTERVAL '30 days'"
        rows = await self.conn.fetch(
            f"SELECT id, user_id, username, status, created_at, updated_at, claimed_by, channel_id FROM support_tickets {where} ORDER BY id DESC"
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id","user_id","username","status","created_at","updated_at","claimed_by","channel_id"])
        for r in rows:
            writer.writerow([
                r.get("id"), r.get("user_id"), r.get("username"), r.get("status"),
                r.get("created_at"), r.get("updated_at"), r.get("claimed_by"), r.get("channel_id")
            ])
        data = discord.File(io.BytesIO(buf.getvalue().encode("utf-8")), filename=f"tickets_{scope or 'all'}.csv")
        await interaction.followup.send(content=f"✅ Exported {len(rows)} tickets (scope={scope}).", file=data, ephemeral=True)

    @app_commands.command(name="export_faq", description="Export FAQ entries as CSV (admin)")
    async def export_faq(self, interaction: discord.Interaction):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not self.conn:
            await interaction.followup.send("❌ Database not connected.", ephemeral=True)
            return
        rows = await self.conn.fetch("SELECT id, title, summary, keywords, created_at FROM faq_entries ORDER BY id DESC")
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id","title","summary","keywords","created_at"])
        for r in rows:
            writer.writerow([r.get("id"), r.get("title"), r.get("summary"), ";".join(r.get("keywords") or []), r.get("created_at")])
        data = discord.File(io.BytesIO(buf.getvalue().encode("utf-8")), filename="faq.csv")
        await interaction.followup.send(content=f"✅ Exported {len(rows)} FAQ entries.", file=data, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Exports(bot))


