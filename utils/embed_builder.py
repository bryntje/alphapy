"""
Embed Builder Utilities

Centralized Discord embed creation following AGENTS.md styling guidelines.
Provides consistent embed formatting across all cogs with proper colors,
timestamps, and field formatting.
"""

from datetime import datetime
from discord import Embed, Color
from utils.timezone import BRUSSELS_TZ
from typing import Optional, List, Dict, Any
from version import __version__, CODENAME


class EmbedBuilder:
    """
    Builder class for creating consistent Discord embeds following AGENTS.md guidelines.
    """
    
    @staticmethod
    def info(
        title: str,
        description: str = "",
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None,
        include_version: bool = False
    ) -> Embed:
        """
        Standard info embed with consistent styling.
        
        Args:
            title: Embed title (emoji will be added if not present)
            description: Embed description
            fields: Optional list of field dictionaries with 'name', 'value', 'inline' keys
            footer: Optional footer text
            include_version: If True, adds version info to footer
            
        Returns:
            Embed: Formatted Discord embed
        """
        # Add emoji prefix if not present
        if title and not any(ord(char) > 127 for char in title[:2]):  # Check if first 2 chars are emoji
            title = f"📋 {title}"
        
        embed = Embed(
            title=title,
            description=description,
            color=Color.blue(),
            timestamp=datetime.now(BRUSSELS_TZ)
        )
        
        if fields:
            for field in fields:
                embed.add_field(**field)
        
        if footer or include_version:
            footer_text = footer or ""
            if include_version:
                version_text = f"v{__version__} — {CODENAME}"
                footer_text = f"{footer_text} | {version_text}" if footer_text else version_text
            embed.set_footer(text=footer_text)
        
        return embed
    
    @staticmethod
    def log(
        title: str,
        description: str,
        level: str = "info",
        guild_id: int = 0
    ) -> Embed:
        """
        Log embed with level-based colors.
        
        Args:
            title: Embed title
            description: Embed description
            level: Log level (info, success, warning, error)
            guild_id: Guild ID for footer (optional)
            
        Returns:
            Embed: Formatted Discord embed
        """
        color_map = {
            "info": Color.blue(),
            "success": Color.green(),
            "warning": Color.orange(),
            "error": Color.red(),
            "debug": Color.light_grey()
        }
        
        embed = Embed(
            title=title,
            description=description,
            color=color_map.get(level, Color.blue()),
            timestamp=datetime.now(BRUSSELS_TZ)
        )
        
        if guild_id:
            embed.set_footer(text=f"Guild: {guild_id}")
        
        return embed
    
    @staticmethod
    def warning(
        title: str,
        description: str = "",
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None
    ) -> Embed:
        """
        Warning embed with orange color.
        
        Args:
            title: Embed title
            description: Embed description
            fields: Optional list of field dictionaries
            footer: Optional footer text
            
        Returns:
            Embed: Formatted Discord embed
        """
        embed = Embed(
            title=title,
            description=description,
            color=Color.orange(),
            timestamp=datetime.now(BRUSSELS_TZ)
        )
        
        if fields:
            for field in fields:
                embed.add_field(**field)
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def success(
        title: str,
        description: str = "",
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None
    ) -> Embed:
        """
        Success embed with green color.
        
        Args:
            title: Embed title
            description: Embed description
            fields: Optional list of field dictionaries
            footer: Optional footer text
            
        Returns:
            Embed: Formatted Discord embed
        """
        embed = Embed(
            title=title,
            description=description,
            color=Color.green(),
            timestamp=datetime.now(BRUSSELS_TZ)
        )
        
        if fields:
            for field in fields:
                embed.add_field(**field)
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def error(
        title: str,
        description: str = "",
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None
    ) -> Embed:
        """
        Error embed with red color.
        
        Args:
            title: Embed title
            description: Embed description
            fields: Optional list of field dictionaries
            footer: Optional footer text
            
        Returns:
            Embed: Formatted Discord embed
        """
        embed = Embed(
            title=title,
            description=description,
            color=Color.red(),
            timestamp=datetime.now(BRUSSELS_TZ)
        )
        
        if fields:
            for field in fields:
                embed.add_field(**field)
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def status(
        title: str,
        description: str = "",
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None
    ) -> Embed:
        """
        Status embed with teal color (for system status).
        
        Args:
            title: Embed title
            description: Embed description
            fields: Optional list of field dictionaries
            footer: Optional footer text
            
        Returns:
            Embed: Formatted Discord embed
        """
        embed = Embed(
            title=title,
            description=description,
            color=Color.teal(),
            timestamp=datetime.now(BRUSSELS_TZ)
        )
        
        if fields:
            for field in fields:
                embed.add_field(**field)
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    @staticmethod
    def truncate_field_value(value: str, max_length: int = 1024) -> str:
        """
        Truncate field value to Discord's max length (1024 characters).
        
        Args:
            value: Field value to truncate
            max_length: Maximum length (default 1024 for Discord)
            
        Returns:
            str: Truncated value with ellipsis if needed
        """
        if len(value) <= max_length:
            return value
        return value[:max_length - 3] + "..."
