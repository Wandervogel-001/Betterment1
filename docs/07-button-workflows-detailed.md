# Button Workflows - Detailed Analysis

## Overview

The `buttons.py` file implements a hierarchical button system with the `TeamButton` base class providing centralized error handling and consistent interaction patterns. All buttons use the `@moderator_required` decorator for permission control and follow a standardized callback structure.

## Base Button Architecture

### TeamButton - Foundation Class

```python
class TeamButton(Button):
    def __init__(self, cog, **kwargs):
        super().__init__(**kwargs)
        self.cog = cog

    async def handle_error(self, interaction: discord.Interaction, error: Exception):
        """Standardized error handling for all button interactions."""
        logger.error(f"Error in '{self.label}' button: {error}", exc_info=True)
        # Smart response handling - use followup if initial response was sent
        responder = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await responder("❌ An error occurred. The incident has been logged.", ephemeral=True)
```

**Purpose**: Provides consistent error handling across all buttons with intelligent response routing based on interaction state.

**Key Features**:
- Logs all errors with full stack traces
- Smart response selection (initial response vs followup)
- Consistent error messaging for users
- Centralizes error handling logic

## Main Panel Buttons (Row 0 & 1)

### ViewTeamButton - Team Selection Interface

```python
class ViewTeamButton(TeamButton):
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
```

**Purpose**: Initiates the team viewing workflow by presenting a dropdown of available teams.

**Workflow**:
1. Fetches all teams from database via `team_service`
2. Handles empty team list with informative message
3. Creates `TeamDropdownView` with `action="view"`
4. Uses local import to avoid circular dependencies
5. Delegates to dropdown for team selection

**Error Handling**: Falls back to base class error handler for any exceptions.

### DeleteTeamButton - Team Deletion Initiation

```python
class DeleteTeamButton(TeamButton):
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
```

**Purpose**: Initiates team deletion workflow with appropriate warning styling.

**Key Differences from ViewTeamButton**:
- Uses `ButtonStyle.danger` to indicate destructive action
- Sets `action="delete"` which triggers confirmation workflow
- Different message text to reflect deletion intent

### ReflectButton - Complex Data Analysis and Formation Gateway

```python
class ReflectButton(TeamButton):
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
```

**Purpose**: Performs comprehensive data analysis and serves as the gateway to team formation actions.

**Complex Workflow**:
1. **Deferred Response**: Uses `defer(thinking=True)` because the operation is potentially long-running
2. **Data Synchronization**: Calls `sync_database_with_discord()` which:
   - Updates team member data from Discord state
   - Syncs unregistered members with current roles
   - Identifies team health issues (empty teams, missing leaders)
3. **Report Generation**: Creates detailed reflection embed showing:
   - Unassigned leader and member counts
   - Team warnings (empty teams, teams without leaders)
   - Formatted list of unassigned members
4. **Conditional View**: Only shows `ReflectionActionsView` if there are unassigned members to work with
5. **Uses Followup**: Since interaction was deferred, uses `followup.send()`

**Data Analysis Details**:
- Calls `team_manager.reflect_teams()` which orchestrates multiple service calls
- Analyzes team completeness and member distribution
- Identifies potential formation opportunities

### StartMarathonButton - Resource Provisioning

```python
class StartMarathonButton(TeamButton):
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
```

**Purpose**: Transitions teams from database-only state to active Discord resources (roles and channels).

**Complex Operations**:
1. **State Validation**: Checks if marathon is already active
2. **Team Validation**: Ensures teams exist before starting
3. **Resource Creation**: Delegates to `marathon_service.start_marathon()` which:
   - Creates Discord roles for each team
   - Creates private text channels
   - Sets proper permissions
   - Assigns members to roles
4. **Result Processing**: Handles both success and error responses
5. **Detailed Reporting**: Creates comprehensive embed showing what was created
6. **Panel Refresh**: Updates the main panel to reflect new marathon state

**Results Embed Builder**:
```python
def _build_results_embed(self, results: Dict) -> discord.Embed:
    embed = discord.Embed(title="🚀 Marathon Start Results", color=discord.Color.green())
    if results['created_roles']:
        embed.add_field(name="✅ Roles Created", value="\n".join(f"• {r}" for r in results['created_roles']), inline=False)
    if results['created_channels']:
        embed.add_field(name="✅ Channels Created", value="\n".join(f"• {c}" for c in results['created_channels']), inline=False)
    if results['skipped_teams']:
        embed.add_field(name="⚠️ Skipped Teams", value="\n".join(f"• {t}" for t in results['skipped_teams']), inline=False)
    return embed
```

### EndMarathonButton - Resource Cleanup

```python
class EndMarathonButton(TeamButton):
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
```

**Purpose**: Safely removes all marathon-related Discord resources while preserving team data.

**Cleanup Operations**:
1. **State Validation**: Ensures marathon is actually active
2. **Resource Removal**: Delegates to `marathon_service.end_marathon()` which:
   - Removes team roles from all members
   - Deletes team channels
   - Updates marathon state in database
3. **Nothing to Clean Check**: Handles edge case where no resources exist
4. **Detailed Reporting**: Shows what was removed
5. **State Update**: Updates panel to reflect inactive marathon state

### RefreshButton - Simplified Data Sync

```python
class RefreshButton(TeamButton):
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
```

**Purpose**: Provides a simple way to sync data and refresh the panel display.

**Simplified Workflow**:
- Single method call to `panel_manager.refresh_team_panel()`
- The panel manager handles the complexity:
  - Calls `sync_database_with_discord()`
  - Rebuilds the panel embed
  - Updates the view components
  - Provides success feedback

### FetchDataButton - Server Discovery

```python
class FetchDataButton(TeamButton):
    def __init__(self, cog):
        super().__init__(cog, label="Fetch Data", style=discord.ButtonStyle.secondary, custom_id="fetch_data_button", row=1)

    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            results = await self.cog.team_manager.team_service.fetch_server_teams(interaction.guild)

            embed = discord.Embed(title="🔄 Data Fetch Results", color=discord.Color.blue())
            embed.add_field(name="Registered Teams", value=str(results['registered']), inline=True)
            embed.add_field(name="Skipped Registered Teams", value=str(results['skipped']), inline=True)

            if results['details']:
                embed.add_field(name="Details", value="\n".join(results['details']), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

            if results['registered'] > 0:
                await self.cog.panel_manager.refresh_team_panel(interaction.guild_id)
        except Exception as e:
            await self.handle_error(interaction, e)
```

**Purpose**: Discovers existing team structures in Discord and registers them in the database.

**Discovery Process**:
1. **Server Scanning**: Calls `team_service.fetch_server_teams()` which:
   - Scans for roles matching "Team X" pattern
   - Finds associated private channels
   - Extracts member lists from roles
   - Validates team structure
2. **Result Analysis**: Processes results showing:
   - How many teams were successfully registered
   - How many were skipped and why
   - Detailed explanations for skipped teams
3. **Conditional Refresh**: Only refreshes panel if new teams were found

## Individual Team Action Buttons

### DeleteMemberButton - Context-Specific Member Removal

```python
class DeleteMemberButton(TeamButton):
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
```

**Purpose**: Opens member removal modal for a specific team with validation.

**Validation Logic**:
1. **Team Existence**: Verifies team still exists (handles race conditions)
2. **Member Check**: Ensures team has members to remove
3. **Modal Trigger**: Opens `DeleteMemberModal` with team context
4. **Error Handling**: Specific handling for `TeamNotFoundError`

### EditChannelNameButton - Channel Management

```python
class EditChannelNameButton(TeamButton):
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
```

**Purpose**: Opens channel name editing modal with team context validation.

**Context Passing**: Passes `team_data` dict containing current channel name for pre-population in modal.

### ConfirmDeleteButton - Final Deletion Confirmation

```python
class ConfirmDeleteButton(TeamButton):
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
```

**Purpose**: Executes final team deletion with comprehensive resource cleanup.

**Deletion Process**:
1. **Deferred Response**: Long-running operation requiring defer
2. **Complete Deletion**: Calls `delete_team_and_resources()` which:
   - Removes team from database
   - Deletes Discord role
   - Removes Discord channel
   - Handles member role removal
3. **Success Feedback**: Clear confirmation of deletion
4. **Panel Update**: Refreshes panel to reflect changes
5. **Edge Case Handling**: Handles already-deleted teams gracefully

## Team Formation Action Buttons

### AssignMemberButton - Individual Member Assignment

```python
class AssignMemberButton(TeamButton):
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
```

**Purpose**: Initiates individual member assignment workflow by presenting unassigned members.

**Data Aggregation**:
1. **Document Retrieval**: Gets unregistered members document from database
2. **Leader/Member Merge**: Combines both leaders and members into single selection
3. **Empty State Handling**: Graceful handling when no unassigned members exist
4. **Dropdown Creation**: Creates selection interface for member assignment

### FormTeamButton - Automated Team Creation Gateway

```python
class FormTeamButton(TeamButton):
    def __init__(self, cog):
        super().__init__(cog, label="Form New Teams", style=discord.ButtonStyle.primary, custom_id="form_teams_button")

    @moderator_required
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(TeamFormationModal(self.cog))
        except Exception as e:
            await self.handle_error(interaction, e)
```

**Purpose**: Opens the team formation confirmation modal as a safety gate.

**Safety Pattern**: Uses modal as confirmation gate rather than direct execution to prevent accidental team creation.

**Modal Delegation**: The complex logic is handled in `TeamFormationModal`:
1. Requires exact confirmation text ("FORM")
2. Processes unassigned members with user_id injection
3. Runs hierarchical formation algorithm
4. Presents results for final confirmation
5. Handles batch team creation

## Button Design Patterns

### Error Handling Strategy

All buttons follow a consistent error handling pattern:

```python
try:
    # Button-specific logic
    pass
except SpecificError as e:
    # Handle specific errors with context
    await interaction.response.send_message(f"❌ {e}", ephemeral=True)
except Exception as e:
    # Fall back to centralized error handling
    await self.handle_error(interaction, e)
```

### Response Management

Buttons use different response patterns based on operation complexity:

1. **Immediate Response**: Simple operations that complete quickly
2. **Deferred Response**: Long-running operations using `defer(thinking=True)`
3. **Modal Response**: Operations requiring user input
4. **Followup Response**: Used after deferred responses

### Circular Import Avoidance

Strategic use of local imports prevents circular dependencies:

```python
from .views import SomeView # Avoid circular import
```

This pattern allows buttons to create views without creating import cycles.

### State Validation

Complex buttons validate state before proceeding:

```python
if await self.cog.team_manager.team_service.is_marathon_active(interaction.guild.id):
    return await interaction.followup.send("⚠️ Marathon is already active for this server.", ephemeral=True)
```

### Resource Management

Buttons that create or modify resources follow the pattern:
1. Validate prerequisites
2. Execute operation
3. Handle results/errors
4. Update UI state
5. Provide user feedback

This comprehensive button system provides a robust, user-friendly interface for all team management operations while maintaining consistency and reliability through centralized patterns and error handling.
