"""
data_core/pipeline.py

Orchestrator for full Data Core execution.

Flow:
1. Structural validation
2. Review analysis (optional, in-memory only)
3. Domain scoring
4. Data Hub generation
"""

from typing import List, Dict, Optional

from core.base_models import BaseEntity

# Correct import paths - files live directly in data_core/, not data_core/shared/
from data_core.structural_validator import StructuralValidator
from data_core.review_analyzer import ReviewAnalyzer
from data_core.domain_scorer import DomainScorer
from data_core.data_hub_builder import DataHubBuilder


class DataCorePipeline:

    def __init__(self):
        self.structural_validator = StructuralValidator()
        self.review_analyzer = ReviewAnalyzer()
        self.domain_scorer = DomainScorer()
        self.hub_builder = DataHubBuilder()

    def process_entity(
        self,
        entity: BaseEntity,
        reviews: Optional[List[Dict]] = None
    ) -> BaseEntity:
        """Full processing of a single entity."""

        self.structural_validator.compute(entity)

        if reviews:
            self.review_analyzer.analyze(entity, reviews)

        self.domain_scorer.compute(entity)

        entity.touch()

        return entity

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

        hub = self.hub_builder.build(processed_entities)

        return hub

    def run(self, entities: List[BaseEntity]) -> List[BaseEntity]:
        """
        Run structural validation + domain scoring on a list of entities.
        Used by city_bootstrap.py.
        """

        processed = []

        for entity in entities:

            try:
                self.structural_validator.compute(entity)
                self.domain_scorer.compute(entity)
                entity.touch()
                processed.append(entity)

            except Exception as e:
                print(f"Pipeline error for {entity.name}: {e}")

        return processed


if __name__ == "__main__":

    from core.base_models import BaseEntity, Domain
    import json

    beach = BaseEntity(
        name="Panambur Beach",
        domain=Domain.PLACES,
        category="Nature",
        subcategory="Beach",
        latitude=12.95,
        longitude=74.80,
        sources=["OSM", "TourismBoard"]
    )

    pipeline = DataCorePipeline()

    hub = pipeline.process_entities([
        {"entity": beach, "reviews": [
            {"rating": 5, "text": "Beautiful beach and clean!"},
            {"rating": 4, "text": "Nice sunset view."},
        ]}
    ])

    print(json.dumps(hub, indent=4))