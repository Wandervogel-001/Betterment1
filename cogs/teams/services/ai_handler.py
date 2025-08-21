import json
import logging
import asyncio
import numpy as np
import tenacity
import re
from typing import Optional, Dict, List, Any
from huggingface_hub import InferenceClient
from config import HUGGINGFACE_API_TOKEN, HUGGINGFACE_MODEL
from ..utils.timezone_utils import TimezoneProcessor

logger = logging.getLogger(__name__)

# --- SBERT Semantic Similarity Implementation ---
_model_cache: Optional[Any] = None
_model_load_lock = asyncio.Lock()

class SimilarityCalculator:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', device: str = 'cpu'):
        self.model_name = model_name
        self.device = device
        self.model = None
    async def _load_model(self):
        global _model_cache
        async with _model_load_lock:
            if _model_cache is None:
                logger.info(f"Loading SentenceTransformer model: {self.model_name}...")
                try:
                    from sentence_transformers import SentenceTransformer
                    _model_cache = SentenceTransformer(self.model_name, device=self.device)
                    _model_cache.eval()
                except Exception as e:
                    logger.error(f"Failed to load SBERT model '{self.model_name}'. Error: {e}", exc_info=True)
                    _model_cache = e
                    raise
            if isinstance(_model_cache, Exception):
                raise RuntimeError("SBERT model is in a failed state.") from _model_cache
            self.model = _model_cache
    def _calculate_similarity(self, list1: List[str], list2: List[str]) -> np.ndarray:
        if not list1 or not list2: return np.array([[]])
        try:
            import torch
            from sentence_transformers import util
            with torch.no_grad():
                embeddings1 = self.model.encode(list1, convert_to_tensor=True, device=self.device)
                embeddings2 = self.model.encode(list2, convert_to_tensor=True, device=self.device)
                cosine_scores = util.cos_sim(embeddings1, embeddings2)
            return cosine_scores.cpu().numpy()
        except Exception as e:
            logger.error(f"Error during similarity calculation: {e}", exc_info=True)
            return np.zeros((len(list1), len(list2)))
    async def compare(self, list_a: List[str], list_b: List[str]) -> np.ndarray:
        if self.model is None: await self._load_model()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._calculate_similarity, list_a, list_b)

class AIHandlerError(Exception): pass
class AIExtractionError(AIHandlerError): pass

class AIHandler:
    """Handles AI operations: profile extraction and semantic comparison."""

    def __init__(self):
        if not HUGGINGFACE_API_TOKEN:
            raise ValueError("HUGGINGFACE_API_TOKEN environment variable not set.")
        self.client = InferenceClient(token=HUGGINGFACE_API_TOKEN)
        self.model_name = HUGGINGFACE_MODEL
        self.similarity_calculator = SimilarityCalculator()

    def _build_profile_prompt(self, profile_text: str) -> str:
        """Builds the dynamic prompt for the AI model."""
        # Dynamically generate the list of timezones from the single source of truth.
        valid_timezones = ", ".join(f'"{tz}"' for tz in TimezoneProcessor.TIMEZONE_MAP.keys())

        return f"""
        You are an AI assistant that extracts structured data from user-written profile introductions.
        Return ONLY a valid, compact JSON object with the following fields (omit any missing fields):

        - "timezone": A valid timezone abbreviation from this list ONLY: [{valid_timezones}]. Infer the most likely abbreviation from user input (e.g., "Central European" -> "CET").
        - "habits": A list of strings describing regular actions or hobbies.
        - "goals": A list of strings describing user goals or aspirations.
        - "category": A dictionary mapping a domain to its sub-domains based on the user's goals and habits. Use only sub-domains from this fixed structure:
            - "health_and_fitness": ["physical_health", "mental_wellness", "nutrition_and_sleep"]
            - "technology_and_computing": ["software_and_web_dev", "emerging_tech_and_ai", "infrastructure_and_security"]
            - "business_and_finance": ["business_strategy", "personal_finance_and_investing", "career_and_economics"]
            - "education_and_learning": ["academic_and_exam_prep", "language_and_communication", "personal_growth"]
            - "creative_arts_and_hobbies": ["arts_and_creation", "performance_and_play", "collection_and_curation"]
            - "lifestyle_community_and_adventure": ["home_and_personal_life", "social_and_community", "travel_and_adventure"]
            - "science_and_research": ["scientific_fields", "research_process_and_tools"]

        Do not add comments or explanations.

        ### User Profile Text:
        {profile_text.strip()}
        """

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def extract_profile_data(self, text: str) -> Optional[Dict]:
        """Extracts structured data from profile text using the AI model."""
        if len(text) < 20:
            logger.warning("Profile text too short for meaningful extraction.")
            return None

        prompt = self._build_profile_prompt(text)
        try:
            loop = asyncio.get_event_loop()
            completion = await loop.run_in_executor(
                None,
                lambda: self.client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model_name,
                    temperature=0.2,
                    max_tokens=512
                )
            )
            raw_response = completion.choices[0].message.content.strip()
            return self._parse_ai_response(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI JSON response: {e}. Raw response: '{raw_response}'")
            raise AIExtractionError("Failed to parse AI response.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during profile extraction: {e}")
            raise AIExtractionError(f"Profile extraction failed: {str(e)}") from e

    def _parse_ai_response(self, raw: str) -> Dict:
        """Cleans and parses the JSON response from the AI."""
        # Remove markdown code blocks if present
        cleaned = re.sub(r"```json\n?|```", "", raw).strip()
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise json.JSONDecodeError("AI response was not a valid JSON object.", cleaned, 0)
        # Filter out empty values for cleaner data
        return {k: v for k, v in data.items() if v}

    async def compare_goals(self, goals1: List[str], goals2: List[str]) -> np.ndarray:
        """Compares two lists of goals for semantic similarity."""
        return await self.similarity_calculator.compare(goals1, goals2)

    async def compare_habits(self, habits1: List[str], habits2: List[str]) -> np.ndarray:
        """Compares two lists of habits for semantic similarity."""
        return await self.similarity_calculator.compare(habits1, habits2)
