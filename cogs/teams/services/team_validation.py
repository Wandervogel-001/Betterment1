import discord
import re
from typing import Set, Tuple, List, Dict

from ..models.team import TeamConfig, InvalidTeamError, TeamMember
from ..utils.team_utils import fetch_member_safely, get_member_role_title

class TeamValidator:
    """Handles validation logic for teams and members."""

    def __init__(self, db):
        self.db = db
        self.config = TeamConfig()

    def validate_team_number(self, team_number: int):
        if not 1 <= team_number <= self.config.max_team_number:
            raise InvalidTeamError(f"Team number must be between 1 and {self.config.max_team_number}.")

    def format_and_validate_channel_name(self, channel_name: str) -> str:
        formatted = re.sub(r"[^a-z0-9\-]", "", channel_name.lower().replace(' ', '-'))
        if not 3 <= len(formatted) <= self.config.max_team_name_length:
            raise InvalidTeamError(f"Channel name must be 3-{self.config.max_team_name_length} alphanumeric characters or hyphens.")
        return formatted

    def parse_member_mentions(self, member_mentions: str) -> Set[str]:
        mention_ids = set(re.findall(r"<@!?(\d+)>", member_mentions))
        if not mention_ids:
            raise InvalidTeamError("You must mention at least one member.")
        return mention_ids

    async def filter_and_validate_members(self, guild: discord.Guild, member_ids: Set[str], current_team_size: int, allow_unregistered: bool, target_team_name: str = None) -> Tuple[Set[str], List[str], Dict[str, str]]:
        """Validates and filters a set of member IDs, returning valid IDs and conflicts."""
        if current_team_size + len(member_ids) > self.config.max_team_size:
            raise InvalidTeamError(f"Adding these members would exceed the max team size of {self.config.max_team_size}.")

        valid_ids, invalid_members, conflicted_members = set(), [], {}

        for user_id in member_ids:
            member = await fetch_member_safely(guild, user_id)
            if not member or member.bot or (get_member_role_title(member) == "Unregistered" and not allow_unregistered):
                invalid_members.append(user_id)
                continue

            # Check if member is already in another team
            other_team_doc = await self.db.find_team_by_member(guild.id, user_id)
            if other_team_doc:
                other_team_name = other_team_doc.get("team_role")
                # If adding to a team, check if it's the *same* team
                if not target_team_name or other_team_name != target_team_name:
                    conflicted_members[user_id] = f"already in {other_team_name}"
                    continue

            valid_ids.add(user_id)

        return valid_ids, invalid_members, conflicted_members

    async def get_valid_team_members(self, guild: discord.Guild, members: Dict[str, TeamMember]) -> Tuple[List[Tuple[discord.Member, str]], bool]:
        """
        Validates that team members are still in the guild and returns their discord.Member objects.
        Also checks if there is at least one leader. This is used by the MarathonService.
        """
        valid_members, has_leader = [], False
        for user_id in members.keys():
            member = await fetch_member_safely(guild, user_id)
            if member:
                role_title = get_member_role_title(member)
                if role_title == "Unregistered":
                    continue
                if role_title == "Team Leader":
                    has_leader = True
                valid_members.append((member, role_title))
        return valid_members, has_leader
