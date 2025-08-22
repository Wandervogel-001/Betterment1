from discord import Member, User, Interaction
from typing import Union
from functools import wraps
import logging

from .models.team import TeamConfig

logger = logging.getLogger(__name__)

class PermissionManager:
    """Handles all permission-related functionality for the bot."""

    def __init__(self):
        self.config = TeamConfig()

    def is_moderator(self, user: Union[Member, User]) -> bool:
        """
        Centralized method to check if a user has moderator-level permissions.
        Checks for server ownership, administrator privilege, or specified moderator roles.
        """
        if not isinstance(user, Member):  # User object for checks outside a guild context
            return False
        if user.guild.owner == user:
            return True
        if user.guild_permissions.administrator:
            return True
        if any(role.name in self.config.moderator_roles for role in user.roles):
            return True
        return False

def moderator_required(func):
    """
    Decorator to ensure the user has moderator privileges.
    It finds the central PermissionManager instance from the bot's TeamsCog.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        interaction: Interaction = None
        for arg in args:
            if isinstance(arg, Interaction):
                interaction = arg
                break

        if not interaction:
            # Fallback for cases where interaction might be a keyword argument
            interaction = kwargs.get("interaction")

        if not interaction:
            logger.error("Decorator 'moderator_required' could not find an Interaction object.")
            # Cannot send a response without an interaction object.
            return

        # Access the cog via the bot client, which is accessible from the interaction.
        # 'TeamsCog' is the name of the class registered with the bot.
        teams_cog = interaction.client.get_cog('TeamsCog')

        if not teams_cog or not hasattr(teams_cog, 'permission_manager'):
            logger.error("Permission manager not found in TeamsCog. Ensure the cog is loaded.")
            return await interaction.response.send_message("❌ Permission system error.", ephemeral=True)

        # Use the centralized permission manager instance from the cog.
        if not teams_cog.permission_manager.is_moderator(interaction.user):
            return await interaction.response.send_message("❌ You need moderator privileges.", ephemeral=True)

        return await func(*args, **kwargs)
    return wrapper
