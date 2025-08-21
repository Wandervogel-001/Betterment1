import re
from typing import Dict, Set, List, Tuple
from collections import defaultdict
from ..services.base_domain_keywords import base_domain_keywords

class CategoryMatcher:
    """
    An intelligent engine to find and rank relevant categories for a given text.

    It works by calculating a "specificity score" for each keyword and then
    scoring potential categories based on the keywords found in the text.
    """

    def __init__(self):
        """
        Initializes the matcher by pre-calculating keyword-to-category mappings
        and specificity scores for each keyword.
        """
        self.keyword_map: Dict[str, Set[str]] = defaultdict(set)
        self.specificity_scores: Dict[str, float] = {}
        self._process_keywords()

    def _process_keywords(self):
        """
        Processes the keyword dictionary to build the keyword map and calculate
        specificity scores.
        """
        keyword_category_counts = defaultdict(int)

        # First pass: Build the keyword_map and count category occurrences for each keyword
        for domain, sub_categories in base_domain_keywords.items():
            for sub_category, keywords in sub_categories.items():
                category_string = f"{domain}:{sub_category}"
                for keyword in keywords:
                    k_lower = keyword.lower()
                    self.keyword_map[k_lower].add(category_string)
                    keyword_category_counts[k_lower] += 1

        # Second pass: Calculate the specificity score for each keyword
        # Score is inversely proportional to how common it is across categories.
        for keyword, count in keyword_category_counts.items():
            self.specificity_scores[keyword] = 1.0 / count

    def get_scored_categories(self, text: str) -> Dict[str, float]:
        """
        Finds all matching categories for a text and calculates a relevance score for each.

        Args:
            text (str): The input text (e.g., a user's goal or habit).

        Returns:
            Dict[str, float]: A dictionary mapping each found category to its total score.
        """
        if not text or not isinstance(text, str):
            return {}

        text_lower = text.lower()
        category_scores = defaultdict(float)

        # Find all unique keywords present in the text
        matched_keywords = set()
        for keyword in self.keyword_map.keys():
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_lower):
                matched_keywords.add(keyword)

        # For each matched keyword, add its specificity score to all its associated categories
        for keyword in matched_keywords:
            specificity_score = self.specificity_scores.get(keyword, 0)
            associated_categories = self.keyword_map.get(keyword, set())
            for category in associated_categories:
                category_scores[category] += specificity_score

        return category_scores

    def get_top_categories(self, text: str, n: int = 2) -> List[Tuple[str, float]]:
        """
        A user-friendly method to get the most relevant N categories for a text.

        Args:
            text (str): The input text (e.g., a user's goal or habit).
            n (int): The number of top categories to return.

        Returns:
            List[Tuple[str, float]]: A sorted list of the top N (category, score) tuples.
        """
        scored_categories = self.get_scored_categories(text)
        if not scored_categories:
            return []

        # Sort the categories by score in descending order
        sorted_cats = sorted(scored_categories.items(), key=lambda item: item[1], reverse=True)

        return sorted_cats[:n]

if __name__ == "__main__":
  matcher = CategoryMatcher()

  # --- Test 1 ---
  text1 = "My main goal is to win a local coding competition."
  top_categories1 = matcher.get_top_categories(text1, n=2)
  print(f"Top categories for '{text1}': {top_categories1}")

  # --- Test 2 ---
  text2 = "I want to improve my gym endurance and squat form."
  top_categories2 = matcher.get_top_categories(text2, n=2)
  print(f"Top categories for '{text2}': {top_categories2}")
