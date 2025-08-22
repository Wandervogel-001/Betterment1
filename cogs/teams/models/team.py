from dataclasses import dataclass, field
from typing import Set, List, Dict, Optional
import re
from config import (
  COMMUNICATION_CHANNEL_ID, MODERATOR_ROLES, EXCLUDED_TEAM_ROLES, MAX_TEAM_SIZE, MAX_LEADERS_PER_TEAM
)

@dataclass
class TeamConfig:
    """Configuration for team management system."""
    communication_channel_id: int = COMMUNICATION_CHANNEL_ID
    moderator_roles: Set[str] = field(default_factory=lambda: set(MODERATOR_ROLES))
    excluded_team_roles: Set[str] = field(default_factory=lambda: set(EXCLUDED_TEAM_ROLES))
    max_team_number: int = 100
    max_team_size: int = MAX_TEAM_SIZE
    max_leaders_per_team = MAX_LEADERS_PER_TEAM
    min_profile_length: int = 20
    max_team_name_length: int = 50
    team_name_pattern: str = r"^Team \d+$"  # e.g. "Team 1", "Team 2"

    def validate(self):
        """Validate configuration values."""
        if not self.communication_channel_id:
            raise ValueError("Communication channel ID must be set")
        if not self.moderator_roles:
            raise ValueError("At least one moderator role must be specified")

@dataclass
class TeamMember:
    """Represents a member of a team."""
    user_id: str
    username: str
    display_name: str
    role_title: str = "Unregistered"  # "Team Leader", "Team Member", or "Unregistered"
    profile_data: Dict = field(default_factory=dict)

    def is_leader(self) -> bool:
        return self.role_title == "Team Leader"

    def is_member(self) -> bool:
        return self.role_title in ("Team Leader", "Team Member")

    def to_dict(self) -> Dict:
        """Returns a dictionary representation of the TeamMember object."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "role_title": self.role_title,
            "profile_data": self.profile_data,
        }

@dataclass
class Team:
    """Represents a team with members and channel."""
    guild_id: int
    team_role: str  # e.g. "Team 1"
    channel_name: str
    members: Dict[str, TeamMember]  # user_id -> TeamMember
    _team_number: Optional[int] = None

    @property
    def team_number(self) -> int:
        """Extract the numeric part from team_role (e.g. "Team 1" -> 1)."""
        if self._team_number is not None:
            return self._team_number
        match = re.search(r"\d+", self.team_role)
        return int(match.group()) if match else 0

    @team_number.setter
    def team_number(self, value: Optional[int]):
        self._team_number = value

    def get_leaders(self) -> List[TeamMember]:
        """Get all team leaders."""
        return [m for m in self.members.values() if m.is_leader()]

    def has_leader(self) -> bool:
        """Check if team has at least one leader."""
        return any(m.is_leader() for m in self.members.values())

    def is_valid(self) -> bool:
        """Check if team has required structure."""
        return (
            bool(self.team_role) and
            bool(self.channel_name) and
            re.match(TeamConfig().team_name_pattern, self.team_role)
        )

    def get_leader_count(self) -> int:
        """Counts the number of leaders in the team."""
        return sum(1 for member in self.members.values() if member.is_leader())

    def to_dict(self) -> Dict:
        """Returns a dictionary representation of the Team object."""
        return {
            "guild_id": self.guild_id,
            "team_role": self.team_role,
            "channel_name": self.channel_name,
            "members": {uid: member.to_dict() for uid, member in self.members.items()},
            "_team_number": self._team_number,
        }

class TeamError(Exception):
    """Base exception for team-related errors."""
    pass

class InvalidTeamError(TeamError):
    """Raised when team data is invalid."""
    pass

class TeamNotFoundError(TeamError):
    """Raised when a team cannot be found."""
    pass

class TeamMemberError(TeamError):
    """Raised when member operations fail."""
    pass
