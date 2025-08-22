import discord
import re
from discord.ui import Modal, TextInput
from typing import Dict
import logging
from ..models.team import TeamConfig, TeamError

logger = logging.getLogger(__name__)
config = TeamConfig()


class EditChannelNameModal(Modal, title="Edit Team Channel Name"):
    new_name = TextInput(
        label="New Channel Name",
        placeholder="e.g., team-phoenix-crew",
        min_length=3,
        max_length=config.max_team_name_length,
        required=True
    )

    def __init__(self, team_manager, panel_manager, team_data: Dict):
        super().__init__(timeout=300)
        self.team_manager = team_manager
        self.panel_manager = panel_manager
        self.team_data = team_data
        self.new_name.default = team_data.get("channel_name", "")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            formatted_name = self._format_channel_name(self.new_name.value)
            await self.team_manager.team_service.update_team_channel_name(
                interaction.guild.id, self.team_data["team_role"], formatted_name
            )
            await self._update_discord_channel(interaction.guild, formatted_name)
            await interaction.followup.send(f"✅ Channel name updated to `{formatted_name}`.", ephemeral=True)
            await self.panel_manager.refresh_team_panel(interaction.guild.id)
        except TeamError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error editing channel name: {e}", exc_info=True)
            await interaction.followup.send("❌ Unexpected error while updating channel name.", ephemeral=True)

    def _format_channel_name(self, name: str) -> str:
        name = name.lower().strip().replace(" ", "-")
        name = re.sub(r"[^a-z0-9\-]", "", name)
        if len(name) < 3:
            raise TeamError("Channel name must be at least 3 valid characters long.")
        return name

    async def _update_discord_channel(self, guild: discord.Guild, new_name: str):
        old_name = self.team_data.get("channel_name")
        if not old_name:
            return
        channel = discord.utils.get(guild.text_channels, name=old_name)
        if channel:
            try:
                await channel.edit(name=new_name, reason=f"Channel rename by {guild.me.display_name}")
            except discord.Forbidden:
                logger.warning(f"Missing permissions to rename channel '{old_name}'.")
            except discord.HTTPException as e:
                logger.error(f"Failed to rename channel '{old_name}': {e}")


class DeleteMemberModal(Modal, title="Remove Member(s) from Team"):
    member_numbers = TextInput(
        label="Member Number(s)",
        placeholder="Enter number(s), e.g., 2, 5",
        min_length=1,
        max_length=100,
        required=True
    )

    def __init__(self, team_manager, panel_manager, team_role: str):
        super().__init__(timeout=300)
        self.team_manager = team_manager
        self.panel_manager = panel_manager
        self.team_role = team_role

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            input_numbers_str = [n.strip() for n in self.member_numbers.value.split(',')]
            if not all(n.isdigit() for n in input_numbers_str):
                return await interaction.followup.send("❌ Please enter valid numbers only.", ephemeral=True)

            team = await self.team_manager.team_service.get_team(interaction.guild.id, self.team_role)
            members_list = list(team.members.items())

            member_ids_to_remove, invalid_numbers = set(), []
            for num_str in input_numbers_str:
                idx = int(num_str) - 1
                if 0 <= idx < len(members_list):
                    user_id, _ = members_list[idx]
                    member_ids_to_remove.add(user_id)
                else:
                    invalid_numbers.append(num_str)

            if not member_ids_to_remove:
                return await interaction.followup.send("❌ No valid numbers provided.", ephemeral=True)

            removed, invalid = await self.team_manager.member_service.remove_members_from_team(
                interaction.guild.id, team, member_ids_to_remove
            )

            msg = [f"**Results for {self.team_role}:**"]
            if removed:
                msg.append(f"✅ Removed {len(removed)} member(s).")
            if invalid_numbers:
                msg.append(f"⚠️ Invalid numbers: {', '.join(invalid_numbers)}.")
            if invalid:
                msg.append(f"⚠️ {len(invalid)} member(s) were not in the team.")

            await interaction.followup.send("\n".join(msg), ephemeral=True)
            await self.panel_manager.refresh_team_panel(interaction.guild.id)
        except TeamError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in DeleteMemberModal: {e}", exc_info=True)
            await interaction.followup.send("❌ Unexpected error while removing members.", ephemeral=True)


class TeamFormationModal(Modal, title="Confirm New Team Formation"):
    confirmation = TextInput(
        label="Confirm Formation",
        placeholder="Type 'FORM' to confirm.",
        min_length=4,
        max_length=4,
        required=True
    )

    def __init__(self, db, team_manager, panel_manager):
        super().__init__(timeout=300)
        self.db = db
        self.team_manager = team_manager
        self.panel_manager = panel_manager

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.upper() != 'FORM':
            return await interaction.response.send_message("❌ Confirmation text mismatch.", ephemeral=True)

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            unassigned_doc = await self.db.get_unregistered_document(interaction.guild_id)
            leaders, members = [], []

            if unassigned_doc:
                for user_id, data in unassigned_doc.get("leaders", {}).items():
                    leader_profile = dict(data)
                    leader_profile["user_id"] = user_id
                    leaders.append(leader_profile)
                for user_id, data in unassigned_doc.get("members", {}).items():
                    member_profile = dict(data)
                    member_profile["user_id"] = user_id
                    members.append(member_profile)

            if not leaders and not members:
                return await interaction.followup.send("ℹ️ No unassigned members found.", ephemeral=True)

            proposed_teams = await self.team_manager.formation_service.form_teams_hierarchical(leaders, members)
            if not proposed_teams:
                return await interaction.followup.send("ℹ️ Could not form teams with current members.", ephemeral=True)

            embed = discord.Embed(
                title="🚀 Proposed Team Formation",
                description=f"Algorithm suggests **{len(proposed_teams)}** new team(s).",
                color=discord.Color.blue()
            )
            for i, team in enumerate(proposed_teams, 1):
                member_list = "\n".join([f"• {m.display_name} ({m.role_title})" for m in team.members.values()])
                embed.add_field(name=f"Team {i}", value=member_list, inline=False)

            from ..ui.views import FormationResultsView
            view = FormationResultsView(self.team_manager, self.panel_manager, proposed_teams)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in TeamFormationModal: {e}", exc_info=True)
            await interaction.followup.send("❌ Unexpected error during team formation.", ephemeral=True)
