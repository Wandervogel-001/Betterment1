import discord
import re
from discord.ui import Modal, TextInput
from typing import Dict
import logging
from ..models.team import TeamConfig, TeamError

logger = logging.getLogger(__name__)
config = TeamConfig()

class EditChannelNameModal(Modal, title="Edit Team Channel Name"):
    """A modal for editing a team's dedicated text channel name."""

    new_name = TextInput(
        label="New Channel Name",
        placeholder="e.g., team-phoenix-crew",
        min_length=3,
        max_length=config.max_team_name_length,
        required=True
    )

    def __init__(self, cog, team_data: Dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.team_data = team_data
        self.new_name.default = team_data.get("channel_name", "")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            formatted_name = self._format_channel_name(self.new_name.value)

            # Update database first
            await self.cog.team_manager.team_service.update_team_channel_name(
                interaction.guild.id,
                self.team_data["team_role"],
                formatted_name
            )

            # Update Discord channel if it exists
            await self._update_discord_channel(interaction.guild, formatted_name)

            await interaction.followup.send(f"✅ Channel name updated to `{formatted_name}`.", ephemeral=True)
            await self.cog.panel_manager.refresh_team_panel(interaction.guild.id)

        except TeamError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error editing channel name: {e}", exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred while updating the channel name.", ephemeral=True)

    def _format_channel_name(self, name: str) -> str:
        """Formats the channel name to be compliant with Discord's naming rules."""
        name = name.lower().strip().replace(" ", "-")
        name = re.sub(r"[^a-z0-9\-]", "", name)
        if len(name) < 3:
            raise TeamError("Channel name must be at least 3 valid characters long.")
        return name

    async def _update_discord_channel(self, guild: discord.Guild, new_name: str):
        """Finds the old channel and edits its name in Discord."""
        old_name = self.team_data.get("channel_name")
        if not old_name:
            return

        channel = discord.utils.get(guild.text_channels, name=old_name)
        if channel:
            try:
                await channel.edit(name=new_name, reason=f"Channel rename initiated by {guild.me.display_name}")
            except discord.Forbidden:
                logger.warning(f"Missing permissions to rename channel '{old_name}'.")
            except discord.HTTPException as e:
                logger.error(f"Failed to rename Discord channel '{old_name}': {e}")


class DeleteMemberModal(Modal, title="Remove Member(s) from Team"):
    """A modal for removing one or more members from a team using their number from the list."""

    member_numbers = TextInput(
        label="Member Number(s)",
        placeholder="Enter number(s) from the list, e.g., 2, 5",
        min_length=1,
        max_length=100,
        required=True
    )

    def __init__(self, cog, team_role: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.team_role = team_role

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            input_numbers_str = [n.strip() for n in self.member_numbers.value.split(',')]
            if not all(n.isdigit() for n in input_numbers_str):
                return await interaction.followup.send("❌ Please enter valid numbers only, separated by commas.", ephemeral=True)

            # Get the full team object
            team = await self.cog.team_manager.team_service.get_team(interaction.guild.id, self.team_role)
            members_list = list(team.members.items())

            member_ids_to_remove = set()
            invalid_numbers = []

            for num_str in input_numbers_str:
                member_index = int(num_str) - 1
                if 0 <= member_index < len(members_list):
                    user_id, _ = members_list[member_index]
                    member_ids_to_remove.add(user_id)
                else:
                    invalid_numbers.append(num_str)

            if not member_ids_to_remove:
                return await interaction.followup.send("❌ No valid member numbers were provided.", ephemeral=True)

            removed_members, invalid_members = await self.cog.team_manager.member_service.remove_members_from_team(
                interaction.guild.id, team, member_ids_to_remove
            )

            # Build response message
            message_parts = [f"**Results for {self.team_role}:**"]
            if len(removed_members) > 0:
                message_parts.append(f"✅ Successfully removed {len(removed_members)} member(s).")
            if invalid_numbers:
                message_parts.append(f"⚠️ The following numbers were invalid: {', '.join(invalid_numbers)}.")
            if len(invalid_members) > 0:
                message_parts.append(f"⚠️ {len(invalid_members)} specified member(s) were not in the team.")

            await interaction.followup.send("\n".join(message_parts), ephemeral=True)
            await self.cog.panel_manager.refresh_team_panel(interaction.guild.id)

        except TeamError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error deleting member via modal: {e}", exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred while removing member(s).", ephemeral=True)


class TeamFormationModal(Modal, title="Confirm New Team Formation"):
    """A modal that acts as a final confirmation gate for automatic team formation."""

    confirmation = TextInput(
        label="Confirm Formation",
        placeholder="Type 'FORM' to confirm and start the process.",
        min_length=4,
        max_length=4,
        required=True
    )

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.upper() != 'FORM':
            return await interaction.response.send_message("❌ Confirmation text did not match. Aborting team formation.", ephemeral=True)

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            unassigned_doc = await self.cog.db.get_unregistered_document(interaction.guild_id)

            leaders, members = [], []

            if unassigned_doc:
                # Process leaders - include user_id in the profile data
                for user_id, profile_data in unassigned_doc.get("leaders", {}).items():
                    leader_profile = dict(profile_data)  # Make a copy
                    leader_profile['user_id'] = user_id  # Add user_id to the profile
                    leaders.append(leader_profile)

                # Process members - include user_id in the profile data
                for user_id, profile_data in unassigned_doc.get("members", {}).items():
                    member_profile = dict(profile_data)  # Make a copy
                    member_profile['user_id'] = user_id  # Add user_id to the profile
                    members.append(member_profile)

            if not leaders and not members:
                return await interaction.followup.send("ℹ️ No unassigned members found to form teams with.", ephemeral=True)

            proposed_teams = await self.cog.team_manager.formation_service.form_teams_hierarchical(leaders, members)

            if not proposed_teams:
                return await interaction.followup.send("ℹ️ The algorithm could not form any new teams with the current members.", ephemeral=True)

            # Display results in a new view for final confirmation
            embed = discord.Embed(
                title="🚀 Proposed Team Formation",
                description=f"The algorithm suggests creating **{len(proposed_teams)}** new team(s).\nReview the teams below and press confirm to create their roles and channels.",
                color=discord.Color.blue()
            )
            for i, team in enumerate(proposed_teams, 1):
                member_list = "\n".join([f"• {m.display_name} ({m.role_title})" for m in team.members.values()])
                embed.add_field(name=f"Proposed Team {i}", value=member_list, inline=False)

            from ..ui.views import FormationResultsView
            view = FormationResultsView(self.cog, proposed_teams)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error during team formation process: {e}", exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred while forming teams.", ephemeral=True)
