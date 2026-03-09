"""
AUTHENTICITY SCORING ENGINE
Assigns a neutral authenticity score to places.
"""

from bias_guard.consensus_engine import has_consensus
from bias_guard.source_registry import validate_sources


def calculate_authenticity_score(place_data):
    """
    Calculates authenticity score based on:
    - number of neutral sources
    - consensus existence
    - presence of factual data

    Args:
        place_data (dict): structured place information

    Returns:
        float: authenticity score (0.0 to 1.0)
    """

    if not isinstance(place_data, dict):
        return 0.0

    sources = place_data.get("sources", [])
    has_name = bool(place_data.get("name"))
    has_location = (
        place_data.get("latitude") is not None and
        place_data.get("longitude") is not None
    )

    source_score = min(validate_sources(sources) / 4.0, 1.0)
    consensus_score = 1.0 if has_consensus(sources) else 0.0
    completeness_score = 1.0 if (has_name and has_location) else 0.5

    final_score = (
        (0.4 * source_score) +
        (0.4 * consensus_score) +
        (0.2 * completeness_score)
    )

    return round(final_score, 2)


class AuthenticityScore:
    """
    Class wrapper around the authenticity scoring functions.
    Used by run_engine.py to initialize and invoke authenticity evaluation.
    """

    def __init__(self):
        pass

    def calculate_score(self, place_data: dict) -> float:
        """
        Calculates the authenticity score for a given place.
        Delegates to the module-level calculate_authenticity_score function.
        """
        return calculate_authenticity_score(place_data)