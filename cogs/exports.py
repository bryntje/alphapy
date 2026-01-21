import io
import csv
import asyncpg
from asyncpg import exceptions as pg_exceptions
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.validators import validate_admin
from utils.db_helpers import acquire_safe, is_pool_healthy
from utils.logger import logger


class Exports(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None
        self.bot.loop.create_task(self._setup())

    async def _setup(self) -> None:
        try:
            self.db = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=1,
                max_size=5,
                command_timeout=10.0
            )
        except Exception as e:
            logger.error(f"❌ Exports: DB pool creation error: {e}")
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None

    async def cog_unload(self):
        """Called when the cog is unloaded - close the database pool."""
        if self.db:
            try:
                await self.db.close()
            except Exception:
                pass
            self.db = None

    @app_commands.command(name="export_tickets", description="Export tickets as CSV (admin)")
    @app_commands.describe(scope="Optional: 7d, 30d, all (default: all)")
    async def export_tickets(self, interaction: discord.Interaction, scope: Optional[str] = "all"):
        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not is_pool_healthy(self.db):
            await interaction.followup.send("❌ Database not connected.", ephemeral=True)
            return
        try:
            where = ""
            if scope == "7d":
                where = "WHERE created_at >= NOW() - INTERVAL '7 days'"
            elif scope == "30d":
                where = "WHERE created_at >= NOW() - INTERVAL '30 days'"
            async with acquire_safe(self.db) as conn:
                rows = await conn.fetch(
                    f"SELECT id, user_id, username, status, created_at, updated_at, claimed_by, channel_id FROM support_tickets {where} ORDER BY id DESC"
                )
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in export_tickets: {conn_err}")
            await interaction.followup.send("❌ Database connection error. Please try again later.", ephemeral=True)
            return
        except Exception as e:
            logger.error(f"Database error in export_tickets: {e}")
            await interaction.followup.send(f"❌ Error exporting tickets: {e}", ephemeral=True)
            return
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
        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(error_msg or "⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not is_pool_healthy(self.db):
            await interaction.followup.send("❌ Database not connected.", ephemeral=True)
            return
        try:
            async with acquire_safe(self.db) as conn:
                rows = await conn.fetch("SELECT id, title, summary, keywords, created_at FROM faq_entries ORDER BY id DESC")
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in export_faq: {conn_err}")
            await interaction.followup.send("❌ Database connection error. Please try again later.", ephemeral=True)
            return
        except Exception as e:
            logger.error(f"Database error in export_faq: {e}")
            await interaction.followup.send(f"❌ Error exporting FAQ: {e}", ephemeral=True)
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id","title","summary","keywords","created_at"])
        for r in rows:
            writer.writerow([r.get("id"), r.get("title"), r.get("summary"), ";".join(r.get("keywords") or []), r.get("created_at")])
        data = discord.File(io.BytesIO(buf.getvalue().encode("utf-8")), filename="faq.csv")
        await interaction.followup.send(content=f"✅ Exported {len(rows)} FAQ entries.", file=data, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Exports(bot))


