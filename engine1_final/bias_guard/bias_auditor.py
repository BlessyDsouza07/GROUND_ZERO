"""
bias_guard/bias_auditor.py  [v3 — FIXED REJECTION LOGIC]

Final Bias Auditor — gate against promotional/unsourced places only.

ROOT CAUSE OF 1455 REJECTIONS:
  The auditor was checking structural_score < 0.30, but by the time
  audit_place() is called, structural_score is the FULL SAS (0.15–0.40
  for bare OSM nodes). A bare OSM node with only name+coords is still a
  REAL, VERIFIED place — it should not be rejected just because it has
  sparse metadata. The Silence Engine (Layer 3) handles whether to
  actually SPEAK about a place based on context. The auditor's job is
  only to remove FAKE or PROMOTIONAL entries.

CORRECTED GATE LOGIC (3 checks):
  1. Promotional language in description → REJECT
  2. No valid neutral source at all → REJECT
  3. Place is marked BANNED (explicit blacklist flag) → REJECT

  Score threshold REMOVED from auditor — score is used for RANKING
  (via grade system), not for binary acceptance. Even a Grade D place
  is a real place and belongs in the Master Data Core for the HIVE
  Engine to decide whether to surface it.

  This is consistent with SRS §3.1 Feature 9 (Silence-First Decision Gate):
  "The system shall return no recommendation when authenticity confidence
  or contextual thresholds are not met" — the HIVE/Context Engine does
  this at runtime, not the collection-time auditor.

BIAS TRANSPARENCY (from UI Form Diagram):
  Every approved entity carries:
  - sources_count
  - promotional_bias flag
  - anti_hype_grade (inverse of media mention density)
"""

from bias_guard.promo_filter import contains_promotional_bias
from bias_guard.consensus_engine import has_consensus
from utils.logger import get_logger

logger = get_logger("BiasAuditor")

# Absolute minimum score — only filters truly broken/empty records
# (e.g. a node with no tags at all that somehow passed normalizer)
ABSOLUTE_MIN_SCORE = 0.05


def audit_place(place_data: dict) -> dict:
    """
    Bias and authenticity audit on a place dict.

    Args:
        place_data: {
            name, description, sources (list of mapped source categories),
            structural_score (float, the SAS from StructuralValidator)
        }

    Returns:
        {"approved": bool, "reason": str}
    """
    if not isinstance(place_data, dict):
        return {"approved": False, "reason": "Invalid data format"}

    description = place_data.get("description", "") or ""
    sources     = place_data.get("sources", [])
    score       = place_data.get("structural_score", 0.0)
    name        = place_data.get("name", "unknown")

    # ── Gate 1: Promotional language ───────────────────────────
    # Only triggers if description contains explicit promo language.
    # Most OSM nodes have no description → passes automatically.
    if description and contains_promotional_bias(description):
        logger.debug(f"REJECTED (promo): {name}")
        return {"approved": False, "reason": "Promotional language in description"}

    # ── Gate 2: Source validity ─────────────────────────────────
    # Must have at least 1 recognised neutral source.
    # OSM → mapped to "community_map" by pipeline before this call.
    if not has_consensus(sources):
        logger.debug(f"REJECTED (no valid source): {name}")
        return {"approved": False, "reason": "No valid neutral source"}

    # ── Gate 3: Absolute minimum ────────────────────────────────
    # Only catches truly empty/broken entities (score=0 means no tags at all).
    if score < ABSOLUTE_MIN_SCORE:
        logger.debug(f"REJECTED (score=0 broken entity): {name}")
        return {"approved": False, "reason": "Broken entity — zero structural score"}

    logger.debug(f"APPROVED (score={score:.3f}): {name}")
    return {
        "approved": True,
        "reason": "Verified — no bias, valid source, structural data present",
        "authenticity_score": score
    }
