"""
data_core/data_hub_builder.py

Final Data Hub generator for 6-domain City Intelligence System.

Responsibilities:
- Accept processed BaseEntity objects
- Rank per domain
- Apply minimum authenticity threshold
- Output structured JSON hub
"""

import json
from typing import List, Dict
from core.base_models import BaseEntity, Domain


# ============================================================
# CONFIGURATION
# ============================================================

MIN_AUTHENTICITY_THRESHOLD = 0.55


# ============================================================
# DATA HUB BUILDER
# ============================================================

class DataHubBuilder:

    def __init__(self):
        pass

    # --------------------------------------------------------
    # BUILD HUB
    # --------------------------------------------------------

    def build(self, entities: List[BaseEntity]) -> Dict:
        """
        Returns structured hub grouped by domain.
        """

        domain_groups = self._group_by_domain(entities)

        hub = {}

        for domain, items in domain_groups.items():
            ranked = self._rank_entities(items)

            hub[domain.value] = [
                self._serialize_entity(entity, rank + 1)
                for rank, entity in enumerate(ranked)
            ]

        return hub

    # --------------------------------------------------------
    # SAVE TO FILE
    # --------------------------------------------------------

    def save(self, hub: Dict, file_path: str = "data_hub.json"):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(hub, f, indent=4)

    # --------------------------------------------------------
    # GROUP BY DOMAIN
    # --------------------------------------------------------

    def _group_by_domain(self, entities: List[BaseEntity]) -> Dict:
        groups = {}

        for entity in entities:

            if entity.final_authenticity_score < MIN_AUTHENTICITY_THRESHOLD:
                continue

            domain = entity.domain

            if domain not in groups:
                groups[domain] = []

            groups[domain].append(entity)

        return groups

    # --------------------------------------------------------
    # RANKING
    # --------------------------------------------------------

    def _rank_entities(self, entities: List[BaseEntity]) -> List[BaseEntity]:
        return sorted(
            entities,
            key=lambda e: e.final_authenticity_score,
            reverse=True
        )

    # --------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------

    def _serialize_entity(self, entity: BaseEntity, rank: int) -> Dict:
        return {
            "rank": rank,
            "entity_id": entity.entity_id,
            "name": entity.name,
            "domain": entity.domain.value,
            "category": entity.category,
            "subcategory": entity.subcategory,
            "coordinates": {
                "latitude": entity.latitude,
                "longitude": entity.longitude
            },
            "authenticity_score": entity.final_authenticity_score,
            "grade": entity.grade.value,
            "derived_signals": entity.derived_signals.to_dict(),
            "decision_trace": entity.decision_trace,
            "created_at": entity.created_at.isoformat(),
            "last_updated": entity.last_updated.isoformat()
        }


# ============================================================
# SAFE EXECUTION TEST
# ============================================================

if __name__ == "__main__":

    from core.base_models import BaseEntity, Domain
    from data_core.shared.structural_validator import StructuralValidator
    from data_core.shared.review_analyzer import ReviewAnalyzer
    from data_core.shared.domain_scorer import DomainScorer

    # Create sample entity
    entity = BaseEntity(
        name="Panambur Beach",
        domain=Domain.PLACES,
        category="Nature",
        subcategory="Beach",
        latitude=12.95,
        longitude=74.80,
        sources=["OSM", "TourismBoard"]
    )

    # Structural
    structural = StructuralValidator()
    structural.compute(entity)

    # Reviews
    reviews = [
        {"rating": 5, "text": "Amazing beach and very clean!"},
        {"rating": 4, "text": "Good place for sunset."},
        {"rating": 5, "text": "Must visit!!!"},
    ]

    review_engine = ReviewAnalyzer()
    review_engine.analyze(entity, reviews)

    # Domain score
    scorer = DomainScorer()
    scorer.compute(entity)

    # Build hub
    builder = DataHubBuilder()
    hub = builder.build([entity])

    print(json.dumps(hub, indent=4))
