"""
data_core/domain_scorer.py

Domain-specific authenticity scoring engine.
"""

from core.base_models import BaseEntity, Domain


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
    # Additional domains used in normalizer.py
    Domain.EMERGENCY: {
        "structural": 0.9,
        "review": 0.0,
        "signals": 0.1
    },
    Domain.STAY: {
        "structural": 0.5,
        "review": 0.4,
        "signals": 0.1
    },
    Domain.TRANSPORT: {
        "structural": 0.8,
        "review": 0.1,
        "signals": 0.1
    },
    Domain.EXPLORE: {
        "structural": 0.6,
        "review": 0.2,
        "signals": 0.2
    },
    Domain.LOCAL: {
        "structural": 0.5,
        "review": 0.3,
        "signals": 0.2
    },
}

# Default weights for any domain not explicitly listed
DEFAULT_WEIGHTS = {
    "structural": 0.6,
    "review": 0.2,
    "signals": 0.2
}


class DomainScorer:

    def __init__(self):
        pass

    def compute(self, entity: BaseEntity) -> float:
        """Compute final authenticity score based on domain."""

        weights = DOMAIN_WEIGHTS.get(entity.domain, DEFAULT_WEIGHTS)

        structural_component = entity.structural_score * weights["structural"]
        review_component = entity.review_score * weights["review"]
        signal_component = self._compute_signal_component(entity) * weights["signals"]

        final_score = structural_component + review_component + signal_component
        final_score = round(min(final_score, 1.0), 3)

        entity.final_authenticity_score = final_score
        entity.assign_grade()

        entity.decision_trace.append(
            f"Domain scoring -> structural:{round(structural_component,3)}, "
            f"review:{round(review_component,3)}, "
            f"signals:{round(signal_component,3)}"
        )

        return final_score

    def _compute_signal_component(self, entity: BaseEntity) -> float:
        signals = entity.derived_signals

        components = [
            signals.safety_index,
            signals.stability_index,
            1 - signals.fake_ratio,
            signals.time_suitability_index
        ]

        valid_components = [c for c in components if c > 0]

        if not valid_components:
            return 0.0

        return round(sum(valid_components) / len(valid_components), 3)