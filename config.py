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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Model Lists
HUGGINGFACE_MODELS = [
  "deepseek-ai/DeepSeek-V3.1-Base",
  "deepseek-ai/DeepSeek-V3.1",
  "deepseek-ai/DeepSeek-V3-0324",
  "deepseek-ai/DeepSeek-R1",
  "openai/gpt-oss-120b",
  "openai/gpt-oss-20b",
]

POE_MODELS = [
  # --- Free Teirs Gets 3000 Points per day ---
  # --- by @siliconclouds ---
  "Qwen2.5_7B_Free",
  "Qwen2.5-72B-Instruct"
  "Qwen2.5-Coder-32B-I",
  "Qwen2-VL-72B-I",
  "QwQ-32B-Preview",
  "DeepSeek2.5",
  "DeepSeek-VL2",
  "GLM4-9B",
  # --- by @Poe ---
  "Assistant", # 7 points/message ~Varibale
  # --- by @oratrice ---
  "Gemma-2-9b-it", # 5 points/message
  # --- by @openai ---
  "GPT-5-nano", # 6 points/message
  "GPT-4.1-nano", # 6 points/message
  "GPT-4o-mini", # 9 points/message
  "GPT-3.5-Turbo-Instruct", # 10 points/message
  "GPT-3.5-Turbo", # 11 points/message
  "GPT-3.5-Turbo-Raw", # 12 points/message
  "GPT-4.1-mini", # 25 points/message
  "GPT-5-mini", # 26 points/message
  "GPT-4o-Aug", # 117 points/message
  "GPT-5-Chat", # 130 points/message
  "o3-mini", # 202 points/message
  "GPT-4o", # 224 points/message
  "GPT-4.1", # 226 points/message
  "o4-mini", # 248 points/message
  "GPT-5", # 251 points/message
  "ChatGPT-4o-Latest", # 337 points/message
  "o1-mini", # 337 points/message
  "GPT-4-Turbo", # 378 points/message
]

GOOGLE_MODELS = [
  "gemini-1.5-flash", # 1000 Requests Per Minute, Unlimited Requests Per Day
  "gemini-2.5-flash", # 5 Requests Per Minute, 500 Requests Per Day
  "gemini-1.5-pro", # 5 Requests Per Minute, 25 Requests Per Day
  "gemini-2.5-pro", # 5 Requests Per Minute, 25 Requests Per Day
]

DEEPSEEK_MODELS = [
  "deepseek-chat",
  "deepseek-coder",
]

OPENROUTER_MODELS = [
  "openai/gpt-oss-20b:free",
  "qwen/qwen3-coder:free",
  "deepseek/deepseek-r1-0528-qwen3-8b:free",
  "qwen/qwen2.5-vl-32b-instruct:free",
  "qwen/qwq-32b:free",
  "qwen/qwen-2.5-coder-32b-instruct:free",
  "google/gemma-3n-e2b-it:free",
  "google/gemma-3-27b-it:free",
  "google/gemini-2.0-flash-exp:free",
  "deepseek/deepseek-r1:free",
  "deepseek/deepseek-chat-v3-0324:free",
  "mistralai/mistral-small-3.2-24b-instruct:free",
  "mistralai/mistral-small-24b-instruct-2501:free",
  "mistralai/mistral-7b-instruct:free",
]

# Default model if none is set in the server's settings
DEFAULT_AI_MODEL = os.getenv("DEFAULT_AI_MODEL", "gemini-2.5-flash")

AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", 30))


# --- Team & Server Configuration ---
REACTION_EMOJI=os.getenv("REACTION_EMOJI", "✅")
COMMUNICATION_CHANNEL_ID = int(os.getenv("COMMUNICATION_CHANNEL_ID", 0))
MODERATOR_ROLES = [role.strip() for role in os.getenv("MODERATOR_ROLES", "").split(",")]
EXCLUDED_TEAM_ROLES = [role.strip() for role in os.getenv("EXCLUDED_TEAM_ROLES", "").split(",")]
MAX_TEAM_SIZE = int(os.getenv("MAX_TEAM_SIZE", 12))
MAX_LEADERS_PER_TEAM = int(os.getenv("MAX_LEADERS_PER_TEAM", 2))

# --- Database Collection Names ---
SETTINGS_COLLECTION=os.getenv("SETTINGS_COLLECTION", "settings")
TEAMS_COLLECTION =os.getenv("TEAMS_COLLECTION ", "teams")
UNREGISTERED_MEMBERS_COLLECTION=os.getenv("UNREGISTERED_MEMBERS_COLLECTION", "unregistered_members")

# --- Scoring Engine Parameters ---
PERFECT_MATCH_THRESHOLD=float(os.getenv("PERFECT_MATCH_THRESHOLD", 0.95))
PERFECT_MATCH_BONUS=float(os.getenv("PERFECT_MATCH_BONUS", 0.25))
MID_MATCH_THRESHOLD_LOW=float(os.getenv("MID_MATCH_THRESHOLD_LOW", 0.4))
MID_MATCH_THRESHOLD_HIGH=float(os.getenv("MID_MATCH_THRESHOLD_HIGH", 0.6))
MID_MATCH_BONUS_INCREMENT=float(os.getenv("MID_MATCH_BONUS_INCREMENT", 0.01))
MID_MATCH_BONUS_CAP=float(os.getenv("MID_MATCH_BONUS_CAP", 0.05))
MIN_CATEGORY_SCORE_THRESHOLD = float(os.getenv("MIN_CATEGORY_SCORE_THRESHOLD", 0.1))
MIN_TIMEZONE_SCORE_THRESHOLD = float(os.getenv("MIN_TIMEZONE_SCORE_THRESHOLD", 0.55))
