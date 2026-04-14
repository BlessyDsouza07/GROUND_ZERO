"""
data_core/domain_scorer.py  [v3 — Five-Layer Formula]

Final authenticity scorer using all 5 layers.

FORMULA (Ground Zero report §4.5.1):
  final_authenticity_score = (
      structural_score     × domain_struct_w    +
      authenticity_formula × domain_auth_w      +
      metadata_bonus       × domain_meta_w      +
      signal_score         × domain_signal_w
  )

  Where authenticity_formula = Layer 4's deterministic formula:
    log_source_weight * log(source_count) +
    agreement_weight  * agreement_score  +
    freshness_weight  * freshness_score  -
    bias_weight       * promotion_bias

Domain weights reflect what matters most per type:
  EMERGENCY/TRANSPORT: structural dominates (accuracy > richness)
  FOOD/STAY: metadata bonus high (practical info matters most)
  EXPLORE/CULTURE: authenticity formula high (trust > description)
  PLACES/ACTIVITIES: balanced
"""

import json
from core.base_models import BaseEntity, Domain, DerivedSignals
from utils.logger import get_logger

logger = get_logger("DomainScorer")

# (structural_w, authenticity_formula_w, metadata_bonus_w, signal_w)
DOMAIN_WEIGHTS = {
    Domain.PLACES:        (0.40, 0.25, 0.20, 0.15),
    Domain.FOOD:          (0.30, 0.25, 0.30, 0.15),
    Domain.EXPLORE:       (0.40, 0.30, 0.15, 0.15),
    Domain.STAY:          (0.30, 0.20, 0.35, 0.15),
    Domain.ACTIVITIES:    (0.35, 0.25, 0.20, 0.20),
    Domain.LOCAL:         (0.35, 0.25, 0.25, 0.15),
    Domain.TRANSPORT:     (0.55, 0.15, 0.20, 0.10),
    Domain.EMERGENCY:     (0.65, 0.10, 0.15, 0.10),
    Domain.CULTURE:       (0.40, 0.30, 0.15, 0.15),
    Domain.TRAVEL_INTEL:  (0.60, 0.20, 0.10, 0.10),
    Domain.SAFETY_SUPPORT:(0.60, 0.15, 0.15, 0.10),
}
DEFAULT_WEIGHTS = (0.40, 0.25, 0.20, 0.15)


class DomainScorer:

    def compute(self, entity: BaseEntity) -> float:
        # Populate derived_signals from OSM_EXTRA (backward compat)
        self._populate_derived_signals(entity)

        sw, aw, mw, sigw = DOMAIN_WEIGHTS.get(entity.domain, DEFAULT_WEIGHTS)

        struct_component = entity.structural_score * sw
        auth_component   = entity.authenticity.compute_formula_score() * aw
        meta_bonus       = self._compute_metadata_bonus(entity) * mw
        signal_component = self._compute_signal_score(entity) * sigw

        final = round(min(struct_component + auth_component + meta_bonus + signal_component, 1.0), 3)

        entity.final_authenticity_score = final
        entity.assign_grade()

        entity.decision_trace.append(
            f"DOMAIN_SCORE → struct:{round(struct_component,3)} "
            f"auth_formula:{round(auth_component,3)} "
            f"meta:{round(meta_bonus,3)} "
            f"signals:{round(signal_component,3)} = {final}"
        )
        return final

    def _populate_derived_signals(self, entity: BaseEntity):
        """Sync derived_signals from the richer Layer 2–4 data."""
        ds = entity.derived_signals
        auth = entity.authenticity
        ctx  = entity.contextual
        exp  = entity.experience

        ds.stability_index        = auth.freshness_score
        ds.fake_ratio             = auth.promotion_bias_score * 0.5
        ds.safety_index           = 0.9 if entity.domain == Domain.EMERGENCY else 0.6
        ds.crowd_index            = {"low": 0.2, "medium": 0.5, "high": 0.8}.get(ctx.crowd_level, 0.5)
        ds.time_suitability_index = 0.8 if entity.contextual.avg_duration_minutes > 0 else 0.5
        ds.review_score           = exp.emotion_score.get("positive", 0.6)
        ds.price_index            = auth.source_agreement_score

    def _compute_metadata_bonus(self, entity: BaseEntity) -> float:
        extra = {}
        for t in entity.decision_trace:
            if t.startswith("OSM_EXTRA:") or t.startswith("HG_META:"):
                try:
                    extra = json.loads(t.split(":", 1)[1])
                except Exception:
                    pass
                break
        score = 0.0
        if extra.get("opening_hours"): score += 0.22
        if extra.get("phone"):         score += 0.18
        if extra.get("website"):       score += 0.15
        if extra.get("address"):       score += 0.15
        if extra.get("description"):   score += 0.15
        if extra.get("cuisine"):       score += 0.08
        if extra.get("wheelchair"):    score += 0.07
        return round(min(score, 1.0), 3)

    def _compute_signal_score(self, entity: BaseEntity) -> float:
        ds = entity.derived_signals
        auth = entity.authenticity
        exp  = entity.experience
        components = [
            ds.stability_index,
            ds.time_suitability_index,
            ds.safety_index * 0.5,
            max(0.0, 1.0 - ds.fake_ratio),
            exp.emotion_score.get("positive", 0.5),
            exp.silence_suitability * 0.5,
        ]
        return round(sum(components) / len(components), 3)
