import discord
from discord.ui import Button
from typing import Dict
import logging

from ..models.team import TeamNotFoundError
from .modals import DeleteMemberModal, EditChannelNameModal, TeamFormationModal

from ..permissions import moderator_required

logger = logging.getLogger(__name__)

class TeamButton(Button):
    """
    Base class for team management buttons. It provides centralized error handling
    and a consistent structure for callbacks. Permissions are now handled by the
    @moderator_required decorator.
    """
    def __init__(self, cog, **kwargs):
        super().__init__(**kwargs)
        self.cog = cog

    async def handle_error(self, interaction: discord.Interaction, error: Exception):
        """Standardized error handling for all button interactions."""
        logger.error(f"Error in '{self.label}' button: {error}", exc_info=True)
        # Use followup if the initial response was already sent
        responder = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await responder("❌ An error occurred. The incident has been logged.", ephemeral=True)

class ViewTeamButton(TeamButton):
    """Button to view detailed information about registered teams."""
    def __init__(self, cog):
        super().__init__(cog, label="View Teams", style=discord.ButtonStyle.primary, custom_id="view_team_button", row=0)
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        try:
            from .views import TeamDropdownView # Avoid circular import
            teams = await self.cog.team_manager.team_service.get_all_teams(interaction.guild_id)
            if not teams:
                return await interaction.response.send_message("ℹ️ No teams are registered in the database.", ephemeral=True)

            view = TeamDropdownView(self.cog, teams, action="view")
            await interaction.response.send_message("Select a team to view its details:", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

class DeleteTeamButton(TeamButton):
    """Button to initiate deleting a team."""
    def __init__(self, cog):
        super().__init__(cog, label="Delete Team", style=discord.ButtonStyle.danger, custom_id="delete_team_button", row=0)
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        try:
            from .views import TeamDropdownView # Avoid circular import
            teams = await self.cog.team_manager.team_service.get_all_teams(interaction.guild_id)
            if not teams:
                return await interaction.response.send_message("ℹ️ No teams are available to delete.", ephemeral=True)

            view = TeamDropdownView(self.cog, teams, action="delete")
            await interaction.response.send_message("Select a team to delete:", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

class StartMarathonButton(TeamButton):
    """Button to start the team marathon, creating roles and channels."""
    def __init__(self, cog):
        super().__init__(cog, label="Start Marathon", style=discord.ButtonStyle.success, custom_id="start_marathon_button", row=1)
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            if await self.cog.team_manager.team_service.is_marathon_active(interaction.guild.id):
                return await interaction.followup.send("⚠️ Marathon is already active for this server.", ephemeral=True)
            teams = await self.cog.team_manager.team_service.get_all_teams(interaction.guild.id)
            if not teams:
                return await interaction.followup.send("❌ No registered teams found to start a marathon.", ephemeral=True)

            results = await self.cog.marathon_service.start_marathon(interaction.guild, teams)
            if "error" in results:
                return await interaction.followup.send(f"❌ {results['error']}", ephemeral=True)
            await interaction.followup.send(embed=self._build_results_embed(results), ephemeral=True)
            await self.cog.panel_manager.refresh_team_panel(interaction.guild_id)
        except Exception as e:
            await self.handle_error(interaction, e)

    def _build_results_embed(self, results: Dict) -> discord.Embed:
        """Creates an embed summarizing the results of starting the marathon."""
        embed = discord.Embed(title="🚀 Marathon Start Results", color=discord.Color.green())
        if results['created_roles']:
            embed.add_field(name="✅ Roles Created", value="\n".join(f"• {r}" for r in results['created_roles']), inline=False)
        if results['created_channels']:
            embed.add_field(name="✅ Channels Created", value="\n".join(f"• {c}" for c in results['created_channels']), inline=False)
        if results['skipped_teams']:
            embed.add_field(name="⚠️ Skipped Teams", value="\n".join(f"• {t}" for t in results['skipped_teams']), inline=False)
        if not embed.fields:
            embed.description = "No new roles or channels were created."
        return embed

class EndMarathonButton(TeamButton):
    """Button to end the marathon, cleaning up all related roles and channels."""
    def __init__(self, cog):
        super().__init__(cog, label="End Marathon", style=discord.ButtonStyle.danger, custom_id="end_marathon_button", row=1)
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            if not await self.cog.team_manager.team_service.is_marathon_active(interaction.guild.id):
                return await interaction.followup.send("⚠️ No active marathon found for this server.", ephemeral=True)
            results = await self.cog.marathon_service.end_marathon(interaction.guild)
            if "error" in results:
                return await interaction.followup.send(f"❌ {results['error']}", ephemeral=True)
            if not results['removed_channels'] and not results['processed_teams']:
                return await interaction.followup.send("ℹ️ No active marathon teams were found to clean up.", ephemeral=True)

            await interaction.followup.send(embed=self._build_results_embed(results), ephemeral=True)
            await self.cog.panel_manager.refresh_team_panel(interaction.guild_id)
        except Exception as e:
            await self.handle_error(interaction, e)

    def _build_results_embed(self, results: Dict) -> discord.Embed:
        """Creates an embed summarizing the results of ending the marathon."""
        embed = discord.Embed(title="🏁 Marathon End Results", description="Cleanup summary:", color=discord.Color.orange())
        embed.add_field(name="🗑️ Channels Removed", value="\n".join(f"• {c}" for c in results['removed_channels']) or "None", inline=False)
        embed.add_field(name="✨ Teams Processed", value="\n".join(f"• {t}" for t in results['processed_teams']) or "None", inline=False)
        return embed

class RefreshButton(TeamButton):
    """
    Button to perform a full data synchronization and refresh the panel.
    This is the primary way to ensure the bot's data is aligned with Discord's state.
    """
    def __init__(self, cog):
        super().__init__(cog, label="Refresh", style=discord.ButtonStyle.secondary, custom_id="refresh_button", row=1)
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            # This single call handles both DB sync and panel refresh
            await self.cog.panel_manager.refresh_team_panel(interaction.guild_id, interaction)
        except Exception as e:
            await self.handle_error(interaction, e)

class ReflectButton(TeamButton):
    """
    Button to run a reflection report, analyzing team health and listing unassigned members.
    This serves as the main entry point for team formation actions.
    """
    def __init__(self, cog):
        super().__init__(cog, label="Reflect & Form Teams", style=discord.ButtonStyle.secondary, custom_id="reflect_button", row=0)
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            from .views import ReflectionActionsView # Avoid circular import
            report = await self.cog.sync_database_with_discord(interaction.guild)
            embed = self.cog.panel_manager.build_reflection_embed(report)

            view = ReflectionActionsView(self.cog) if report.get("unassigned_leader_count", 0) + report.get("unassigned_member_count", 0) > 0 else discord.ui.View()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            await self.handle_error(interaction, e)

class FetchDataButton(TeamButton):
    """Button to fetch team data from server."""
    def __init__(self, cog):
        super().__init__(cog, label="Fetch Data", style=discord.ButtonStyle.secondary, custom_id="fetch_data_button", row=1)
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            results = await self.cog.team_manager.team_service.fetch_server_teams(interaction.guild)

            embed = discord.Embed(
                title="🔄 Data Fetch Results",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Registered Teams",
                value=str(results['registered']),
                inline=True
            )
            embed.add_field(
                name="Skipped Registered Teams",
                value=str(results['skipped']),
                inline=True
            )

            if results['details']:
                embed.add_field(
                    name="Details",
                    value="\n".join(results['details']),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

            if results['registered'] > 0:
                await self.cog.panel_manager.refresh_team_panel(interaction.guild_id)
        except Exception as e:
            await self.handle_error(interaction, e)

# --- Individual Team Action Buttons (Used in TeamManagementView) ---

class DeleteMemberButton(TeamButton):
    """Button within a team view to open the member removal modal."""
    def __init__(self, cog, team_role: str):
        super().__init__(cog, label="Remove Member", style=discord.ButtonStyle.danger, custom_id=f"delete_member_{team_role}")
        self.team_role = team_role
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        try:
            # Ensure team still exists before opening modal
            team = await self.cog.team_manager.team_service.get_team(interaction.guild_id, self.team_role)
            if not team.members:
                return await interaction.response.send_message(f"❌ Team `{self.team_role}` has no members to remove.", ephemeral=True)

            await interaction.response.send_modal(DeleteMemberModal(self.cog, self.team_role))
        except TeamNotFoundError:
            await interaction.response.send_message(f"❌ Team `{self.team_role}` no longer exists.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

class EditChannelNameButton(TeamButton):
    """Button within a team view to edit the team's channel name."""
    def __init__(self, cog, team_data: Dict):
        super().__init__(cog, label="Edit Channel", style=discord.ButtonStyle.secondary, custom_id=f"edit_channel_{team_data['team_role']}")
        self.team_data = team_data
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        try:
            # Ensure team exists before opening modal
            await self.cog.team_manager.team_service.get_team(interaction.guild_id, self.team_data["team_role"])
            await interaction.response.send_modal(EditChannelNameModal(self.cog, self.team_data))
        except TeamNotFoundError:
            await interaction.response.send_message(f"❌ Team `{self.team_data['team_role']}` no longer exists.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

class ConfirmDeleteButton(TeamButton):
    """Button in a confirmation view to finalize the deletion of a team."""
    def __init__(self, cog, team_name: str):
        super().__init__(cog, label="Confirm & Delete", style=discord.ButtonStyle.danger, custom_id=f"confirm_delete_{team_name}")
        self.team_name = team_name
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            success = await self.cog.team_manager.team_service.delete_team_and_resources(interaction.guild, self.team_name)

            if success:
                await interaction.followup.send(f"✅ `{self.team_name}` and its resources have been deleted.", ephemeral=True)
                await self.cog.panel_manager.refresh_team_panel(interaction.guild_id) # Refresh panel after deletion
            else:
                await interaction.followup.send(f"⚠️ `{self.team_name}` was not found in the database. It may have already been deleted.", ephemeral=True)

        except Exception as e:
            await self.handle_error(interaction, e)

# --- Team Formation Action Buttons (Used in ReflectionActionsView) ---

class AssignMemberButton(TeamButton):
    """Button to start the process of assigning an unassigned member to a team."""
    def __init__(self, cog):
        super().__init__(cog, label="Assign Member", style=discord.ButtonStyle.success, custom_id="assign_member_button")
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        try:
            from .views import UnregisteredMemberDropdownView # Avoid circular import
            unregistered_doc = await self.cog.db.get_unregistered_document(interaction.guild_id)

            leaders = unregistered_doc.get("leaders", {}) if unregistered_doc else {}
            members = unregistered_doc.get("members", {}) if unregistered_doc else {}

            if not leaders and not members:
                return await interaction.response.send_message("ℹ️ There are no unassigned members to assign.", ephemeral=True)

            view = UnregisteredMemberDropdownView(self.cog, {**leaders, **members})
            await interaction.response.send_message("Select a member to find a suitable team for them:", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)


class FormTeamButton(TeamButton):
    """Button to trigger the automatic hierarchical formation of new teams."""
    def __init__(self, cog):
        super().__init__(cog, label="Form New Teams", style=discord.ButtonStyle.primary, custom_id="form_teams_button")
    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(TeamFormationModal(self.cog))
        except Exception as e:
            await self.handle_error(interaction, e)
