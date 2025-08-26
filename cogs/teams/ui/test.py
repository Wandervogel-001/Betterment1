import discord
from discord.ui import View, Button, Modal, TextInput
import logging
import math

# Assuming your config file is accessible
from config import (
    HUGGINGFACE_MODELS, POE_MODELS, GOOGLE_MODELS,
    DEEPSEEK_MODELS, OPENROUTER_MODELS
)

logger = logging.getLogger(__name__)

# Enhanced MODEL_MAP without emojis
MODEL_MAP = {
    "Hugging Face": {"models": HUGGINGFACE_MODELS},
    "Poe": {"models": POE_MODELS},
    "Google": {"models": GOOGLE_MODELS},
    "DeepSeek": {"models": DEEPSEEK_MODELS},
    "OpenRouter": {"models": OPENROUTER_MODELS},
}
MODELS_PER_PAGE = 10 # Reduced for better display in a code block

# --- The Modal for Final Selection ---

class ModelSelectionModal(Modal):
    def __init__(self, db, original_interaction, parent_view):
        super().__init__(title=f"Set {parent_view.current_brand} Model")
        self.db = db
        self.original_interaction = original_interaction
        self.parent_view = parent_view
        self.valid_models = parent_view.all_models_for_brand

        self.model_name_input = TextInput(
            label="Model Name",
            placeholder="Type the exact name of the model from the list",
            required=True
        )
        self.add_item(self.model_name_input)

    async def on_submit(self, interaction: discord.Interaction):
        typed_model = self.model_name_input.value.strip()

        if typed_model not in self.valid_models:
            await interaction.response.send_message(
                f"❌ Invalid model name: `{typed_model}`. Please check the spelling and try again.",
                ephemeral=True
            )
            return

        # --- Success Case ---
        # Defer the modal interaction
        await interaction.response.defer()

        # Update the database
        await self.db.set_active_ai_model(interaction.guild_id, typed_model)

        # Create the final confirmation embed
        embed = discord.Embed(
            title="Configuration Saved ✅",
            description="The active AI model for this server has been successfully updated.",
            color=discord.Color.green()
        )
        embed.add_field(name="New Active Model", value=f"```\n{typed_model}\n```", inline=False)
        embed.set_footer(text=f"Set by {interaction.user.display_name}")

        # Disable the original view and update the message
        self.parent_view.disable_all_items()
        await self.original_interaction.edit_original_response(embed=embed, view=self.parent_view)


# --- The Main View Managing the Entire Flow ---

class AIModelSelectionView(View):
    def __init__(self, db, original_interaction):
        super().__init__(timeout=300)
        self.db = db
        self.original_interaction = original_interaction

        # State Management
        self.current_stage = "category"  # 'category' or 'model'
        self.current_brand = None
        self.current_page = 0
        self.all_models_for_brand = []

    async def start(self):
        """Sends the initial message with the category view."""
        embed = self._build_category_embed()
        self._update_components()
        await self.original_interaction.response.send_message(embed=embed, view=self, ephemeral=True)

    def _build_category_embed(self):
        """Builds the embed for the provider/category selection screen."""
        embed = discord.Embed(
            title="AI Model Configuration ⚙️",
            description="Please select a provider below to view and choose a new AI model.",
            color=discord.Color.blue()
        )
        provider_list = "\n".join(MODEL_MAP.keys())
        embed.add_field(name="Providers", value=f"```\n{provider_list}\n```", inline=False)
        return embed

    def _build_model_embed(self):
        """Builds the embed for the model selection screen."""
        total_pages = math.ceil(len(self.all_models_for_brand) / MODELS_PER_PAGE)
        embed = discord.Embed(
            title=f"Configuration > {self.current_brand}",
            description="Browse the models below. Click 'Select a Model' to confirm your choice.",
            color=discord.Color.purple()
        )

        start_index = self.current_page * MODELS_PER_PAGE
        end_index = start_index + MODELS_PER_PAGE
        models_on_page = self.all_models_for_brand[start_index:end_index]

        embed.add_field(
            name="Available Models",
            value=f"```\n" + "\n".join(models_on_page) + "\n```",
            inline=False
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
        return embed

    def _update_components(self):
        """Clears and adds the correct buttons based on the current stage."""
        self.clear_items()
        if self.current_stage == "category":
            for name in MODEL_MAP.keys():
                self.add_item(Button(label=name, custom_id=f"brand_{name}"))
            self.add_item(Button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel"))

        elif self.current_stage == "model":
            total_pages = math.ceil(len(self.all_models_for_brand) / MODELS_PER_PAGE)
            # Row 1: Navigation
            prev_button = Button(label="◀️ Previous", custom_id="prev_page", disabled=self.current_page == 0)
            next_button = Button(label="Next ▶️", custom_id="next_page", disabled=self.current_page >= total_pages - 1)
            self.add_item(prev_button)
            self.add_item(next_button)
            # Row 2: Actions
            self.add_item(Button(label="Select a Model", style=discord.ButtonStyle.success, custom_id="select_model", row=1))
            self.add_item(Button(label="⬅️ Back to Providers", style=discord.ButtonStyle.secondary, custom_id="back_to_category", row=1))

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """The primary dispatcher for all component interactions."""
        # Ensure only the original user can interact
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("You cannot interact with this menu.", ephemeral=True)
            return False

        custom_id = interaction.data["custom_id"]

        # --- Stage 1: Category Selection ---
        if custom_id.startswith("brand_"):
            self.current_brand = custom_id.split("_")[1]
            self.current_stage = "model"
            self.current_page = 0
            self.all_models_for_brand = MODEL_MAP.get(self.current_brand, {}).get("models", [])

        # --- Stage 2: Model Navigation & Selection ---
        elif custom_id == "prev_page":
            if self.current_page > 0: self.current_page -= 1
        elif custom_id == "next_page":
            self.current_page += 1
        elif custom_id == "back_to_category":
            self.current_stage = "category"
        elif custom_id == "select_model":
            modal = ModelSelectionModal(self.db, self.original_interaction, self)
            await interaction.response.send_modal(modal)
            return True # Don't update the view yet, wait for modal submission

        # --- General Actions ---
        elif custom_id == "cancel":
            await self.original_interaction.edit_original_response(content="Interaction cancelled.", embed=None, view=None)
            self.stop()
            return True

        # --- Update the message based on the new state ---
        new_embed = self._build_model_embed() if self.current_stage == 'model' else self._build_category_embed()
        self._update_components()
        await interaction.response.edit_message(embed=new_embed, view=self)
        return True
