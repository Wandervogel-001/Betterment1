import logging
from typing import Optional, Dict, List, Any
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from config import DB_NAME, TEAMS_COLLECTION, TEAM_PANELS_COLLECTION, UNREGISTERED_MEMBERS_COLLECTION, MARATHON_STATE_COLLECTION

logger = logging.getLogger(__name__)

class TeamDatabaseManager:
    """
    Manages all database interactions for team and member data using MongoDB.
    This refactored version simplifies the schema for unregistered members to
    improve performance and reduce code complexity.
    """
    def __init__(self, uri: str, db_name: str = DB_NAME):
        """Initializes the database client and collections."""
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.teams = self.db[TEAMS_COLLECTION]
        self.team_panels = self.db[TEAM_PANELS_COLLECTION]
        self.unregistered = self.db[UNREGISTERED_MEMBERS_COLLECTION]
        self.marathon_state = self.db[MARATHON_STATE_COLLECTION]
        logger.info("Database manager initialized.")

    # ========== GENERIC CRUD OPERATIONS ==========

    async def _update_document(self, collection, filter_query: Dict, update_data: Dict, upsert: bool = False):
        """Generic method to update a single document."""
        update_query = {"$set": {**update_data, "updated_at": datetime.utcnow()}}
        return await collection.update_one(filter_query, update_query, upsert=upsert)

    async def _update_many_documents(self, collection, filter_query: Dict, update_data: Dict):
        """Generic method to update multiple documents."""
        update_query = {"$set": {**update_data, "updated_at": datetime.utcnow()}}
        return await collection.update_many(filter_query, update_query)

    async def _find_document(self, collection, filter_query: Dict) -> Optional[Dict[str, Any]]:
        """Generic method to find a single document."""
        return await collection.find_one(filter_query)

    async def _find_documents(self, collection, filter_query: Dict) -> List[Dict[str, Any]]:
        """Generic method to find multiple documents."""
        cursor = collection.find(filter_query)
        return await cursor.to_list(length=None)

    async def _delete_document(self, collection, filter_query: Dict):
        """Generic method to delete a single document."""
        return await collection.delete_one(filter_query)

    # ========== TEAM MANAGEMENT ==========

    async def get_teams(self, guild_id: int) -> List[Dict[str, Any]]:
        """Retrieves all teams for a given guild."""
        return await self._find_documents(self.teams, {"guild_id": guild_id})

    async def get_team_by_name(self, guild_id: int, team_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific team by its role name."""
        return await self._find_document(self.teams, {"guild_id": guild_id, "team_role": team_name})

    async def insert_team(self, team_data: Dict[str, Any]):
        """Creates a new team document."""
        team_data.update({
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        return await self.teams.insert_one(team_data)

    async def delete_team(self, guild_id: int, team_role: str):
        """Deletes a team document."""
        return await self._delete_document(self.teams, {"guild_id": guild_id, "team_role": team_role})

    async def update_team_field(self, guild_id: int, team_role: str, field: str, value: Any):
        """Updates a specific field of a team document."""
        return await self._update_document(self.teams, {"guild_id": guild_id, "team_role": team_role}, {field: value})

    async def update_team_members(self, guild_id: int, team_role: str, members_dict: Dict[str, Any]):
        """Convenience method to update all members of a team."""
        return await self.update_team_field(guild_id, team_role, "members", members_dict)

    async def update_member_in_teams(self, guild_id: int, user_id: str, updates: Dict[str, Any]):
        """Updates specific fields for a member across all teams they might be in."""
        filter_query = {"guild_id": guild_id, f"members.{user_id}": {"$exists": True}}
        update_data = {f"members.{user_id}.{k}": v for k, v in updates.items()}
        return await self._update_many_documents(self.teams, filter_query, update_data)

    async def find_team_by_member(self, guild_id: int, user_id: str) -> Optional[dict]:
        """Finds the team document that contains a specific member ID."""
        return await self._find_document(self.teams, {"guild_id": guild_id, f"members.{user_id}": {"$exists": True}})

    async def get_max_team_number(self, guild_id: int) -> int:
        """Finds the highest team_number for a guild for efficient numbering."""
        highest_team = await self.teams.find_one({"guild_id": guild_id}, sort=[("team_number", -1)])
        return highest_team.get("team_number", 0) if highest_team else 0

    async def update_team_channel_name(self, guild_id: int, team_name: str, new_channel_name: str):
        """Updates the channel name for a specific team."""
        return await self.update_team_field(guild_id, team_name, "channel_name", new_channel_name)

    async def delete_team_panel(self, guild_id: int):
        """Deletes the team panel message reference."""
        return await self._delete_document(self.team_panels, {"guild_id": guild_id})

    # ========== TEAM PANELS ==========

    async def save_team_panel(self, guild_id: int, channel_id: int, message_id: int):
        """Saves or updates the team panel message reference."""
        return await self._update_document(
            self.team_panels,
            {"guild_id": guild_id},
            {"channel_id": channel_id, "message_id": message_id},
            upsert=True
        )

    async def get_team_panel(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves the team panel message reference."""
        return await self._find_document(self.team_panels, {"guild_id": guild_id})

    # ========== UNREGISTERED MEMBER MANAGEMENT ==========

    async def get_unregistered_document(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves the single document containing all unregistered members for a guild."""
        return await self._find_document(self.unregistered, {"guild_id": guild_id})

    async def save_unregistered_member(self, guild_id: int, user_id: str, member_data: Dict, role_type: str):
        """Saves or updates an unregistered member's data in the correct category (leaders/members)."""
        if role_type not in ["leaders", "members"]:
            raise ValueError("role_type must be 'leaders' or 'members'")

        return await self._update_document(
            self.unregistered,
            {"guild_id": guild_id},
            {f"{role_type}.{user_id}": member_data},
            upsert=True
        )

    async def remove_unregistered_member(self, guild_id: int, user_id: str):
        """Removes a user from both unregistered leader and member lists in a single operation."""
        return await self.unregistered.update_one(
            {"guild_id": guild_id},
            {
                "$unset": {f"leaders.{user_id}": "", f"members.{user_id}": ""},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

    async def move_unregistered_member_role(self, guild_id: int, user_id: str, from_type: str, to_type: str):
        """Atomically moves a member from one role type to another within the unregistered document."""
        if from_type not in ["leaders", "members"] or to_type not in ["leaders", "members"]:
            raise ValueError("role_type must be 'leaders' or 'members'")

        # Find the document and get the member data in one go
        unregistered_doc = await self.get_unregistered_document(guild_id)
        if not unregistered_doc or user_id not in unregistered_doc.get(from_type, {}):
            logger.warning(f"User {user_id} not found in unregistered '{from_type}' list for guild {guild_id}.")
            return False

        member_data = unregistered_doc[from_type][user_id]

        # Perform an atomic move using $rename and $set
        update_pipeline = {
            "$set": {f"{to_type}.{user_id}": member_data, "updated_at": datetime.utcnow()},
            "$unset": {f"{from_type}.{user_id}": ""}
        }

        result = await self.unregistered.update_one({"guild_id": guild_id}, update_pipeline)
        return result.modified_count > 0

    # ========== MARATHON STATE MANAGEMENT ==========

    async def get_marathon_state(self, guild_id: int) -> bool:
        """
        Retrieves the marathon state for a guild.
        Returns True if marathon is active, False if not active or not found.
        """
        state_doc = await self._find_document(self.marathon_state, {"guild_id": guild_id})
        return state_doc.get("is_active", False) if state_doc else False

    async def set_marathon_state(self, guild_id: int, is_active: bool) -> bool:
        """
        Sets the marathon state for a guild.
        Creates a new document if it doesn't exist.
        Returns True if the operation was successful.
        """
        state_data = {
            "is_active": is_active,
            "last_changed": datetime.utcnow()
        }

        result = await self._update_document(
            self.marathon_state,
            {"guild_id": guild_id},
            state_data,
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    async def get_marathon_state_document(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves the full marathon state document for a guild.
        Useful for getting additional metadata like last_changed timestamp.
        """
        return await self._find_document(self.marathon_state, {"guild_id": guild_id})
