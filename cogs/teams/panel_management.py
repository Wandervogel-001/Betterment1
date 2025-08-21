import discord
from discord import Interaction
from typing import Dict
import logging
import re

from .ui.views import MainPanelView

logger = logging.getLogger(__name__)

class PanelManager:
    """Handles all panel management functionality."""

    def __init__(self, cog):
        self.cog = cog
        self.bot = cog.bot
        self.db = cog.db
        self.team_manager = cog.team_manager

    def _team_sort_key(self, team_name: str) -> int:
        """Extract numeric part from team name for sorting."""
        match = re.search(r'\d+', team_name)
        return int(match.group()) if match else 0

    async def build_teams_embed(self, guild_id: int) -> discord.Embed:
        """Builds the main team management panel embed with up-to-date team info."""
        teams = await self.team_manager.get_all_teams(guild_id)
        is_marathon_active = await self.team_manager.is_marathon_active(guild_id)
        embed = discord.Embed(title="🏆 Team Management Panel", color=discord.Color.blue())

        if not teams:
            embed.description = "No teams are registered yet. Use `/create_team` or the `Reflect` button to find teams."
        else:
            team_list = "\n".join(
                f"• `{team.team_role}` ({len(team.members)} members) - `#{team.channel_name}`"
                for team in teams
            )
            embed.description = f"**Registered Teams:**\n{team_list}"

        # Add marathon state information
        if is_marathon_active:
            embed.set_footer(text="Marathon Status: Active - Teams have Discord channels and roles")
        else:
            embed.set_footer(text="Marathon Status: Inactive - Teams exist in database only")

        return embed

    def build_reflection_embed(self, results: Dict) -> discord.Embed:
        """Build the reflection report embed."""
        embed = discord.Embed(
            title="🔍 Reflection Report",
            color=discord.Color.purple()
        )

        # Display counts of unassigned members
        embed.add_field(
            name="Unassigned Leaders",
            value=str(results.get("unassigned_leader_count", 0)),
            inline=True
        )
        embed.add_field(
            name="Unassigned Members",
            value=str(results.get("unassigned_member_count", 0)),
            inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True) # Spacer

        # Add warnings if needed
        warning_lines = []
        if results["empty_teams"]:
            warning_lines.append(
                f"- Empty Team(s): {' - '.join(f'`{t}`' for t in sorted(results['empty_teams'], key=self._team_sort_key))}"
            )
        if results["no_leader_teams"]:
            warning_lines.append(
                f"- Teams without Leader: {' - '.join(f'`{t}`' for t in sorted(results['no_leader_teams'], key=self._team_sort_key))}"
            )

        if warning_lines:
            embed.add_field(
                name="⚠️ Warnings",
                value="\n".join(warning_lines),
                inline=False
            )

        # Add unassigned members section
        if results["unassigned_members"]:
            formatted = "\n".join(results["unassigned_members"])
            embed.add_field(
                name="Unassigned Members",
                value=f"```{formatted}```",
                inline=False
            )
        else:
            embed.add_field(
                name="Unassigned Members",
                value="✅ All registered members are assigned to teams.",
                inline=False
            )

        return embed

    async def refresh_team_panel(self, guild_id: int, interaction: Interaction = None):
        """
        Refreshes the team panel message after performing a full data sync.
        """
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        # Perform data sync before refreshing the panel
        await self.cog.sync_database_with_discord(guild)

        panel_data = await self.db.get_team_panel(guild_id)
        if not panel_data:
            if interaction:
                await interaction.followup.send("Panel data not found. Please recreate it with `/panel`.", ephemeral=True)
            return

        try:
            channel = guild.get_channel(panel_data["channel_id"])
            if not channel:
                await self.db.delete_team_panel(guild_id)
                return

            msg = await channel.fetch_message(panel_data["message_id"])
            embed = await self.build_teams_embed(guild_id)
            view = MainPanelView(self.cog)
            await msg.edit(embed=embed, view=view)
            self.bot.add_view(view, message_id=msg.id)
            if interaction:
                await interaction.followup.send("✅ Panel and data refreshed.", ephemeral=True)
        except discord.NotFound:
            await self.db.delete_team_panel(guild_id)
        except Exception as e:
            logger.error(f"Error refreshing panel for guild {guild_id}: {e}")
