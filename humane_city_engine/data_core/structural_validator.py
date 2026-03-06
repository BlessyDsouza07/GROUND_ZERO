"""
data_core/shared/structural_validator.py

Deterministic structural validation engine
for BaseEntity objects.

Independent of:
- Review logic
- Bias guard
- Context engine

Pure structural scoring only.
"""

from typing import List, Dict
from core.base_models import BaseEntity, Domain


# ============================================================
# SOURCE QUALITY REGISTRY (DETERMINISTIC WEIGHTS)
# ============================================================

SOURCE_WEIGHTS = {
    "OSM": 0.3,
    "Government": 0.35,
    "TourismBoard": 0.3,
    "FieldSurvey": 0.4,
    "PublicRegistry": 0.35,
    "VerifiedAPI": 0.3,
    "CommunityVerified": 0.25,
}


# ============================================================
# MAIN STRUCTURAL VALIDATOR CLASS
# ============================================================

class StructuralValidator:

    def __init__(self):
        pass

    # --------------------------------------------------------
    # Public Method
    # --------------------------------------------------------

    def compute(self, entity: BaseEntity) -> float:
        """
        Computes structural authenticity score.
        """

        entity.validate()

        source_score = self._compute_source_score(entity.sources)
        geo_score = self._compute_geo_score(entity)
        metadata_score = self._compute_metadata_score(entity)
        domain_score = self._compute_domain_requirements(entity)

        # Weighted deterministic formula
        final_score = (
            source_score * 0.4 +
            geo_score * 0.2 +
            metadata_score * 0.2 +
            domain_score * 0.2
        )

        final_score = round(min(final_score, 1.0), 3)

        entity.update_structural_score(final_score)

        entity.decision_trace.append(
            f"Structural components → "
            f"source:{source_score}, geo:{geo_score}, "
            f"metadata:{metadata_score}, domain:{domain_score}"
        )

        return final_score

    # --------------------------------------------------------
    # SOURCE SCORE
    # --------------------------------------------------------

    def _compute_source_score(self, sources: List[str]) -> float:
        if not sources:
            return 0.0

        weight_sum = 0.0

        for source in sources:
            weight_sum += SOURCE_WEIGHTS.get(source, 0.1)

        # Normalize (max theoretical 1.0+ but cap at 1)
        return round(min(weight_sum, 1.0), 3)

    # --------------------------------------------------------
    # GEO VALIDATION SCORE
    # --------------------------------------------------------

    def _compute_geo_score(self, entity: BaseEntity) -> float:
        if entity.latitude and entity.longitude:
            return 1.0
        return 0.0

    # --------------------------------------------------------
    # METADATA COMPLETENESS
    # --------------------------------------------------------

    def _compute_metadata_score(self, entity: BaseEntity) -> float:
        score = 0.0

        if entity.category:
            score += 0.3

        if entity.subcategory:
            score += 0.3

        if entity.name:
            score += 0.2

        if entity.sources:
            score += 0.2

        return round(min(score, 1.0), 3)

    # --------------------------------------------------------
    # DOMAIN-SPECIFIC STRUCTURAL RULES
    # --------------------------------------------------------

    def _compute_domain_requirements(self, entity: BaseEntity) -> float:
        """
        Ensures domain-specific minimal structural validity.
        """

        if entity.domain == Domain.PLACES:
            return 1.0

        if entity.domain == Domain.FOOD:
            # Food entities must have at least 1 strong source
            return 1.0 if len(entity.sources) >= 1 else 0.5

        if entity.domain == Domain.CULTURE:
            # Cultural events ideally need multi-source
            return 1.0 if len(entity.sources) >= 2 else 0.6

        if entity.domain == Domain.ACTIVITIES:
            return 1.0 if len(entity.sources) >= 1 else 0.7

        if entity.domain == Domain.TRAVEL_INTEL:
            return 1.0

        if entity.domain == Domain.SAFETY_SUPPORT:
            return 1.0

        return 0.8


# ============================================================
# SAFE EXECUTION TEST
# ============================================================

if __name__ == "__main__":

    from core.base_models import BaseEntity, Domain

    entity = BaseEntity(
        name="Panambur Beach",
        domain=Domain.PLACES,
        category="Nature",
        subcategory="Beach",
        latitude=12.95,
        longitude=74.80,
        sources=["OSM", "TourismBoard"]
    )

    validator = StructuralValidator()
    score = validator.compute(entity)

    print("Structural Score:", score)
    print(entity.to_dict())
