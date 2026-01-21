"""
Database migration management commands for Alembic.

Provides Discord commands to check migration status and apply migrations.
"""

import discord
from discord.ext import commands
from discord import app_commands
import subprocess
import sys
import os
from typing import Optional
from utils.checks_interaction import is_owner_or_admin_interaction
from utils.logger import logger
import config


class Migrations(commands.Cog):
    """Database migration management commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="migrate", description="Database migration management")
    @app_commands.describe(action="Action to perform: 'status', 'upgrade', 'downgrade', 'history'")
    async def migrate(self, interaction: discord.Interaction, action: str = "status"):
        """Manage database migrations."""
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        if action.lower() == "status":
            result = await self._get_migration_status()
            await interaction.followup.send(f"```\n{result}\n```", ephemeral=True)
        elif action.lower() == "upgrade":
            result = await self._run_migration("upgrade", "head")
            await interaction.followup.send(f"```\n{result}\n```", ephemeral=True)
        elif action.lower() == "downgrade":
            result = await self._run_migration("downgrade", "-1")
            await interaction.followup.send(f"```\n⚠️ Downgrade executed:\n{result}\n```", ephemeral=True)
        elif action.lower() == "history":
            result = await self._run_migration("history")
            await interaction.followup.send(f"```\n{result}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Unknown action: {action}. Use 'status', 'upgrade', 'downgrade', or 'history'.", ephemeral=True)
    
    async def _get_migration_status(self) -> str:
        """Get current migration status."""
        try:
            result = subprocess.run(
                ["python3", "-m", "alembic", "current"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd="."
            )
            if result.returncode == 0:
                return result.stdout.strip() or "No migrations applied"
            else:
                return f"Error: {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return "Timeout: Migration check took too long"
        except Exception as e:
            logger.error(f"Migration status check failed: {e}")
            return f"Error: {str(e)}"
    
    async def _run_migration(self, command: str, args: str = "") -> str:
        """Run an Alembic migration command."""
        try:
            cmd = ["python3", "-m", "alembic", command]
            if args:
                cmd.append(args)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=".",
                env={**dict(os.environ), "DATABASE_URL": config.DATABASE_URL or ""}
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                logger.info(f"Migration {command} {args} completed successfully")
                return output or f"Migration {command} completed successfully"
            else:
                error = result.stderr.strip()
                logger.error(f"Migration {command} {args} failed: {error}")
                return f"Error: {error}"
        except subprocess.TimeoutExpired:
            logger.error(f"Migration {command} {args} timed out")
            return f"Timeout: Migration took too long"
        except Exception as e:
            logger.error(f"Migration {command} {args} failed: {e}")
            return f"Error: {str(e)}"
    
    @app_commands.command(name="migrate_status", description="Check database migration status")
    async def migrate_status(self, interaction: discord.Interaction):
        """Check current migration status (alias for /migrate status)."""
        await self.migrate(interaction, action="status")


async def setup(bot: commands.Bot):
    await bot.add_cog(Migrations(bot))
