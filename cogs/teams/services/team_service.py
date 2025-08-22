import logging
import re
from typing import List, Dict, Tuple, Optional

import discord
from ..models.team import Team, TeamError, TeamNotFoundError, InvalidTeamError, TeamMember, TeamConfig
from .team_validation import TeamValidator
from .team_member_service import TeamMemberService
from ..utils import team_utils

logger = logging.getLogger(__name__)

class TeamService:
    """Handles high-level team CRUD and state management operations."""

    def __init__(self, db, validator: TeamValidator, member_service: TeamMemberService):
        self.config = TeamConfig()
        self.db = db
        self.validator = validator
        self.member_service = member_service

    async def is_marathon_active(self, guild_id: int) -> bool:
        return await self.db.get_marathon_state(guild_id)

    async def get_marathon_state_info(self, guild_id: int) -> Dict:
        """
        Retrieves the full marathon state document, providing a default if none exists.
        """
        state_doc = await self.db.get_marathon_state_document(guild_id)
        if state_doc:
            return state_doc
        # Return a default structure if no state is found in the database
        return {"is_active": False, "last_changed": None}

    async def create_team(self, guild: discord.Guild, team_number: int, channel_name: str, member_mentions: str) -> Tuple[Team, List[str]]:
        """
        Creates a new team and returns the team object and a list of invalid member IDs that were skipped.
        """
        self.validator.validate_team_number(team_number)
        team_role = f"Team {team_number}"

        if await self.db.get_team_by_name(guild.id, team_role):
            raise InvalidTeamError(f"Team '{team_role}' already exists.")

        formatted_channel = self.validator.format_and_validate_channel_name(channel_name)
        member_ids = self.validator.parse_member_mentions(member_mentions)
        is_marathon = await self.is_marathon_active(guild.id)

        # We need to know which members were invalid to report back to the user
        valid_ids, invalid_ids, _ = await self.validator.filter_and_validate_members(guild, member_ids, 0, not is_marathon)

        if not valid_ids:
            # If no members are valid, raise a more descriptive error
            error_message = "No valid members were provided for the new team."
            if is_marathon and invalid_ids:
                 error_message = "No valid members were provided. During a marathon, all members must have the 'Team Member' or 'Team Leader' role."
            raise InvalidTeamError(error_message)

        members = await self.member_service.create_member_objects(guild, valid_ids, not is_marathon)
        team = Team(guild_id=guild.id, team_role=team_role, channel_name=formatted_channel, members=members, _team_number=team_number)

        await self.db.insert_team(team.to_dict())

        if is_marathon:
            await team_utils.provision_team_resources(guild, team)

        logger.info(f"Created team '{team_role}' with {len(members)} members. Skipped {len(invalid_ids)} invalid members.")

        # Return both the created team and the list of IDs that were skipped
        return team, invalid_ids

    async def get_team(self, guild_id: int, team_name: str) -> Team:
        team_data = await self.db.get_team_by_name(guild_id, team_name)
        if not team_data:
            raise TeamNotFoundError(f"Team '{team_name}' not found.")
        return team_utils.build_team_from_data(guild_id, team_data)

    async def get_all_teams(self, guild_id: int) -> List[Team]:
        teams_data = await self.db.get_teams(guild_id)
        teams = [team_utils.build_team_from_data(guild_id, data) for data in teams_data]
        return sorted(teams, key=lambda t: t.team_number)

    async def delete_team_and_resources(self, guild: discord.Guild, team_name: str):
        """Deletes a team from the DB and removes its Discord role and channel."""
        team = await self.get_team(guild.id, team_name)
        deleted = await self.db.delete_team(guild.id, team_name)
        if deleted and deleted.deleted_count > 0:
            await team_utils.cleanup_team_discord_resources(guild, team)
            return True
        else:
            raise TeamError(f"Failed to delete team '{team_name}' from the database.")


    async def update_team_channel_name(self, guild_id: int, team_name: str, new_channel_name: str) -> bool:
        """Updates the channel name for a specific team in the database."""
        formatted_name = self.validator.format_and_validate_channel_name(new_channel_name)
        result = await self.db.update_team_channel_name(guild_id, team_name, formatted_name)
        if result and result.modified_count > 0:
            logger.info(f"Successfully updated channel name for team '{team_name}' to '{formatted_name}'.")
            return True
        logger.warning(f"Attempted to update channel name for team '{team_name}' but no changes were made.")
        return False

    async def fetch_server_teams(self, guild: discord.Guild) -> dict:
        """Scans the server for existing team roles and registers them in the database."""
        registered_count = 0
        skipped_count = 0
        skipped_details = []

        existing_teams = {t.team_role for t in await self.get_all_teams(guild.id)}

        potential_team_roles = [
            r for r in guild.roles
            if (r.name.startswith("Team ") and
                not r.is_default() and
                r.name not in self.config.excluded_team_roles)
        ]

        for role in potential_team_roles:
            if role.name in existing_teams:
                skipped_count += 1
                skipped_details.append(f"`{role.name}` (already registered)")
                continue

            try:
                match = re.search(r"Team (\d+)", role.name)
                if not match:
                    skipped_details.append(f"`{role.name}` (invalid name format)")
                    continue
                team_number = int(match.group(1))
            except (ValueError, AttributeError):
                skipped_details.append(f"`{role.name}` (could not get team number)")
                continue

            found_channel = None
            for channel in guild.text_channels:
                overwrites = channel.overwrites_for(role)
                default_overwrites = channel.overwrites_for(guild.default_role)
                if overwrites.view_channel is True and default_overwrites.view_channel is False:
                    found_channel = channel
                    break

            if not found_channel:
                skipped_details.append(f"`{role.name}` (no private channel)")
                continue

            members_dict = {}
            for member in role.members:
                if not member.bot:
                    role_title = team_utils.get_member_role_title(member)
                    team_member = TeamMember(user_id=str(member.id), username=member.name, display_name=member.display_name, role_title=role_title)
                    members_dict[str(member.id)] = team_member

            if not members_dict:
                skipped_details.append(f"`{role.name}` (no valid members)")
                continue

            team_data = {
                "guild_id": guild.id,
                "team_number": team_number,
                "team_role": role.name,
                "channel_name": found_channel.name,
                "members": {uid: tm.to_dict() for uid, tm in members_dict.items()}
            }

            try:
                await self.db.insert_team(team_data)
                registered_count += 1
            except Exception as e:
                skipped_details.append(f"`{role.name}` (database error: {e})")

        return {"registered": registered_count, "skipped": skipped_count, "details": skipped_details}
