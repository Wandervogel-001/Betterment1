import discord
from discord.ui import View, Select
from typing import List, Dict, Optional
import logging

from ..utils.team_utils import fetch_member_safely, get_member_role_title
from ..models.team import Team, TeamNotFoundError
from .buttons import (
    ViewTeamButton, DeleteTeamButton, StartMarathonButton, EndMarathonButton,
    ReflectButton, RefreshButton, EditChannelNameButton, DeleteMemberButton,
    ConfirmDeleteButton, AssignMemberButton, FormTeamButton, FetchDataButton
)

logger = logging.getLogger(__name__)

# ========== Main Panel View ==========

class MainPanelView(View):
    """
    The main, persistent view for the Team Management Panel. It contains all
    primary action buttons, which are now the refactored, consistent versions.
    """
    def __init__(self, cog, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        # Row 0: Core Team & Reflection Actions
        self.add_item(ViewTeamButton(cog))
        self.add_item(DeleteTeamButton(cog))
        self.add_item(ReflectButton(cog)) # Combines reflection and formation

        # Row 1: Marathon Lifecycle & Syncing
        self.add_item(StartMarathonButton(cog))
        self.add_item(EndMarathonButton(cog))
        self.add_item(FetchDataButton(cog))
        self.add_item(RefreshButton(cog)) # handles full data sync and UI refresh

# ========== Team Selection & Management Views ==========

class TeamDropdown(Select):
    """A dropdown menu to select a team for a specific action (view/delete)."""
    def __init__(self, cog, teams: List[Team], action: str):
        self.cog = cog
        self.action = action

        options = [
            discord.SelectOption(
                label=team.team_role,
                description=f"#{team.channel_name} | {len(team.members)} members",
                value=team.team_role
            ) for team in teams
        ]

        placeholder = f"Select a team to {self.action}..."
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_team_name = self.values[0]

        try:
            team = await self.cog.team_manager.team_service.get_team(interaction.guild_id, selected_team_name)

            if self.action == "view":
                embed = await self._build_team_embed(interaction.guild, team)
                view = TeamManagementView(self.cog, team)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)

            elif self.action == "delete":
                view = ConfirmDeleteView(self.cog, team.team_role)
                await interaction.followup.send(
                    f"**Are you sure you want to permanently delete `{team.team_role}`?**\nThis will also delete its Discord role and channel, if they exist.",
                    view=view,
                    ephemeral=True
                )
        except TeamNotFoundError:
            await interaction.followup.send(f"❌ Team `{selected_team_name}` no longer exists.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in TeamDropdown callback for action '{self.action}': {e}", exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

    async def _build_team_embed(self, guild: discord.Guild, team: Team) -> discord.Embed:
        """Builds a detailed embed for a single team, showing real-time member status."""
        embed = discord.Embed(title=f"Team Details: {team.team_role}", color=discord.Color.blue())
        embed.add_field(name="Channel", value=f"`#{team.channel_name}`", inline=True)
        embed.add_field(name="Team Number", value=f"`{team.team_number}`", inline=True)

        if not team.members:
            embed.add_field(name="Members (0)", value="This team has no members.", inline=False)
            return embed

        members_info = []
        for i, (user_id, db_member) in enumerate(team.members.items(), 1):
            discord_member = await fetch_member_safely(guild, user_id)
            if discord_member:
                # Use live data for display
                current_role = get_member_role_title(discord_member)
                line = f"`{i: >2} • {discord_member.display_name} • {current_role}`"
            else:
                # Member has left the server
                line = f"`{i: >2} • {db_member.display_name} • (Deactivated)`"
            members_info.append(line)

        embed.add_field(name=f"Members ({len(team.members)})", value="\n".join(members_info), inline=False)
        embed.set_footer(text=f"Team ID: {team.team_role}")
        return embed

class TeamDropdownView(View):
    """A view that simply holds the TeamDropdown."""
    def __init__(self, cog, teams: List[Team], action: str, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.add_item(TeamDropdown(cog, teams, action))

class TeamManagementView(View):
    """A view providing management buttons for a specific team (e.g., edit, remove member)."""
    def __init__(self, cog, team: Team, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        team_data = {"team_role": team.team_role, "channel_name": team.channel_name}

        self.add_item(EditChannelNameButton(cog, team_data))
        if team.members:
            self.add_item(DeleteMemberButton(cog, team.team_role))

class ConfirmDeleteView(View):
    """A view that holds the confirmation button for a team deletion."""
    def __init__(self, cog, team_name: str, timeout: Optional[float] = 60):
        super().__init__(timeout=timeout)
        self.add_item(ConfirmDeleteButton(cog, team_name))

# ========== Team Formation & Assignment Views ==========

class UnregisteredMemberDropdown(Select):
    """Dropdown for selecting an unassigned member to assign to a team."""
    def __init__(self, cog, unassigned_members: Dict[str, Dict]):
        self.cog = cog
        options = [
            discord.SelectOption(
                label=data.get('display_name', f"ID: {user_id}"),
                description=f"Role: {data.get('role_title', 'Unknown')}",
                value=user_id
            ) for user_id, data in unassigned_members.items()
        ]
        super().__init__(placeholder="Select an unassigned member...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        selected_user_id = self.values[0]

        member_profile = await self.cog.team_manager.member_service.get_unassigned_member_profile(interaction.guild_id, selected_user_id)
        if not member_profile:
            return await interaction.followup.send("❌ Could not find profile for the selected member.", ephemeral=True)

        all_teams = await self.cog.team_manager.team_service.get_all_teams(interaction.guild_id)
        recommendations = await self.cog.team_manager.formation_service.find_best_teams_for_member(member_profile, all_teams)

        if not recommendations:
            return await interaction.followup.send("ℹ️ No suitable teams found for this member.", ephemeral=True)

        view = TeamRecommendationView(self.cog, selected_user_id, recommendations)
        await interaction.followup.send("Select a recommended team to assign the member to:", view=view, ephemeral=True)

class UnregisteredMemberDropdownView(View):
    """View that holds the UnregisteredMemberDropdown."""
    def __init__(self, cog, unassigned_members: Dict[str, Dict], timeout: float = 180):
        super().__init__(timeout=timeout)
        self.add_item(UnregisteredMemberDropdown(cog, unassigned_members))

class TeamRecommendationDropdown(Select):
    """A dropdown of recommended teams that directly triggers member assignment on selection."""
    def __init__(self, cog, user_id: str, recommendations: List[Dict]):
        self.cog = cog
        self.user_id = user_id
        options = [
            discord.SelectOption(label=rec['team_name'], description=f"Fit Score: {rec['score']}")
            for rec in recommendations[:25]
        ]
        super().__init__(placeholder="Choose a team to assign the member to...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer() # Acknowledge interaction immediately
        selected_team_name = self.values[0]

        success, message = await self.cog.team_manager.formation_service.assign_member_to_team(
            interaction.guild, self.user_id, selected_team_name
        )

        # Disable the view after the action
        for item in self.view.children:
            item.disabled = True

        response_prefix = "✅" if success else "❌"
        await interaction.edit_original_response(content=f"{response_prefix} {message}", view=self.view)

        if success:
            await self.cog.panel_manager.refresh_team_panel(interaction.guild.id)

class TeamRecommendationView(View):
    """A view that holds the direct-action TeamRecommendationDropdown."""
    def __init__(self, cog, user_id: str, recommendations: List[Dict], timeout: float = 180):
        super().__init__(timeout=timeout)
        self.add_item(TeamRecommendationDropdown(cog, user_id, recommendations))

class FormationResultsView(View):
    """Displays proposed new teams and provides a button to confirm their creation."""
    def __init__(self, cog, proposed_teams: List[Team], timeout: float = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.proposed_teams = proposed_teams

        confirm_button = discord.ui.Button(label=f"Create {len(proposed_teams)} New Teams", style=discord.ButtonStyle.success)

        async def confirm_callback(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            results = await self.cog.team_manager.formation_service.batch_create_teams(interaction.guild, self.proposed_teams)

            await interaction.followup.send(f"✅ Formation complete! Created: {results['created']}, Failed: {len(results['failed'])}.", ephemeral=True)
            await self.cog.panel_manager.refresh_team_panel(interaction.guild_id)

        confirm_button.callback = confirm_callback
        self.add_item(confirm_button)

class ReflectionActionsView(View):
    """A view that holds the team formation action buttons, shown after a reflection."""
    def __init__(self, cog, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.add_item(AssignMemberButton(cog))
        self.add_item(FormTeamButton(cog))
