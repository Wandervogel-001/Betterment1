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
    """Persistent Team Management Panel with primary action buttons."""
    def __init__(self, team_manager, marathon_service, panel_manager, db, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        # Row 0: Core Team & Reflection Actions
        self.add_item(ViewTeamButton(team_manager, panel_manager))
        self.add_item(DeleteTeamButton(team_manager, panel_manager))
        self.add_item(ReflectButton(team_manager, panel_manager, db))
        # Row 1: Marathon Lifecycle & Syncing
        self.add_item(StartMarathonButton(team_manager,  marathon_service, panel_manager))
        self.add_item(EndMarathonButton(team_manager,  marathon_service, panel_manager))
        self.add_item(FetchDataButton(team_manager, panel_manager))
        self.add_item(RefreshButton(panel_manager))


# ========== Team Selection & Management Views ==========

class TeamDropdown(Select):
    """Dropdown menu to select a team for view/delete actions."""
    def __init__(self, team_manager, panel_manager, teams: List[Team], action: str):
        self.team_manager = team_manager
        self.panel_manager = panel_manager
        self.action = action

        options = [
            discord.SelectOption(
                label=team.team_role,
                description=f"#{team.channel_name} | {len(team.members)} members",
                value=team.team_role
            ) for team in teams
        ]
        super().__init__(placeholder=f"Select a team to {self.action}...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_team_name = self.values[0]

        try:
            team = await self.team_manager.team_service.get_team(interaction.guild_id, selected_team_name)

            if self.action == "view":
                embed = await self._build_team_embed(interaction.guild, team)
                view = TeamManagementView(self.team_manager, self.panel_manager, team)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)

            elif self.action == "delete":
                view = ConfirmDeleteView(self.team_manager, self.panel_manager, selected_team_name)
                await interaction.followup.send(
                    f"**Are you sure you want to permanently delete `{selected_team_name}`?**\nThis will also delete its Discord role and channel, if they exist.",
                    view=view,
                    ephemeral=True
                )
        except TeamNotFoundError:
            await interaction.followup.send(f"❌ Team `{selected_team_name}` no longer exists.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in TeamDropdown callback ({self.action}): {e}", exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

    async def _build_team_embed(self, guild: discord.Guild, team: Team) -> discord.Embed:
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
                line = f"`{i: >2} • {discord_member.display_name} • {get_member_role_title(discord_member)}`"
            else:
                line = f"`{i: >2} • {db_member.display_name} • (Deactivated)`"
            members_info.append(line)

        embed.add_field(name=f"Members ({len(team.members)})", value="\n".join(members_info), inline=False)
        embed.set_footer(text=f"Team ID: {team.team_role}")
        return embed


class TeamDropdownView(View):
    def __init__(self, team_manager, panel_manager, teams: List[Team], action: str, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.add_item(TeamDropdown(team_manager, panel_manager, teams, action))


class TeamManagementView(View):
    def __init__(self, team_manager, panel_manager, team: Team, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        team_data = {"team_role": team.team_role, "channel_name": team.channel_name}
        self.add_item(EditChannelNameButton(team_manager, panel_manager, team_data))
        if team.members:
            self.add_item(DeleteMemberButton(team_manager, panel_manager, team.team_role))


class ConfirmDeleteView(View):
    def __init__(self, team_manager, panel_manager, team_name: str, timeout: Optional[float] = 60):
        super().__init__(timeout=timeout)
        self.add_item(ConfirmDeleteButton(team_manager, panel_manager, team_name))


# ========== Team Formation & Assignment Views ==========

class UnregisteredMemberDropdown(Select):
    def __init__(self, team_manager, panel_manager, unassigned_members: Dict[str, Dict]):
        self.team_manager = team_manager
        self.panel_manager = panel_manager
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

        member_profile = await self.team_manager.member_service.get_unassigned_member_profile(interaction.guild_id, selected_user_id)
        if not member_profile:
            return await interaction.followup.send("❌ Could not find profile for the selected member.", ephemeral=True)

        all_teams = await self.team_manager.team_service.get_all_teams(interaction.guild_id)
        recommendations = await self.team_manager.formation_service.find_best_teams_for_member(member_profile, all_teams)

        if not recommendations:
            return await interaction.followup.send("ℹ️ No suitable teams found for this member.", ephemeral=True)

        view = TeamRecommendationView(self.team_manager, self.panel_manager, selected_user_id, recommendations)
        await interaction.followup.send("Select a recommended team to assign the member to:", view=view, ephemeral=True)


class UnregisteredMemberDropdownView(View):
    def __init__(self, team_manager, panel_manager, unassigned_members: Dict[str, Dict], timeout: float = 180):
        super().__init__(timeout=timeout)
        self.add_item(UnregisteredMemberDropdown(team_manager, panel_manager, unassigned_members))


class TeamRecommendationDropdown(Select):
    def __init__(self, team_manager, panel_manager, user_id: str, recommendations: List[Dict]):
        self.team_manager = team_manager
        self.panel_manager = panel_manager
        self.user_id = user_id
        options = [
            discord.SelectOption(label=rec['team_name'], description=f"Fit Score: {rec['score']}")
            for rec in recommendations[:25]
        ]
        super().__init__(placeholder="Choose a team to assign the member to...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_team_name = self.values[0]

        success, message = await self.team_manager.formation_service.assign_member_to_team(
            interaction.guild, self.user_id, selected_team_name
        )

        for item in self.view.children:
            item.disabled = True

        response_prefix = "✅" if success else "❌"
        await interaction.edit_original_response(content=f"{response_prefix} {message}", view=self.view)

        if success:
            await self.panel_manager.refresh_team_panel(interaction.guild.id)


class TeamRecommendationView(View):
    def __init__(self, team_manager, panel_manager, user_id: str, recommendations: List[Dict], timeout: float = 180):
        super().__init__(timeout=timeout)
        self.add_item(TeamRecommendationDropdown(team_manager, panel_manager, user_id, recommendations))


class FormationResultsView(View):
    def __init__(self, team_manager, panel_manager, proposed_teams: List[Team], timeout: float = 300):
        super().__init__(timeout=timeout)

        confirm_button = discord.ui.Button(label=f"Create {len(proposed_teams)} New Teams", style=discord.ButtonStyle.success)

        async def confirm_callback(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            results = await team_manager.formation_service.batch_create_teams(interaction.guild, proposed_teams)
            await interaction.followup.send(f"✅ Formation complete! Created: {results['created']}, Failed: {len(results['failed'])}.", ephemeral=True)
            await panel_manager.refresh_team_panel(interaction.guild_id)

        confirm_button.callback = confirm_callback
        self.add_item(confirm_button)


class ReflectionActionsView(View):
    def __init__(self, team_manager, panel_manager, db, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.add_item(AssignMemberButton(team_manager, panel_manager, db))
        self.add_item(FormTeamButton(team_manager, panel_manager, db))
