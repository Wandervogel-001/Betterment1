import discord
import logging

from .ui.views import MainPanelView
from .profile_parsing import ProfileParser
from config import REACTION_EMOJI

logger = logging.getLogger(__name__)

class EventListeners:
    """Handles all event listeners for the bot."""

    def __init__(self, cog):
        self.cog = cog
        self.bot = cog.bot
        self.db = cog.db
        self.config = cog.config
        self.profile_parser = ProfileParser(cog)

    async def on_ready(self):
        """Initializes the cog and restores persistent views."""
        logger.info(f"{self.cog.__class__.__name__} cog ready.")
        for guild in self.bot.guilds:
            try:
                # Refresh panel on startup to ensure views are active
                panel_data = await self.db.get_team_panel(guild.id)
                if panel_data:
                    self.bot.add_view(MainPanelView(self.cog), message_id=panel_data["message_id"])
            except Exception as e:
                logger.error(f"Error restoring panel view for guild {guild.id}: {e}")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handles profile parsing via reaction."""
        if payload.channel_id != self.config.communication_channel_id or str(payload.emoji) != REACTION_EMOJI:
            return

        guild = self.bot.get_guild(payload.guild_id)
        reactor = guild.get_member(payload.user_id)

        if not guild or not reactor or not self.cog.permission_manager.is_moderator(reactor):
            return

        try:
            channel = guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            if message.author.bot:
                return
            await self.profile_parser.handle_profile_parsing(message)
        except discord.NotFound:
            pass
