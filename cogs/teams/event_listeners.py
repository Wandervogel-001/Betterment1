import discord
import logging

from .ui.views import MainPanelView
from .profile_parsing import ProfileParser
from config import REACTION_EMOJI

logger = logging.getLogger(__name__)

class EventListeners:
    """Handles all event listeners for the bot."""

    def __init__(self, bot, db, profile_parser, team_manager, marathon_service, panel_manager, config, permission_manager):
        self.bot = bot
        self.db = db
        self.profile_parser = profile_parser
        self.team_manager = team_manager
        self.marathon_service = marathon_service
        self.panel_manager = panel_manager
        self.config = config
        self.permission_manager = permission_manager

    async def on_ready(self):
        """Initializes the cog and restores persistent views."""
        for guild in self.bot.guilds:
            try:
                # Refresh panel on startup to ensure views are active
                panel_data = await self.db.get_team_panel(guild.id)
                if panel_data:
                    self.bot.add_view(
                        MainPanelView(self.team_manager, self.marathon_service, self.panel_manager, self.db),
                        message_id=panel_data["message_id"]
                    )
            except Exception as e:
                logger.error(f"Error restoring panel view for guild {guild.id}: {e}")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handles profile parsing via reaction."""
        if payload.channel_id != self.config.communication_channel_id or str(payload.emoji) != REACTION_EMOJI:
            return

        guild = self.bot.get_guild(payload.guild_id)
        reactor = guild.get_member(payload.user_id)

        if not guild or not reactor or not self.permission_manager.is_moderator(reactor):
            return

        try:
            channel = guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            if message.author.bot:
                return
            await self.profile_parser.handle_profile_parsing(message, payload.guild_id)
        except discord.NotFound:
            pass
