"""
data_core/structural_validator.py  [v3 — Full Authenticity Formula]

Deterministic Structural Authenticity Score (SAS) Engine.

FORMULA (aligned with Ground Zero report, Section 4.5.1 + 3.1):
─────────────────────────────────────────────────────────────────
SAS = (
    source_confidence     × 0.30  +
    metadata_completeness × 0.25  +
    consensus_strength    × 0.20  +
    stability_index       × 0.15  +
    local_depth_bonus     × 0.10
) × bias_penalty_factor

GRADE THRESHOLDS:
  A: >= 0.75   Very strong — cross-verified, rich metadata
  B: >= 0.55   Good — primary source + solid metadata
  C: >= 0.38   Acceptable — exists with basic info
  D:  < 0.38   Weak — minimal data, single source

KEY FIX: normalizer.py sets entity.structural_score from OSM tag richness.
This class READS that value as the metadata base — it does NOT overwrite it.
It then enhances with source confidence, consensus, stability, local depth.
"""

import json
from typing import List
from core.base_models import BaseEntity, Domain, Grade
from utils.logger import get_logger

logger = get_logger("StructuralValidator")

SOURCE_WEIGHTS = {
    "OSM":              0.30,
    "community_map":    0.30,
    "public_media":     0.25,
    "Government":       0.40,
    "TourismBoard":     0.35,
    "FieldSurvey":      0.45,
    "PublicRegistry":   0.35,
    "VerifiedAPI":      0.30,
    "user_behavior":    0.10,
}
SOURCE_DIMINISHING = [1.0, 0.70, 0.50, 0.35, 0.25]

METADATA_FIELD_WEIGHTS = {
    "phone":          0.12,
    "website":        0.10,
    "opening_hours":  0.14,
    "address":        0.12,
    "cuisine":        0.08,
    "description":    0.09,
    "wheelchair":     0.05,
    "wikipedia":      0.12,
    "wikidata":       0.10,
    "alt_name":       0.04,
    "stars":          0.04,
}
METADATA_MAX = sum(METADATA_FIELD_WEIGHTS.values())


class StructuralValidator:

    def compute(self, entity: BaseEntity) -> float:
        extra = self._extract_extra(entity)

        source_conf = self._compute_source_confidence(entity.sources)
        osm_tag_score = entity.structural_score  # from normalizer — DO NOT RECOMPUTE
        metadata_completeness = self._compute_metadata_completeness(extra, osm_tag_score)
        consensus = self._compute_consensus(entity.sources)
        stability = self._compute_stability(extra, entity)
        local_depth = self._compute_local_depth(extra, entity)
        bias_factor = self._compute_bias_factor(entity)

        raw = (
            source_conf           * 0.30 +
            metadata_completeness * 0.25 +
            consensus             * 0.20 +
            stability             * 0.15 +
            local_depth           * 0.10
        ) * bias_factor

        sas = round(min(max(raw, 0.0), 1.0), 3)
        entity.update_structural_score(sas)
        entity.assign_grade()

        entity.decision_trace.append(
            f"SAS → src:{round(source_conf,3)} meta:{round(metadata_completeness,3)} "
            f"consensus:{round(consensus,3)} stability:{round(stability,3)} "
            f"local:{round(local_depth,3)} bias:{round(bias_factor,3)} = {sas}"
        )
        return sas

    def _compute_source_confidence(self, sources: List[str]) -> float:
        if not sources:
            return 0.0
        sorted_weights = sorted([SOURCE_WEIGHTS.get(s, 0.05) for s in sources], reverse=True)
        total = sum(w * (SOURCE_DIMINISHING[i] if i < len(SOURCE_DIMINISHING) else 0.20)
                    for i, w in enumerate(sorted_weights))
        return round(min(total, 1.0), 3)

    def _compute_metadata_completeness(self, extra: dict, osm_tag_score: float) -> float:
        field_score = sum(w for f, w in METADATA_FIELD_WEIGHTS.items()
                          if extra.get(f) and str(extra.get(f)).strip())
        normalised = round(min(field_score / METADATA_MAX, 1.0), 3)
        # 60% weighted field presence + 40% OSM tag richness
        return round(min(normalised * 0.60 + osm_tag_score * 0.40, 1.0), 3)

    def _compute_consensus(self, sources: List[str]) -> float:
        type_map = {
            "OSM": "community_map", "community_map": "community_map",
            "public_media": "public_media", "Government": "government",
            "TourismBoard": "government", "FieldSurvey": "field",
            "user_behavior": "behavioral",
        }
        n = len(set(type_map.get(s, s) for s in sources))
        return {0: 0.0, 1: 0.25, 2: 0.55, 3: 0.80}.get(n, 1.0)

    def _compute_stability(self, extra: dict, entity: BaseEntity) -> float:
        score = 0.0
        if extra.get("wikipedia"):     score += 0.30
        if extra.get("wikidata"):      score += 0.25
        if extra.get("opening_hours"): score += 0.15
        if extra.get("phone"):         score += 0.10
        if extra.get("website"):       score += 0.10
        for t in entity.decision_trace:
            if t.startswith("WIKIDATA_ENRICHED"):  score += 0.20; break
        for t in entity.decision_trace:
            if t.startswith("WIKIPEDIA_ENRICHED"): score += 0.15; break
        for t in entity.decision_trace:
            if t.startswith("OTM_ENRICHED"):       score += 0.10; break
        if "historic" in entity.category or "heritage" in entity.category:
            score += 0.15
        return round(min(score, 1.0), 3)

    def _compute_local_depth(self, extra: dict, entity: BaseEntity) -> float:
        score = 0.0
        if extra.get("name_tulu"):    score += 0.20
        if extra.get("name_kannada"): score += 0.15
        cuisine = (extra.get("cuisine") or "").lower()
        local_c = {"tulu","mangalorean","coastal","konkani","udupi",
                   "kori_rotti","neer_dosa","fish","seafood","prawn"}
        if any(c in cuisine for c in local_c): score += 0.25
        if extra.get("brand") or extra.get("operator"): score += 0.10
        if extra.get("religion"):     score += 0.10
        if len(extra.get("description","")) > 30: score += 0.20
        return round(min(score, 1.0), 3)

    def _compute_bias_factor(self, entity: BaseEntity) -> float:
        for t in entity.decision_trace:
            if "BIAS_AUDIT_REJECTED" in t: return 0.60
            if "promotional" in t.lower():  return 0.75
        return 1.0

    def _extract_extra(self, entity: BaseEntity) -> dict:
        for t in entity.decision_trace:
            if t.startswith("OSM_EXTRA:"):
                try:
                    return json.loads(t.replace("OSM_EXTRA:", ""))
                except Exception:
                    pass
        return {}
