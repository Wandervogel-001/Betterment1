import discord
from typing import Dict, List, Set, Tuple, Optional
from ..models.team import Team, TeamMember
from ..utils.team_utils import fetch_member_safely, get_member_role_title
from .team_validation import TeamValidator

class TeamMemberService:
    """Manages all operations related to team members."""

    def __init__(self, db, validator: TeamValidator):
        self.db = db
        self.validator = validator

    async def create_member_objects(self, guild: discord.Guild, member_ids: Set[str], allow_unregistered: bool) -> Dict[str, TeamMember]:
        """Creates a dictionary of TeamMember objects from a set of user IDs."""
        members = {}
        for uid in member_ids:
            member = await fetch_member_safely(guild, uid)
            if not member or member.bot:
                continue

            role_title = get_member_role_title(member)
            if role_title == "Unregistered" and not allow_unregistered:
                continue

            # Default role for unregistered members when allowed
            if role_title == "Unregistered":
                role_title = "Team Member"

            members[uid] = TeamMember(user_id=uid, username=member.name, display_name=member.display_name, role_title=role_title)
        return members

    async def add_members_to_team(self, guild: discord.Guild, team, member_mentions: str, is_marathon_active: bool) -> Tuple[list, list, list, list]:
        """Adds members to an existing team."""
        member_ids = self.validator.parse_member_mentions(member_mentions)

        valid_ids, invalid_list, conflict_dict = await self.validator.filter_and_validate_members(
            guild, member_ids, len(team.members), not is_marathon_active, team.team_role
        )

        new_members = []
        if valid_ids:
            new_member_objects = await self.create_member_objects(guild, valid_ids, not is_marathon_active)
            team.members.update(new_member_objects)
            await self.db.update_team_members(guild.id, team.team_role, {uid: vars(m) for uid, m in team.members.items()})
            new_members = list(new_member_objects.values())

        existing_members = conflict_dict.get("existing", [])
        in_other_teams = conflict_dict.get("in_other_teams", [])

        return new_members, existing_members, invalid_list, in_other_teams


    async def _update_team_members_data(self, guild: discord.Guild, members: Dict[str, TeamMember]) -> Tuple[Dict[str, TeamMember], bool]:
        """Updates data for members within a specific team and checks for a leader."""
        updated_members = {}
        has_leader = False
        for user_id, member_obj in members.items():
            member = await fetch_member_safely(guild, user_id)
            if not member:
                continue

            new_role_title = get_member_role_title(member)
            member_obj.username = member.name
            member_obj.display_name = member.display_name
            member_obj.role_title = new_role_title
            updated_members[user_id] = member_obj

            if new_role_title == "Team Leader":
                has_leader = True

        return updated_members, has_leader

    async def remove_members_from_team(self, guild_id: int, team: Team, member_ids: Set[str]) -> Tuple[List[TeamMember], List[str]]:
        """Removes members from a team, updates the database, and reports invalid IDs."""
        removed_members = []
        invalid_members = []

        for uid in member_ids:
            if uid in team.members:
                removed_members.append(team.members.pop(uid))
            else:
                invalid_members.append(uid)

        if removed_members:
            await self.db.update_team_members(guild_id, team.team_role, {uid: vars(m) for uid, m in team.members.items()})

        return removed_members, invalid_members

    async def sync_unregistered_members(self, guild: discord.Guild, all_team_member_ids: set) -> dict:
        """Synchronizes the unregistered members list with Discord roles and returns a report."""
        # 1. Get all tracked unregistered member IDs from the DB
        unregistered_doc = await self.db.get_unregistered_document(guild.id) or {} #
        unregistered_leaders = unregistered_doc.get("leaders", {})
        unregistered_members = unregistered_doc.get("members", {})
        all_unregistered_ids = set(unregistered_leaders.keys()) | set(unregistered_members.keys()) #

        # 2. Sync existing DB entries
        for user_id in all_unregistered_ids:
            member = await fetch_member_safely(guild, user_id)
            # Remove if member left or no longer has a team role
            if not member or get_member_role_title(member) == "Unregistered": #
                await self.db.remove_unregistered_member(guild.id, user_id) #

        # 3. Find and add new members with team roles but no team
        team_leader_role = discord.utils.get(guild.roles, name="Team Leader")
        team_member_role = discord.utils.get(guild.roles, name="Team Member")

        for member in guild.members:
            if member.bot: continue

            member_id = str(member.id)
            has_team_role = (team_leader_role in member.roles) or (team_member_role in member.roles) #

            if has_team_role and member_id not in all_team_member_ids and member_id not in all_team_member_ids:
                role_title = get_member_role_title(member)
                role_type = "leaders" if role_title == "Team Leader" else "members"
                member_data = {"username": member.name, "display_name": member.display_name, "role_title": role_title, "profile_data": {}}
                await self.db.save_unregistered_member(guild.id, member_id, member_data, role_type) #

        # 4. Generate the final report from the now-synced database
        final_doc = await self.db.get_unregistered_document(guild.id) or {} #
        final_leaders = final_doc.get("leaders", {})
        final_members = final_doc.get("members", {})

        unassigned_list = [
            f"{i+1:<2} • {data['display_name']:<15} • {data['role_title']}"
            for i, data in enumerate(list(final_leaders.values()) + list(final_members.values()))
        ]

        return {"unassigned_list": unassigned_list, "leader_count": len(final_leaders), "member_count": len(final_members)}

    async def get_unassigned_member_profile(self, guild_id: int, user_id: str) -> Optional[Dict]:
        """
        Retrieves the profile data for a specific unassigned member.

        Args:
            guild_id (int): The Discord guild ID
            user_id (str): The user ID to look up

        Returns:
            Optional[Dict]: The member's profile data, or None if not found
        """
        unregistered_doc = await self.db.get_unregistered_document(guild_id)
        if not unregistered_doc:
            return None

        # Check both leaders and members collections
        leaders = unregistered_doc.get("leaders", {})
        members = unregistered_doc.get("members", {})

        if user_id in leaders:
            return leaders[user_id]
        elif user_id in members:
            return members[user_id]

        return None
