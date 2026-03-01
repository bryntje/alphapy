"""
Response helpers for consistent Discord interaction responses.
"""
import discord
from typing import Optional


class ResponseHelper:
    """Helper for consistent Discord interaction responses."""

    @staticmethod
    async def defer(interaction: discord.Interaction, ephemeral: bool = True) -> None:
        """Defer interaction response."""
        await interaction.response.defer(ephemeral=ephemeral)

    @staticmethod
    async def send_error(interaction: discord.Interaction, message: str, ephemeral: bool = True) -> None:
        """Send error message."""
        try:
            await interaction.followup.send(message, ephemeral=ephemeral)
        except:
            # Fallback if followup fails
            try:
                await interaction.response.send_message(message, ephemeral=ephemeral)
            except:
                pass  # Last resort - ignore if all methods fail

    @staticmethod
    async def send_success(interaction: discord.Interaction, message: str, ephemeral: bool = True) -> None:
        """Send success message."""
        try:
            await interaction.followup.send(message, ephemeral=ephemeral)
        except:
            try:
                await interaction.response.send_message(message, ephemeral=ephemeral)
            except:
                pass

    @staticmethod
    async def send_file(interaction: discord.Interaction, file: discord.File, filename: str, ephemeral: bool = True) -> None:
        """Send file attachment."""
        try:
            await interaction.followup.send(file=file, ephemeral=ephemeral)
        except:
            try:
                await interaction.response.send_message(file=file, ephemeral=ephemeral)
            except:
                pass


# Convenience functions
async def send_db_error(interaction: discord.Interaction, operation: str = "operation") -> None:
    """Send database error message."""
    await ResponseHelper.send_error(
        interaction,
        f"❌ Database not available for {operation}.",
        ephemeral=True
    )


async def send_generic_error(interaction: discord.Interaction, operation: str = "operation", error: Optional[Exception] = None) -> None:
    """Send generic error message."""
    error_msg = f"❌ Failed to {operation}"
    if error:
        error_msg += f": {str(error)}"
    await ResponseHelper.send_error(interaction, error_msg, ephemeral=True)