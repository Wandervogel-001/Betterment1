from discord import Message
import logging

from .services.ai_handler import AIExtractionError

logger = logging.getLogger(__name__)

class ProfileParser:
    """Handles profile parsing functionality."""

    def __init__(self, ai_handler, team_manager, db):
        self.ai_handler = ai_handler
        self.team_manager = team_manager
        self.db = db

    async def handle_profile_parsing(self, message: Message, guild_id: int):
        """Internal logic for parsing profile messages from reactions."""
        try:
            extracted_data = await self.ai_handler.extract_profile_data(message.content, guild_id)
            if not extracted_data:
                return await message.channel.send("❌ AI failed to extract data.", delete_after=5)

            role_title = self.team_manager._get_member_role_title(message.author)
            if role_title == "Unregistered":
                return await message.channel.send(f"⚠️ {message.author.mention} needs a team role.", delete_after=15)

            # Save to unassigned members collection
            role_type = "leaders" if role_title == "Team Leader" else "members"
            member_data = {
                "username": message.author.name,
                "display_name": message.author.display_name,
                "role_title": role_title,
                "profile_data": extracted_data
            }
            await self.db.save_unregistered_member(message.guild.id, str(message.author.id), member_data, role_type)
            await message.add_reaction("💾")  # Add a save icon reaction
            logger.info(f"Profile data saved for {message.author.mention}. profile_data: \n{extracted_data}")
        except AIExtractionError as e:
            await message.channel.send(f"❌ AI Error: {e}", delete_after=5)
        except Exception as e:
            logger.error(f"Error in profile parsing: {e}", exc_info=True)
            await message.channel.send("❌ An unexpected error occurred.", delete_after=5)
