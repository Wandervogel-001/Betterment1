import logging
import discord
from typing import Dict, List

from ..models.team import TeamConfig, TeamError
from ..services.team_service import TeamService
from ..services.team_member_service import TeamMemberService
from ..services.team_validation import TeamValidator
from ..services.ai_handler import AIHandler
from ..services.scoring_engine import TeamScoringEngine
from ..services.team_formation_service import TeamFormationService

logger = logging.getLogger(__name__)

class TeamManager:
    """
    Main entry point for team management. Initializes and orchestrates
    specialized services for validation, team operations, and member management.

    """

    def __init__(self, db):
        self.db = db
        self.config = TeamConfig()

        # Initialize specialized services
        self.validator = TeamValidator(self.db)
        self.member_service = TeamMemberService(self.db, self.validator)
        self.team_service = TeamService(self.db, self.validator, self.member_service)

        # Initialize other high-level services
        self.scorer = TeamScoringEngine(AIHandler())
        self.formation_service = TeamFormationService(self.scorer, self.db, self)

    # ========== PUBLIC METHODS ==========

    async def create_team(self, *args, **kwargs):
        """Delegates team creation to TeamService."""
        return await self.team_service.create_team(*args, **kwargs)

    async def get_team(self, *args, **kwargs):
        """Delegates team retrieval to TeamService."""
        return await self.team_service.get_team(*args, **kwargs)

    async def get_all_teams(self, *args, **kwargs):
        """Delegates fetching all teams to TeamService."""
        return await self.team_service.get_all_teams(*args, **kwargs)

    async def delete_team_and_resources(self, *args, **kwargs):
        """Delegates team and resource deletion to TeamService."""
        return await self.team_service.delete_team_and_resources(*args, **kwargs)

    async def add_members_to_team(self, guild, team_name, member_mentions):
        """Orchestrates adding members by fetching team and marathon state first."""
        team = await self.get_team(guild.id, team_name)
        is_marathon = await self.is_marathon_active(guild.id)
        return await self.member_service.add_members_to_team(guild, team, member_mentions, is_marathon)

    async def remove_members_from_team(self, guild, team_name, member_ids):
        """Orchestrates removing members by fetching the team first."""
        team = await self.get_team(guild.id, team_name)
        return await self.member_service.remove_members_from_team(guild.id, team, member_ids)

    async def is_marathon_active(self, *args, **kwargs):
        """Delegates marathon state check to TeamService."""
        return await self.team_service.is_marathon_active(*args, **kwargs)

    async def get_marathon_state_info(self, *args, **kwargs):
        """Delegates marathon state info retrieval to TeamService."""
        return await self.team_service.get_marathon_state_info(*args, **kwargs)

    def _get_member_role_title(self, member: discord.Member) -> str:
        """Delegates getting the member's role title to the TeamService."""
        return self.team_service._get_member_role_title(member)

    # ========== ORCHESTRATION METHODS ==========

    async def reflect_teams(self, guild: discord.Guild) -> Dict[str, List]:
        """
        Analyzes and reports on the consistency of team data by orchestrating
        calls to the team and member services.
        """
        teams = await self.get_all_teams(guild.id)
        empty_teams, no_leader_teams = [], []

        for team in teams:
            if not team.members:
                empty_teams.append(team.team_role) #
                continue

            # This logic could be further delegated if needed
            _, has_leader = await self.member_service._update_team_members_data(guild, team.members) #
            if not has_leader:
                no_leader_teams.append(team.team_role) #

        # Get all members currently in a team to pass to the sync function
        all_team_member_ids = {uid for team in teams for uid in team.members.keys()} #

        # Perform synchronization of unassigned members and get the report
        sync_report = await self.member_service.sync_unregistered_members(guild, all_team_member_ids) #

        return {
            "empty_teams": empty_teams,
            "no_leader_teams": no_leader_teams,
            "unassigned_members": sync_report["unassigned_list"],
            "unassigned_leader_count": sync_report["leader_count"],
            "unassigned_member_count": sync_report["member_count"],
        }
