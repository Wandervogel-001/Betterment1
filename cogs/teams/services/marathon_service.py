import discord
import logging
from typing import Dict, List, Tuple
from ..models.team import Team, TeamMember

logger = logging.getLogger(__name__)

class MarathonService:
    """
    Handles the lifecycle of a marathon event by provisioning and deprovisioning
    Discord resources (roles and channels) for teams.
    """
    def __init__(self, db, team_manager):
        """
        Initializes the service with only the dependencies it actually needs.
        """
        self.db = db
        self.team_manager = team_manager

    async def start_marathon(self, guild: discord.Guild, teams: List[Team]) -> Dict:
        """
        Handles the logic for starting a marathon. It validates teams and creates
        dedicated roles and private channels for them.
        """
        # Check if marathon is already active
        is_active = await self.cog.db.get_marathon_state(guild.id)
        if is_active:
            return {"error": "Marathon is already active for this guild"}

        report = {"created_roles": [], "created_channels": [], "skipped_teams": []}

        for team in teams:
            # 1. Validate the team using the public method from TeamManager
            valid_members, has_leader = await self.cog.team_manager.validator.get_valid_team_members(guild, team.members)

            if not valid_members or not has_leader:
                report["skipped_teams"].append(f"{team.team_role} (No valid leader or members)")
                continue

            # 2. Provision resources using the helper method
            role, channel = await self._provision_team_resources(guild, team, valid_members)

            if role:
                report["created_roles"].append(role.name)
            if channel:
                report["created_channels"].append(channel.name)

        # Set marathon state to active if any teams were processed successfully
        if report["created_roles"] or report["created_channels"]:
            await self.cog.db.set_marathon_state(guild.id, True)
            report["marathon_state"] = "activated"

        return report

    async def end_marathon(self, guild: discord.Guild) -> Dict:
        """
        Handles the logic for ending a marathon. It removes all marathon-related
        roles from members and deletes the team channels.
        """
        # Check if marathon is active
        is_active = await self.cog.db.get_marathon_state(guild.id)
        if not is_active:
            return {"error": "No active marathon found for this guild"}

        report = {"removed_channels": [], "removed_roles": [], "processed_teams": []}
        teams = await self.cog.team_manager.get_all_teams(guild.id)

        team_leader_role = discord.utils.get(guild.roles, name="Team Leader")
        team_member_role = discord.utils.get(guild.roles, name="Team Member")

        for team in teams:
            # Deprovision resources using the new helper method
            removed_role, removed_channel = await self._deprovision_team_resources(
                guild, team, team_leader_role, team_member_role
            )

            report["processed_teams"].append(team.team_role)
            if removed_role:
                report["removed_roles"].append(removed_role.name)
            if removed_channel:
                report["removed_channels"].append(removed_channel.name)

        # Set marathon state to inactive
        await self.cog.db.set_marathon_state(guild.id, False)
        report["marathon_state"] = "deactivated"

        return report

    async def _provision_team_resources(
        self, guild: discord.Guild, team: Team, members: List[Tuple[discord.Member, str]]
    ) -> Tuple[discord.Role | None, discord.TextChannel | None]:
        """
        Creates a role and a private channel for a single team.
        Returns the created role and channel, or None if creation failed.
        """
        created_role, created_channel = None, None

        try:
            # Get or create the team-specific role
            role = discord.utils.get(guild.roles, name=team.team_role)
            if not role:
                role = await guild.create_role(name=team.team_role, reason=f"Marathon start for {team.team_role}")
                created_role = role

            # Assign the role to all valid members
            for member, _ in members:
                if role not in member.roles:
                    await member.add_roles(role, reason="Marathon team assignment")

            # Get or create the private text channel
            channel = discord.utils.get(guild.text_channels, name=team.channel_name.lower())
            if not channel:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                }
                channel = await guild.create_text_channel(
                    team.channel_name, overwrites=overwrites, reason=f"Marathon channel for {team.team_role}"
                )
                created_channel = channel

            return created_role, created_channel

        except discord.Forbidden:
            logger.error(f"Missing permissions to create resources for {team.team_role}. Check role and channel permissions.")
            return None, None
        except discord.HTTPException as e:
            logger.error(f"An HTTP error occurred while provisioning for {team.team_role}: {e}")
            return None, None

    async def _deprovision_team_resources(
        self, guild: discord.Guild, team: Team,
        team_leader_role: discord.Role | None, team_member_role: discord.Role | None
    ) -> Tuple[discord.Role | None, discord.TextChannel | None]:
        """
        Removes roles from members and deletes the team's channel and role.
        Returns the deleted role and channel, or None if they didn't exist or failed to delete.
        """
        deleted_role, deleted_channel = None, None
        team_role = discord.utils.get(guild.roles, name=team.team_role)

        if not team_role:
            logger.warning(f"Could not find role '{team.team_role}' to deprovision.")
            return None, None

        # Remove all relevant roles from every member of the team role
        for member in list(team_role.members):
            try:
                roles_to_remove = [r for r in [team_role, team_leader_role, team_member_role] if r and r in member.roles]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason="Marathon end")
            except discord.Forbidden:
                logger.warning(f"Missing permissions to remove roles from {member.display_name}.")
            except discord.HTTPException as e:
                logger.error(f"Failed to remove roles from {member.display_name}: {e}")

        # Delete the team channel
        channel = discord.utils.get(guild.text_channels, name=team.channel_name.lower())
        if channel:
            try:
                await channel.delete(reason="Marathon end")
                deleted_channel = channel
            except discord.Forbidden:
                logger.warning(f"Missing permissions to delete channel {channel.name}.")
            except discord.HTTPException as e:
                logger.error(f"Failed to delete channel {channel.name}: {e}")

        # Delete the team role itself
        try:
            await team_role.delete(reason="Marathon end")
            deleted_role = team_role
        except discord.Forbidden:
            logger.warning(f"Missing permissions to delete role {team_role.name}.")
        except discord.HTTPException as e:
            logger.error(f"Failed to delete role {team_role.name}: {e}")

        return deleted_role, deleted_channel
