"""
data_core/shared/domain_scorer.py

Domain-specific authenticity scoring engine.

Combines:
- Structural score
- Review score
- Derived domain signals

Outputs:
- Final authenticity score
- Grade assignment
- Explainability trace
"""

from core.base_models import BaseEntity, Domain


# ============================================================
# DOMAIN WEIGHT CONFIGURATION
# ============================================================

DOMAIN_WEIGHTS = {
    Domain.PLACES: {
        "structural": 0.6,
        "review": 0.3,
        "signals": 0.1
    },
    Domain.FOOD: {
        "structural": 0.5,
        "review": 0.4,
        "signals": 0.1
    },
    Domain.CULTURE: {
        "structural": 0.7,
        "review": 0.1,
        "signals": 0.2
    },
    Domain.ACTIVITIES: {
        "structural": 0.5,
        "review": 0.3,
        "signals": 0.2
    },
    Domain.TRAVEL_INTEL: {
        "structural": 0.8,
        "review": 0.0,
        "signals": 0.2
    },
    Domain.SAFETY_SUPPORT: {
        "structural": 0.8,
        "review": 0.0,
        "signals": 0.2
    },
}


# ============================================================
# DOMAIN SCORER CLASS
# ============================================================

class DomainScorer:

    def __init__(self):
        pass

    # --------------------------------------------------------
    # PUBLIC METHOD
    # --------------------------------------------------------

    def compute(self, entity: BaseEntity) -> float:
        """
        Compute final authenticity score based on domain.
        """

        weights = DOMAIN_WEIGHTS.get(entity.domain)

        if not weights:
            raise ValueError("Domain weights not defined.")

        structural_component = entity.structural_score * weights["structural"]
        review_component = entity.review_score * weights["review"]
        signal_component = self._compute_signal_component(entity) * weights["signals"]

        final_score = structural_component + review_component + signal_component
        final_score = round(min(final_score, 1.0), 3)

        entity.final_authenticity_score = final_score
        entity.assign_grade()

        entity.decision_trace.append(
            f"Domain scoring → structural:{round(structural_component,3)}, "
            f"review:{round(review_component,3)}, "
            f"signals:{round(signal_component,3)}"
        )

        return final_score

    # --------------------------------------------------------
    # SIGNAL COMPONENT
    # --------------------------------------------------------

    def _compute_signal_component(self, entity: BaseEntity) -> float:
        """
        Uses derived signals like:
        - safety_index
        - stability_index
        - price_index
        - crowd_index
        """

        signals = entity.derived_signals

        components = [
            signals.safety_index,
            signals.stability_index,
            1 - signals.fake_ratio,
            signals.time_suitability_index
        ]

        # Filter non-zero signals
        valid_components = [c for c in components if c > 0]

        if not valid_components:
            return 0.0

        return round(sum(valid_components) / len(valid_components), 3)


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

    entity.update_structural_score(0.82)
    entity.update_review_score(0.75)

    entity.derived_signals.safety_index = 0.9
    entity.derived_signals.stability_index = 0.8

    scorer = DomainScorer()
    scorer.compute(entity)

    print(entity.to_dict())
