"""
Bias Audit — computes bias_index for every place (blueprint 3.2).

bias_index ∈ [0, 1]: 0 = fully authentic / zero hype, 1 = fully
commercialised tourist trap. It is a weighted combination of:
  - media_mentions        (normalized, log-scaled — a handful of blog posts
                            shouldn't swamp the score the same way 500 do)
  - local_percentage      (inverted — high local % pulls bias DOWN)
  - commercial_flags      (souvenir density / inflated fees / sponsored signals)
  - tourist_popularity    (normalized 0..1 signal, e.g. review-count percentile)
  - sponsored_indicator   (boolean penalty — a paid/sponsored listing signal)

This module contains no I/O. It is pure math over `BiasSignals`, so it can
be exhaustively unit tested without a database or network — see
layer0/tests/test_bias_audit.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from layer0.domain.entities import BiasSignals, Grade

# Weights sum to 1.0. Chosen so that local_percentage (the strongest signal
# of authenticity per the blueprint's worked example, Table 10) dominates,
# while a single sponsored flag can still meaningfully move the score.
WEIGHT_MEDIA_MENTIONS = 0.25
WEIGHT_LOCAL_PERCENTAGE = 0.35
WEIGHT_COMMERCIAL_FLAGS = 0.20
WEIGHT_TOURIST_POPULARITY = 0.15
WEIGHT_SPONSORED = 0.05

# media_mentions is unbounded in principle; we log-compress it so 5 vs 50
# mentions matters more than 500 vs 545 does.
MEDIA_MENTIONS_SATURATION = 200  # mentions count at which the signal saturates to ~1.0
COMMERCIAL_FLAGS_SATURATION = 5  # commercial flag count at which signal saturates to 1.0


@dataclass(frozen=True)
class BiasBreakdown:
    """Explainable output — every component contributing to the final
    number, so a jury (or an admin dashboard) can see *why* a place scored
    the way it did, not just trust a black box."""
    media_component: float
    local_component: float
    commercial_component: float
    popularity_component: float
    sponsored_component: float
    bias_index: float


def _saturating_normalize(value: float, saturation_point: float) -> float:
    """Maps [0, saturation_point] -> [0, 1] with diminishing returns past
    the saturation point, using 1 - e^{-value/saturation_point}."""
    if value <= 0:
        return 0.0
    return min(1.0, 1.0 - math.exp(-value / saturation_point))


class BiasAuditService:
    def compute(self, signals: BiasSignals) -> BiasBreakdown:
        media_component = _saturating_normalize(
            signals.media_mentions, MEDIA_MENTIONS_SATURATION
        )
        # local_percentage is authenticity, so its contribution to *bias*
        # is inverted: high local % -> low bias contribution.
        local_component = 1.0 - max(0.0, min(1.0, signals.local_percentage))
        commercial_component = _saturating_normalize(
            signals.commercial_flags, COMMERCIAL_FLAGS_SATURATION
        )
        popularity_component = max(0.0, min(1.0, signals.tourist_popularity))
        sponsored_component = 1.0 if signals.sponsored_indicator else 0.0

        bias_index = (
            WEIGHT_MEDIA_MENTIONS * media_component
            + WEIGHT_LOCAL_PERCENTAGE * local_component
            + WEIGHT_COMMERCIAL_FLAGS * commercial_component
            + WEIGHT_TOURIST_POPULARITY * popularity_component
            + WEIGHT_SPONSORED * sponsored_component
        )
        bias_index = round(max(0.0, min(1.0, bias_index)), 4)

        return BiasBreakdown(
            media_component=round(media_component, 4),
            local_component=round(local_component, 4),
            commercial_component=round(commercial_component, 4),
            popularity_component=round(popularity_component, 4),
            sponsored_component=sponsored_component,
            bias_index=bias_index,
        )

    def grade_for(self, bias_index: float) -> Grade:
        if bias_index < 0.3:
            return Grade.AUTHENTIC
        if bias_index < 0.6:
            return Grade.BALANCED
        return Grade.COMMERCIALISED
