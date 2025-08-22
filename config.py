import os
from dotenv import load_dotenv

load_dotenv()

# --- Core Bot Settings ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "Betterment")

# --- AI Model Configuration ---

# Credentials
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
POE_API_KEY = os.getenv("POE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Model Lists
HUGGINGFACE_MODELS = [
    "deepseek-ai/DeepSeek-V3-0324",
    # Add other Hugging Face models here
]

POE_MODELS = [
    "Qwen2.5_7B_Free",
    "Gemma-2-9b-it",
    # Add other Poe models here
]

GOOGLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    # Add other Google models here
]

# Active Model Selection (change this value to switch models)
ACTIVE_AI_MODEL = os.getenv("ACTIVE_AI_MODEL", "gemini-1.5-flash")

AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", 30))


# --- Team & Server Configuration ---
REACTION_EMOJI=os.getenv("REACTION_EMOJI", "✅")
COMMUNICATION_CHANNEL_ID = int(os.getenv("COMMUNICATION_CHANNEL_ID", 0))
MODERATOR_ROLES = [role.strip() for role in os.getenv("MODERATOR_ROLES", "").split(",")]
EXCLUDED_TEAM_ROLES = [role.strip() for role in os.getenv("EXCLUDED_TEAM_ROLES", "").split(",")]
MAX_TEAM_SIZE = int(os.getenv("MAX_TEAM_SIZE", 12))
MAX_LEADERS_PER_TEAM = int(os.getenv("MAX_LEADERS_PER_TEAM", 2))

# --- Database Collection Names ---
TEAMS_COLLECTION =os.getenv("TEAMS_COLLECTION", "teams")
TEAM_PANELS_COLLECTION =os.getenv("TEAM_PANELS_COLLECTION", "team_panels")
UNREGISTERED_MEMBERS_COLLECTION =os.getenv("UNREGISTERED_MEMBERS_COLLECTION", "unregistered_members")
MARATHON_STATE_COLLECTION =os.getenv("MARATHON_STATE_COLLECTION", "marathon_state")

# --- Scoring Engine Parameters ---
PERFECT_MATCH_THRESHOLD=float(os.getenv("PERFECT_MATCH_THRESHOLD", 0.95))
PERFECT_MATCH_BONUS=float(os.getenv("PERFECT_MATCH_BONUS", 0.25))
MID_MATCH_THRESHOLD_LOW=float(os.getenv("MID_MATCH_THRESHOLD_LOW", 0.4))
MID_MATCH_THRESHOLD_HIGH=float(os.getenv("MID_MATCH_THRESHOLD_HIGH", 0.6))
MID_MATCH_BONUS_INCREMENT=float(os.getenv("MID_MATCH_BONUS_INCREMENT", 0.01))
MID_MATCH_BONUS_CAP=float(os.getenv("MID_MATCH_BONUS_CAP", 0.05))
MIN_CATEGORY_SCORE_THRESHOLD = float(os.getenv("MIN_CATEGORY_SCORE_THRESHOLD", 0.1))
MIN_TIMEZONE_SCORE_THRESHOLD = float(os.getenv("MIN_TIMEZONE_SCORE_THRESHOLD", 0.55))
