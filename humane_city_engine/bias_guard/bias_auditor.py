"""
FINAL BIAS AUDITOR
Decides whether a place is safe to recommend.
"""

from bias_guard.promo_filter import contains_promotional_bias
from bias_guard.consensus_engine import has_consensus
from bias_guard.authenticity_score import calculate_authenticity_score

# Minimum authenticity score required
AUTHENTICITY_THRESHOLD = 0.6


def audit_place(place_data):
    """
    Runs full bias and authenticity audit.

    Args:
        place_data (dict): complete place information

    Returns:
        dict: audit result with decision and reason
    """

    if not isinstance(place_data, dict):
        return {
            "approved": False,
            "reason": "Invalid data format"
        }

    description = place_data.get("description", "")
    sources = place_data.get("sources", [])

    # Step 1: Promotional bias check
    if contains_promotional_bias(description):
        return {
            "approved": False,
            "reason": "Promotional language detected"
        }

    # Step 2: Consensus check
    if not has_consensus(sources):
        return {
            "approved": False,
            "reason": "Insufficient source consensus"
        }

    # Step 3: Authenticity scoring
    score = calculate_authenticity_score(place_data)

    if score < AUTHENTICITY_THRESHOLD:
        return {
            "approved": False,
            "reason": f"Low authenticity score ({score})"
        }

    # Passed all checks
    return {
        "approved": True,
        "authenticity_score": score,
        "reason": "Place verified and unbiased"
    }
