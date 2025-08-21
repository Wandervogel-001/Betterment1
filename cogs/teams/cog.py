import discord
from discord.ext import commands
from discord import app_commands, Interaction, Member
import logging
from typing import Dict, Optional

from .services.team_manager import TeamManager
from .services.ai_handler import AIHandler
from .services.marathon_service import MarathonService
from .models.team import TeamConfig, TeamError, InvalidTeamError, TeamNotFoundError
from .ui.views import MainPanelView

# Import the separated modules
from .permissions import PermissionManager, moderator_required
from .panel_management import PanelManager
from .event_listeners import EventListeners
from .profile_parsing import ProfileParser

logger = logging.getLogger(__name__)

class TeamsCog(commands.Cog):
    """
    Main cog for all team management functionality. This refactored version
    centralizes permission checking and data synchronization for improved
    consistency and maintainability across all commands and UI components.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.config = TeamConfig()
        self.team_manager = TeamManager(self.db)
        self.ai_handler = AIHandler()
        self.marathon_service = MarathonService(self)

        # Initialize component managers
        self.permission_manager = PermissionManager()
        self.panel_manager = PanelManager(self)
        self.event_listeners = EventListeners(self)
        self.profile_parser = ProfileParser(self)

        # Add persistent view
        bot.add_view(MainPanelView(self))

    # ========== CORE HELPER METHODS ==========

    async def sync_database_with_discord(self, guild: discord.Guild) -> Dict:
        """
        Centralized method to synchronize the database with the current state of Discord.
        This is the single source of truth for data reflection.
        """
        try:
            report = await self.team_manager.reflect_teams(guild)
            return report
        except Exception as e:
            logger.error(f"Error during data sync for guild {guild.id}: {e}", exc_info=True)
            return {}

    # ========== EVENT LISTENERS ==========

    @commands.Cog.listener()
    async def on_ready(self):
        """Initializes the cog and restores persistent views."""
        await self.event_listeners.on_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handles profile parsing via reaction."""
        await self.event_listeners.on_raw_reaction_add(payload)

    # ========== SLASH COMMANDS ==========

    @app_commands.command(name="panel", description="Creates the main team management panel.")
    @moderator_required
    async def create_panel(self, interaction: discord.Interaction):
        """Create or refresh the team management panel."""
        await interaction.response.defer(ephemeral=True)
        # Check for existing panel
        existing = await self.db.get_team_panel(interaction.guild_id)
        if existing:
            try:
                channel = self.bot.get_channel(existing["channel_id"])
                await channel.fetch_message(existing["message_id"])
                await interaction.followup.send(
                    "ℹ️ Team panel already exists in this server.",
                    ephemeral=True
                )
                return
            except (discord.NotFound, discord.Forbidden):
                await self.db.delete_team_panel(interaction.guild_id)

        # Create new panel
        embed = await self.panel_manager.build_teams_embed(interaction.guild_id)
        view = MainPanelView(self)
        msg = await interaction.channel.send(embed=embed, view=view)
        await self.db.save_team_panel(interaction.guild_id, interaction.channel_id, msg.id)
        await interaction.followup.send("✅ Team management panel created!",ephemeral=True)

    @app_commands.command(name="sync", description="Manually synchronizes the database with Discord.")
    @moderator_required
    async def sync_command(self, interaction: Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        report = await self.sync_database_with_discord(interaction.guild)
        await interaction.followup.send("✅ Database synchronization complete." if report else "❌ Sync failed.", ephemeral=True)

    @app_commands.command(name="create_team", description="Creates a new team.")
    @app_commands.describe(team_number="Unique number for the team.", channel_name="Name for the private channel.", members="Mention all team members.")
    @moderator_required
    async def create_team(self, interaction: Interaction, team_number: int, channel_name: str, members: str):
        await interaction.response.defer(ephemeral=True)

        try:
            team = await self.team_manager.create_team(interaction.guild, team_number, channel_name, members)
            response_parts = [f"✅ `{team.team_role}` created with {len(team.members)} members."]
            await interaction.followup.send(" ".join(response_parts), ephemeral=True)
            await self.panel_manager.refresh_team_panel(interaction.guild_id)

        except (InvalidTeamError, TeamError) as e:
            # Add context about marathon state to error messages if relevant
            error_msg = str(e)
            if "don't have 'Team Leader' or 'Team Member' roles" in error_msg:
                is_marathon_active = await self.team_manager.is_marathon_active(interaction.guild_id)
                if is_marathon_active:
                    error_msg += " Note: During marathon, only registered members with team roles can be added."
            await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

    @app_commands.command(name="add_members", description="Adds members to an existing team.")
    @app_commands.describe(team_number="The number of the team (e.g., 1 for Team 1).", members="Mention one or more members to add.")
    @moderator_required
    async def add_members(self, interaction: Interaction, team_number: int, members: str):
        await interaction.response.defer(ephemeral=True)

        try:
            team_name = f"Team {team_number}"
            is_marathon_active = await self.team_manager.is_marathon_active(interaction.guild_id)

            added_members, existing_members, invalid_members, in_other_teams = await self.team_manager.add_members_to_team(
                interaction.guild, team_name, members
            )

            # Build detailed response message
            response_parts = []

            if added_members:
                response_parts.append(f"✅ Successfully added {len(added_members)} members to `{team_name}`.")

            # Build warnings with context
            warnings = []
            if existing_members:
                warnings.append(f"{len(existing_members)} already in this team")
            if in_other_teams:
                warnings.append(f"{len(in_other_teams)} already in other teams")
            if invalid_members:
                if is_marathon_active:
                    warnings.append(f"{len(invalid_members)} invalid/unregistered")
                else:
                    warnings.append(f"{len(invalid_members)} invalid (bots or non-existent users)")

            if warnings:
                response_parts.append(f"⚠️ Skipped members: {', '.join(warnings)}.")

            if not added_members and not warnings:
                response_parts.append("ℹ️ No members were added.")

            await interaction.followup.send(" ".join(response_parts), ephemeral=True)
            await self.panel_manager.refresh_team_panel(interaction.guild_id)

        except TeamError as e:
            # Add context about marathon state to error messages if relevant
            error_msg = str(e)
            if "don't have 'Team Leader' or 'Team Member' roles" in error_msg:
                is_marathon_active = await self.team_manager.is_marathon_active(interaction.guild_id)
                if is_marathon_active:
                    error_msg += " Note: During marathon, only registered members with team roles can be added."
            await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

    @app_commands.command(name="manual_save", description="Manually saves profile data for an unassigned member.")
    @app_commands.describe(user="The member to save data for.", timezone="e.g., EST, PST, GMT", goals="Comma-separated list.", habits="Comma-separated list.")
    @moderator_required
    async def manual_save(self, interaction: Interaction, user: Member, timezone: str = None, goals: str = None, habits: str = None):
        await interaction.response.defer(ephemeral=True)

        profile_data = {}
        if timezone: profile_data["timezone"] = timezone.strip()
        if goals: profile_data["goals"] = [g.strip() for g in goals.split(',')]
        if habits: profile_data["habits"] = [h.strip() for h in habits.split(',')]

        if not profile_data:
            return await interaction.followup.send("❌ No data provided to save.", ephemeral=True)

        role_title = self.team_manager._get_member_role_title(user)
        if role_title == "Unregistered":
            return await interaction.followup.send(f"❌ {user.mention} needs a 'Team Leader' or 'Team Member' role.", ephemeral=True)

        role_type = "leaders" if role_title == "Team Leader" else "members"
        member_data = {"username": user.name, "display_name": user.display_name, "role_title": role_title, "profile_data": profile_data}
        await self.db.save_unregistered_member(interaction.guild.id, str(user.id), member_data, role_type)
        await interaction.followup.send(f"✅ Profile data saved for unassigned member {user.mention}.", ephemeral=True)

    @app_commands.command(name="marathon_status", description="Shows the current marathon state and provides management options.")
    @app_commands.describe(
        set_active="Optional: Set marathon state to active (True) or inactive (False)"
    )
    @moderator_required
    async def marathon_status(self, interaction: Interaction, set_active: Optional[bool] = None):
        await interaction.response.defer(ephemeral=True)

        try:
            # If set_active parameter is provided, update the marathon state
            if set_active is not None:
                # Update the marathon state in the database
                success = await self.team_manager.db.set_marathon_state(interaction.guild_id, set_active)

                if not success:
                    await interaction.followup.send("❌ Failed to update marathon state.", ephemeral=True)
                    return

                # Create confirmation message
                state_text = "**ACTIVE**" if set_active else "**INACTIVE**"
                action_text = "activated" if set_active else "deactivated"

                embed = discord.Embed(
                    title="Marathon State Updated",
                    description=f"Marathon has been **{action_text}**",
                    color=discord.Color.green() if set_active else discord.Color.orange()
                )

                embed.add_field(
                    name="New State",
                    value=state_text,
                    inline=True
                )

                embed.add_field(
                    name="Changed By",
                    value=interaction.user.mention,
                    inline=True
                )

                embed.add_field(
                    name="Timestamp",
                    value=f"<t:{int(discord.utils.utcnow().timestamp())}:F>",
                    inline=True
                )

                if set_active:
                    embed.add_field(
                        name="Effects",
                        value="• Teams now have Discord roles and channels\n• Only registered members can join teams\n• Team resources are provisioned automatically",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Effects",
                        value="• Teams exist in database only\n• Unregistered members can join teams\n• No Discord resources are provisioned",
                        inline=False
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)
                await self.panel_manager.refresh_team_panel(interaction.guild_id)

            else:
                state_info = await self.team_manager.get_marathon_state_info(interaction.guild_id)
                is_active = state_info["is_active"]

                embed = discord.Embed(
                    title="Marathon Status",
                    color=discord.Color.green() if is_active else discord.Color.orange()
                )

                if is_active:
                    embed.add_field(
                        name="Current State",
                        value="**ACTIVE**\n• Teams have Discord roles and channels\n• Only registered members can join teams\n• Team resources are provisioned automatically",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Current State",
                        value="**INACTIVE**\n• Teams exist in database only\n• Unregistered members can join teams\n• No Discord resources are provisioned",
                        inline=False
                    )

                if state_info.get("last_changed"):
                    embed.add_field(
                        name="Last Changed",
                        value=f"<t:{int(state_info['last_changed'].timestamp())}:R>",
                        inline=True
                    )

                embed.add_field(
                    name="Usage",
                    value="Use `/marathon_status set_active:True` to activate\nUse `/marathon_status set_active:False` to deactivate",
                    inline=False
                )

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in marathon_status command: {e}")
            await interaction.followup.send("❌ Failed to process marathon status command.", ephemeral=True)


    # ========== ERROR HANDLING ==========

    async def cog_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        """Global error handler for slash commands in this cog."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        elif isinstance(error, TeamError):
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        else:
            logger.error(f"An unhandled command error occurred in TeamsCog: {error}", exc_info=True)
            response_method = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
            await response_method("❌ A critical error occurred. The incident has been logged.", ephemeral=True)

async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(TeamsCog(bot))
    logger.info("TeamsCog loaded successfully.")
