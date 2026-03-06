"""
data_core/pipeline.py

Orchestrator for full Data Core execution.

Flow:
1. Structural validation
2. Review analysis (optional, in-memory only)
3. Domain scoring
4. Data Hub generation

This module:
- Does NOT depend on context engine
- Does NOT depend on bias guard
- Does NOT persist review text
- Is fully deterministic
"""

from typing import List, Dict, Optional

from core.base_models import BaseEntity
from data_core.shared.structural_validator import StructuralValidator
from data_core.shared.review_analyzer import ReviewAnalyzer
from data_core.shared.domain_scorer import DomainScorer
from data_core.data_hub_builder import DataHubBuilder


# ============================================================
# DATA CORE PIPELINE CLASS
# ============================================================

class DataCorePipeline:

    def __init__(self):
        self.structural_validator = StructuralValidator()
        self.review_analyzer = ReviewAnalyzer()
        self.domain_scorer = DomainScorer()
        self.hub_builder = DataHubBuilder()

    # --------------------------------------------------------
    # PROCESS SINGLE ENTITY
    # --------------------------------------------------------

    def process_entity(
        self,
        entity: BaseEntity,
        reviews: Optional[List[Dict]] = None
    ) -> BaseEntity:
        """
        Full processing of a single entity.
        """

        # 1️⃣ Structural validation
        self.structural_validator.compute(entity)

        # 2️⃣ Review analysis (in-memory only)
        if reviews:
            self.review_analyzer.analyze(entity, reviews)

        # 3️⃣ Domain-specific scoring
        self.domain_scorer.compute(entity)

        entity.touch()

        return entity

    # --------------------------------------------------------
    # PROCESS MULTIPLE ENTITIES
    # --------------------------------------------------------

    def process_entities(
        self,
        entities_with_reviews: List[Dict]
    ) -> Dict:
        """
        Input format:
        [
            {
                "entity": BaseEntity,
                "reviews": [ {rating, text}, ... ]  # optional
            }
        ]
        """

        processed_entities = []

        for item in entities_with_reviews:

            entity = item.get("entity")
            reviews = item.get("reviews", None)

            processed_entity = self.process_entity(entity, reviews)

            processed_entities.append(processed_entity)

        # 4️⃣ Build Data Hub
        hub = self.hub_builder.build(processed_entities)

        return hub


# ============================================================
# SAFE EXECUTION TEST
# ============================================================

if __name__ == "__main__":

    from core.base_models import BaseEntity, Domain
    import json

    # Sample Entities
    beach = BaseEntity(
        name="Panambur Beach",
        domain=Domain.PLACES,
        category="Nature",
        subcategory="Beach",
        latitude=12.95,
        longitude=74.80,
        sources=["OSM", "TourismBoard"]
    )

    restaurant = BaseEntity(
        name="Gajalee Seafood",
        domain=Domain.FOOD,
        category="Traditional",
        subcategory="Seafood",
        latitude=12.91,
        longitude=74.85,
        sources=["OSM", "VerifiedAPI"]
    )

    beach_reviews = [
        {"rating": 5, "text": "Beautiful beach and clean!"},
        {"rating": 4, "text": "Nice sunset view."},
        {"rating": 5, "text": "Must visit place!!!"}
    ]

    restaurant_reviews = [
        {"rating": 5, "text": "Amazing seafood and service!"},
        {"rating": 4, "text": "Very authentic coastal food."},
        {"rating": 5, "text": "Highly recommend!!!"},
        {"rating": 2, "text": "Too crowded."}
    ]

    pipeline = DataCorePipeline()

    hub = pipeline.process_entities([
        {"entity": beach, "reviews": beach_reviews},
        {"entity": restaurant, "reviews": restaurant_reviews}
    ])

    print(json.dumps(hub, indent=4))
