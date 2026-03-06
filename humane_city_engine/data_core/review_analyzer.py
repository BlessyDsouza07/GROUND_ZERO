"""
data_core/shared/review_analyzer.py

Deterministic in-memory review analysis engine.

Rules:
- No review persistence
- No reviewer storage
- Only derived metrics saved
- Fully explainable scoring
"""

import statistics
import re
from typing import List, Dict
from core.base_models import BaseEntity


# ============================================================
# CONFIGURABLE THRESHOLDS
# ============================================================

PROMO_KEYWORDS = [
    "best ever",
    "must visit",
    "highly recommend",
    "limited offer",
    "discount",
    "offer",
    "contact",
    "call now",
    "guaranteed"
]

MIN_REVIEW_LENGTH = 10


# ============================================================
# REVIEW ANALYZER CLASS
# ============================================================

class ReviewAnalyzer:

    def __init__(self):
        pass

    # --------------------------------------------------------
    # PUBLIC METHOD
    # --------------------------------------------------------

    def analyze(self, entity: BaseEntity, reviews: List[Dict]) -> None:
        """
        Analyze reviews in-memory and update entity.
        """

        if not reviews:
            entity.decision_trace.append("No reviews provided.")
            return

        ratings = []
        short_reviews = 0
        promo_reviews = 0
        punctuation_heavy = 0

        for r in reviews:
            rating = r.get("rating", 0)
            text = r.get("text", "")

            ratings.append(rating)

            # Short review detection
            if len(text.strip()) < MIN_REVIEW_LENGTH:
                short_reviews += 1

            # Promotional keyword detection
            if self._contains_promo_language(text):
                promo_reviews += 1

            # Excess punctuation detection
            if text.count("!") > 3:
                punctuation_heavy += 1

        total_reviews = len(reviews)

        avg_rating = statistics.mean(ratings)
        rating_variance = statistics.pvariance(ratings) if total_reviews > 1 else 0.0

        fake_ratio = short_reviews / total_reviews
        promo_ratio = promo_reviews / total_reviews
        punctuation_ratio = punctuation_heavy / total_reviews

        anomaly_signal = self._compute_anomaly_signal(ratings)

        # Deterministic Review Score Formula
        review_score = (
            (avg_rating / 5.0) *
            (1 - fake_ratio) *
            (1 - promo_ratio) *
            (1 - anomaly_signal)
        )

        review_score = round(max(0.0, min(review_score, 1.0)), 3)

        # Update entity safely
        entity.update_review_score(review_score)

        entity.derived_signals.review_score = review_score
        entity.derived_signals.fake_ratio = round(fake_ratio, 3)
        entity.derived_signals.stability_index = round(1 - rating_variance, 3)
        entity.derived_signals.crowd_index = round(total_reviews / 100, 3)

        entity.decision_trace.append(
            f"Review analysis → avg:{round(avg_rating,2)}, "
            f"fake_ratio:{round(fake_ratio,2)}, "
            f"promo_ratio:{round(promo_ratio,2)}, "
            f"anomaly:{round(anomaly_signal,2)}"
        )

        # Explicit cleanup (ensure no review retention)
        reviews.clear()

    # --------------------------------------------------------
    # PROMO LANGUAGE DETECTION
    # --------------------------------------------------------

    def _contains_promo_language(self, text: str) -> bool:
        text_lower = text.lower()

        for keyword in PROMO_KEYWORDS:
            if keyword in text_lower:
                return True

        return False

    # --------------------------------------------------------
    # ANOMALY DETECTION
    # --------------------------------------------------------

    def _compute_anomaly_signal(self, ratings: List[int]) -> float:
        """
        Detect suspicious rating distributions.
        Example: 90% 5-star pattern.
        """

        total = len(ratings)
        if total == 0:
            return 0.0

        five_star_count = ratings.count(5)
        ratio = five_star_count / total

        if ratio > 0.9:
            return 0.5  # moderate anomaly penalty

        return 0.0


# ============================================================
# SAFE EXECUTION TEST
# ============================================================

if __name__ == "__main__":

    from core.base_models import BaseEntity, Domain

    entity = BaseEntity(
        name="Test Restaurant",
        domain=Domain.FOOD,
        category="Traditional",
        subcategory="Seafood",
        latitude=12.91,
        longitude=74.85,
        sources=["OSM", "VerifiedAPI"]
    )

    reviews = [
        {"rating": 5, "text": "Amazing food!!! Must visit!!!"},
        {"rating": 5, "text": "Best ever"},
        {"rating": 4, "text": "Very good seafood and service."},
        {"rating": 5, "text": "Highly recommend this place"},
        {"rating": 3, "text": "Okay experience."}
    ]

    analyzer = ReviewAnalyzer()
    analyzer.analyze(entity, reviews)

    print(entity.to_dict())
