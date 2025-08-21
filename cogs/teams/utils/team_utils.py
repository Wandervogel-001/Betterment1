import discord
import logging
from typing import Dict, Optional

from ..models.team import Team, TeamMember, TeamError

logger = logging.getLogger(__name__)

async def fetch_member_safely(guild: discord.Guild, user_id: str) -> Optional[discord.Member]:
    """Safely fetches a member from the guild by ID, returning None if not found."""
    try:
        # Prefer cache, then fetch
        return guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))
    except (ValueError, discord.NotFound, discord.HTTPException) as e:
        logger.warning(f"Could not fetch member {user_id}: {e}")
        return None

def get_member_role_title(member: discord.Member) -> str:
    """Determines a member's role title based on their Discord roles."""
    roles = {role.name for role in member.roles}
    if "Team Leader" in roles:
        return "Team Leader"
    if "Team Member" in roles:
        return "Team Member"
    return "Unregistered"

def build_team_from_data(guild_id: int, team_data: Dict) -> Team:
    """Builds a Team object from a database document."""
    members = {uid: TeamMember(**data) for uid, data in team_data.get("members", {}).items()}
    return Team(
        guild_id=guild_id,
        team_role=team_data["team_role"],
        channel_name=team_data["channel_name"],
        members=members,
        _team_number=team_data.get("team_number")
    )

async def cleanup_team_discord_resources(guild: discord.Guild, team: Team):
    """Cleans up Discord roles and channels for a deleted team."""
    # Remove team role
    role = discord.utils.get(guild.roles, name=team.team_role)
    if role:
        try:
            await role.delete(reason=f"Team {team.team_role} deleted")
            logger.info(f"Deleted Discord role: {team.team_role}")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Failed to delete role '{team.team_role}': {e}")

    # Remove team channel
    channel = discord.utils.get(guild.text_channels, name=team.channel_name)
    if channel:
        try:
            await channel.delete(reason=f"Team {team.team_role} deleted")
            logger.info(f"Deleted Discord channel: #{team.channel_name}")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Failed to delete channel '#{team.channel_name}': {e}")

async def provision_team_resources(guild: discord.Guild, team: Team):
    """Provisions Discord role and channel for a team."""
    try:
        role = discord.utils.get(guild.roles, name=team.team_role) or await guild.create_role(name=team.team_role, reason=f"Provisioning for {team.team_role}")

        for user_id in team.members:
            member = await fetch_member_safely(guild, user_id)
            if member and role not in member.roles:
                await member.add_roles(role, reason="Team assignment")

        channel = discord.utils.get(guild.text_channels, name=team.channel_name.lower())
        if not channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                role: discord.PermissionOverwrite(view_channel=True)
            }
            await guild.create_text_channel(team.channel_name, overwrites=overwrites)
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.error(f"Failed to provision resources for {team.team_role}: {e}")
        raise TeamError(f"Failed to create Discord resources for {team.team_role}.")

async def provision_roles_for_new_members(guild: discord.Guild, team_name: str, new_members: list[TeamMember]):
    """Assigns the team role to newly added members."""
    role = discord.utils.get(guild.roles, name=team_name)
    if not role:
        logger.warning(f"Team role '{team_name}' not found when adding new members.")
        return

    for team_member in new_members:
        member = await fetch_member_safely(guild, team_member.user_id)
        if member and role not in member.roles:
            try:
                await member.add_roles(role, reason=f"Added to {team_name}")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"Failed to assign role to {member.display_name}: {e}")
