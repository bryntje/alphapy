"""
Embed helpers for consistent embed creation across the bot.
"""
import discord
from .embed_builder import EmbedBuilder
from typing import Optional


def create_success_embed(title: str, description: Optional[str] = None) -> discord.Embed:
    """Create a success embed with consistent styling."""
    return EmbedBuilder.success(title=title, description=description)


def create_error_embed(title: str = "Error", description: Optional[str] = None) -> discord.Embed:
    """Create an error embed with consistent styling."""
    return EmbedBuilder.error(title=title, description=description)


def create_warning_embed(title: str, description: Optional[str] = None) -> discord.Embed:
    """Create a warning embed with consistent styling."""
    return EmbedBuilder.warning(title=title, description=description)


def create_info_embed(title: str, description: Optional[str] = None) -> discord.Embed:
    """Create an info embed with consistent styling."""
    return EmbedBuilder.info(title=title, description=description)


def create_status_embed(title: str, description: Optional[str] = None) -> discord.Embed:
    """Create a status embed with consistent styling."""
    return EmbedBuilder.status(title=title, description=description)


# Convenience functions for common operations
def create_db_unavailable_embed(operation: str = "operation") -> discord.Embed:
    """Create embed for database unavailable errors."""
    return create_error_embed(
        title="Database Unavailable",
        description=f"❌ Database is not available for {operation}. Please try again later."
    )


def create_permission_denied_embed(feature: str = "this feature") -> discord.Embed:
    """Create embed for permission denied errors."""
    return create_error_embed(
        title="Permission Denied",
        description=f"❌ You don't have permission to access {feature}."
    )


def create_operation_success_embed(operation: str, details: Optional[str] = None) -> discord.Embed:
    """Create embed for successful operations."""
    description = f"✅ {operation} completed successfully"
    if details:
        description += f"\n{details}"
    return create_success_embed(
        title="Success",
        description=description
    )