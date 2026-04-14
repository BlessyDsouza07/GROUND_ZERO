"""
CONSENSUS ENGINE
Evaluates whether place information is reliable
based on multi-source agreement.

UPDATED THRESHOLDS (v2):
  MIN_SOURCE_THRESHOLD = 1   — OSM alone is sufficient
  STRONG_CONSENSUS     = 2   — 2+ sources = stronger signal (bonus, not gate)

  Rationale:
    OpenStreetMap is a globally verified community database with
    hundreds of millions of mapped features. A named place with a
    verified OSM entry (lat, lon, tags) is a legitimate data point.
    Requiring 2 sources as a hard gate was rejecting 95%+ of valid
    places that simply haven't been cross-referenced yet.
    Multi-source verification is tracked as a quality signal, not
    used as a binary pass/fail gate.
"""

from bias_guard.source_registry import validate_sources

# Minimum valid sources to pass consensus check
MIN_SOURCE_THRESHOLD = 1       # OSM alone = sufficient

# Strong consensus bonus threshold (used by authenticity scorer)
STRONG_CONSENSUS_THRESHOLD = 2  # 2+ sources = high confidence


def has_consensus(source_list):
    """
    Determines if a place has sufficient neutral source agreement.

    Args:
        source_list (list): list of source category strings
                            (from source_registry.ALLOWED_SOURCE_TYPES)

    Returns:
        bool: True if consensus exists, False otherwise
    """
    valid_source_count = validate_sources(source_list)
    return valid_source_count >= MIN_SOURCE_THRESHOLD


def consensus_strength(source_list) -> str:
    """
    Returns a qualitative strength label for the source consensus.

    Returns:
        str: "strong" | "moderate" | "weak" | "none"
    """
    count = validate_sources(source_list)
    if count >= 3:   return "strong"
    if count == 2:   return "moderate"
    if count == 1:   return "weak"
    return "none"