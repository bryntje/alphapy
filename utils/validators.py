"""
Validation Utilities

Centralized permission checks and ownership validation to reduce duplicate
code across cogs. Provides type-safe validators with consistent error messages.
"""

from typing import Optional, Tuple
from discord import Interaction
from discord import app_commands
from discord.app_commands import CheckFailure
from utils.checks_interaction import is_owner_or_admin_interaction
import config


async def validate_admin(
    interaction: Interaction,
    raise_on_fail: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Type-safe admin validation with consistent error messages.
    
    Args:
        interaction: The Discord interaction to validate
        raise_on_fail: If True, raises CheckFailure on failure instead of returning False
        
    Returns:
        Tuple[bool, Optional[str]]: (is_admin, error_message)
        
    Raises:
        CheckFailure: If raise_on_fail is True and user is not admin
    """
    is_admin = await is_owner_or_admin_interaction(interaction)
    
    if not is_admin:
        error_msg = "❌ You don't have permission to use this command. Administrator access required."
        if raise_on_fail:
            raise CheckFailure(error_msg)
        return False, error_msg
    
    return True, None


async def validate_ownership(
    user_id: int,
    resource_user_id: int,
    resource_type: str = "resource"
) -> Tuple[bool, Optional[str]]:
    """
    Validate resource ownership.
    
    Args:
        user_id: The ID of the user attempting to access the resource
        resource_user_id: The ID of the user who owns the resource
        resource_type: Type of resource for error message (e.g., "reminder", "ticket")
        
    Returns:
        Tuple[bool, Optional[str]]: (is_owner, error_message)
    """
    if user_id != resource_user_id:
        return False, f"❌ You can only access your own {resource_type}."
    return True, None


async def validate_owner_or_admin(
    interaction: Interaction,
    resource_user_id: int,
    resource_type: str = "resource",
    raise_on_fail: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Validate that user is either the owner of the resource or an admin.
    
    Args:
        interaction: The Discord interaction to validate
        resource_user_id: The ID of the user who owns the resource
        resource_type: Type of resource for error message
        raise_on_fail: If True, raises CheckFailure on failure
        
    Returns:
        Tuple[bool, Optional[str]]: (has_access, error_message)
        
    Raises:
        CheckFailure: If raise_on_fail is True and user has no access
    """
    # Check if user is admin first
    is_admin, admin_error = await validate_admin(interaction, raise_on_fail=False)
    if is_admin:
        return True, None
    
    # Check if user owns the resource
    is_owner, owner_error = await validate_ownership(
        interaction.user.id,
        resource_user_id,
        resource_type
    )
    
    if is_owner:
        return True, None
    
    # User is neither admin nor owner
    error_msg = f"❌ You don't have permission to access this {resource_type}. You must be the owner or an administrator."
    if raise_on_fail:
        raise CheckFailure(error_msg)
    return False, error_msg


def requires_admin():
    """
    Decorator factory for app_commands that require admin access.
    
    Usage:
        @app_commands.command(name="admin_command")
        @requires_admin()
        async def admin_command(interaction: Interaction):
            ...
    """
    async def predicate(interaction: Interaction) -> bool:
        is_admin, _ = await validate_admin(interaction, raise_on_fail=True)
        return is_admin
    return predicate


def requires_owner():
    """
    Decorator factory for app_commands that require owner access only (not admin).
    
    Usage:
        @app_commands.command(name="owner_command")
        @requires_owner()
        async def owner_command(interaction: Interaction):
            ...
    """
    async def predicate(interaction: Interaction) -> bool:
        try:
            app_info = await interaction.client.application_info()
            if interaction.user.id == app_info.owner.id:
                return True
        except Exception:
            pass
        owner_ids = getattr(interaction.client, "owner_ids", None) or []
        config_owner_ids = getattr(config, "OWNER_IDS", [])
        if interaction.user.id in owner_ids or interaction.user.id in config_owner_ids:
            return True
        raise CheckFailure("This command is restricted to bot owners only.")
    return app_commands.check(predicate)
