import logging
import re
from typing import Dict, Set, List
import numpy as np
from ..services.category_matcher import CategoryMatcher
from ..utils.timezone_utils import TimezoneProcessor
from config import (
    PERFECT_MATCH_THRESHOLD, PERFECT_MATCH_BONUS, MID_MATCH_THRESHOLD_LOW,
    MID_MATCH_THRESHOLD_HIGH, MID_MATCH_BONUS_INCREMENT, MID_MATCH_BONUS_CAP
)

logger = logging.getLogger(__name__)

class TeamScoringEngine:
    """Provides tools for calculating compatibility between members and teams."""

    def __init__(self, ai_handler):
        self.ai_handler = ai_handler
        self.tz_processor = TimezoneProcessor()
        self.category_matcher = CategoryMatcher()

    def get_member_categories(self, profile_data: Dict) -> Set[str]:
        """
        Gets member categories, first from structured data, then by scanning text as a fallback.
        This method is now simplified by removing the private helper.
        """
        # 1. Prioritize structured data from the AI extraction
        if isinstance(profile_data.get("category"), dict):
            category_set = {f"{domain}:{sub}" for domain, subs in profile_data["category"].items() for sub in subs}
            if category_set:
                return category_set

        # 2. Fallback to text-based matching if structured data is absent
        logger.debug("No structured categories found, falling back to text-based matching.")
        fallback_categories = set()
        for item_type in ["goals", "habits"]:
            for item in profile_data.get(item_type, []):
                # Get the top 2 matching categories for each goal/habit
                for cat, _ in self.category_matcher.get_top_categories(item, n=2):
                    fallback_categories.add(cat)
        return fallback_categories

    def _calculate_categorical_score(self, categories1: Set[str], categories2: Set[str]) -> float:
        """Calculates a score based on shared domains and sub-categories."""
        if not categories1 or not categories2: return 0.0

        domains1 = {cat.split(':')[0] for cat in categories1}
        domains2 = {cat.split(':')[0] for cat in categories2}

        shared_sub_score = len(categories1 & categories2) / min(len(categories1), len(categories2))
        shared_dom_score = len(domains1 & domains2) / min(len(domains1), len(domains2))

        # Weighted average: 60% for specific sub-category matches, 40% for broader domain matches.
        return (0.6 * shared_sub_score) + (0.4 * shared_dom_score)

    def _apply_similarity_bonuses(self, matrix: np.ndarray) -> float:
        """Calculates a final score from a similarity matrix with bonuses for strong matches."""
        if matrix.size == 0: return 0.0

        base_similarity = np.mean(matrix)

        # Add a significant bonus for each "perfect" match
        perfect_matches = np.sum(matrix >= PERFECT_MATCH_THRESHOLD)
        bonus = perfect_matches * PERFECT_MATCH_BONUS

        # Add a small, capped bonus for "mid-range" matches
        mid_matches = np.sum((matrix >= MID_MATCH_THRESHOLD_LOW) & (matrix < MID_MATCH_THRESHOLD_HIGH))
        bonus += min(MID_MATCH_BONUS_CAP, mid_matches * MID_MATCH_BONUS_INCREMENT)

        return min(1.0, base_similarity + bonus)

    async def calculate_semantic_compatibility(self, profile1: Dict, profile2: Dict) -> float:
        """Calculates compatibility based on the semantic similarity of goals and habits."""
        if not profile1 or not profile2: return 0.0

        goals1, goals2 = profile1.get("goals", []), profile2.get("goals", [])
        habits1, habits2 = profile1.get("habits", []), profile2.get("habits", [])

        scores, weights = [], []
        if goals1 and goals2:
            goals_matrix = await self.ai_handler.compare_goals(goals1, goals2)
            scores.append(self._apply_similarity_bonuses(goals_matrix))
            weights.append(1.0) # Weight goals normally

        if habits1 and habits2:
            habits_matrix = await self.ai_handler.compare_habits(habits1, habits2)
            scores.append(self._apply_similarity_bonuses(habits_matrix))
            weights.append(1.0) # Weight habits normally

        if not scores: return 0.0
        return np.average(scores, weights=weights)

    def calculate_member_team_fit(self, member_profile: Dict, team_leaders: List[Dict]) -> Dict[str, float]:
        """
        Calculates the average timezone and category fit between a member and team leaders.
        This new method centralizes logic previously duplicated in team_formation.py.
        """
        if not team_leaders:
            return {"tz_score": 0.0, "cat_score": 0.0}

        member_tz_offset = self.tz_processor.parse_to_utc_offset(member_profile.get("timezone"))
        member_cats = self.get_member_categories(member_profile)

        tz_scores, cat_scores = [], []
        for leader in team_leaders:
            leader_profile = leader.get("profile_data", {})
            leader_tz_offset = self.tz_processor.parse_to_utc_offset(leader_profile.get("timezone"))
            leader_cats = self.get_member_categories(leader_profile)

            tz_scores.append(self.tz_processor.calculate_compatibility(member_tz_offset, leader_tz_offset))
            cat_scores.append(self._calculate_categorical_score(member_cats, leader_cats))

        return {
            "tz_score": np.mean(tz_scores) if tz_scores else 0.0,
            "cat_score": np.mean(cat_scores) if cat_scores else 0.0
        }
