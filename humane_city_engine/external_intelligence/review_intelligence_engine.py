"""
external_intelligence/review_intelligence_engine.py

Purpose
-------
Convert extracted review signals into explainable intelligence scores
that determine authenticity, hype, crowd pressure, and tourist trap risk.

This module is deterministic and fully explainable, matching the
Bias-Resistant City Discovery Engine philosophy.

Key Principles
--------------
• No star ratings
• No influencer popularity
• No social media metrics
• Only behavioral signals from reviews
• Deterministic scoring
"""

from typing import Dict


# ------------------------------------------------------------
# SCORING WEIGHTS
# These weights are transparent and adjustable.
# ------------------------------------------------------------

AUTHENTICITY_WEIGHT = 2.0
LOCAL_CULTURE_WEIGHT = 1.5

CROWD_WEIGHT = -0.5
COMMERCIAL_HYPE_WEIGHT = -1.0
TOURIST_TRAP_WEIGHT = -2.5


# ------------------------------------------------------------
# AUTHENTICITY SCORE
# ------------------------------------------------------------

def compute_authenticity_score(signals: Dict) -> float:
    """
    Compute authenticity score using deterministic weighting.

    Parameters
    ----------
    signals : Dict
        Output from review_signal_extractor

    Returns
    -------
    float
        Authenticity score
    """

    authenticity = signals.get("authenticity_mentions", 0)
    local_culture = signals.get("local_culture_mentions", 0)

    crowd = signals.get("crowd_mentions", 0)
    hype = signals.get("commercial_hype_mentions", 0)
    tourist_trap = signals.get("tourist_trap_mentions", 0)

    score = 0.0

    score += authenticity * AUTHENTICITY_WEIGHT
    score += local_culture * LOCAL_CULTURE_WEIGHT

    score += crowd * CROWD_WEIGHT
    score += hype * COMMERCIAL_HYPE_WEIGHT
    score += tourist_trap * TOURIST_TRAP_WEIGHT

    if score < 0:
        score = 0.0

    return round(score, 2)


# ------------------------------------------------------------
# CROWD PRESSURE INDEX
# ------------------------------------------------------------

def compute_crowd_pressure(signals: Dict) -> float:
    """
    Estimate crowd pressure based on review signals.

    Returns
    -------
    float
        Crowd index between 0 and 1
    """

    crowd_mentions = signals.get("crowd_mentions", 0)
    review_count = signals.get("review_count", 1)

    ratio = crowd_mentions / max(review_count, 1)

    return round(min(ratio, 1.0), 2)


# ------------------------------------------------------------
# HYPE INDEX
# ------------------------------------------------------------

def compute_hype_index(signals: Dict) -> float:
    """
    Detect commercial or social media hype level.

    Returns
    -------
    float
        Hype index between 0 and 1
    """

    hype_mentions = signals.get("commercial_hype_mentions", 0)
    review_count = signals.get("review_count", 1)

    ratio = hype_mentions / max(review_count, 1)

    return round(min(ratio, 1.0), 2)


# ------------------------------------------------------------
# TOURIST TRAP RISK
# ------------------------------------------------------------

def compute_tourist_trap_risk(signals: Dict) -> float:
    """
    Estimate tourist trap probability.

    Returns
    -------
    float
        Risk value between 0 and 1
    """

    trap_mentions = signals.get("tourist_trap_mentions", 0)
    review_count = signals.get("review_count", 1)

    ratio = trap_mentions / max(review_count, 1)

    return round(min(ratio, 1.0), 2)


# ------------------------------------------------------------
# FINAL CLASSIFICATION
# ------------------------------------------------------------

def classify_place(auth_score: float, trap_risk: float, hype_index: float) -> str:
    """
    Determine final authenticity category.
    """

    if trap_risk > 0.35:
        return "tourist_trap"

    if hype_index > 0.4:
        return "overhyped"

    if auth_score >= 8:
        return "very_authentic"

    if auth_score >= 4:
        return "authentic"

    if auth_score >= 2:
        return "mixed"

    return "low_authenticity"


# ------------------------------------------------------------
# FULL INTELLIGENCE REPORT
# ------------------------------------------------------------

def generate_review_intelligence(signals: Dict) -> Dict:
    """
    Generate full intelligence report for a place.
    """

    authenticity_score = compute_authenticity_score(signals)
    crowd_pressure = compute_crowd_pressure(signals)
    hype_index = compute_hype_index(signals)
    trap_risk = compute_tourist_trap_risk(signals)

    category = classify_place(
        authenticity_score,
        trap_risk,
        hype_index
    )

    return {

        "authenticity_score": authenticity_score,

        "crowd_pressure": crowd_pressure,

        "hype_index": hype_index,

        "tourist_trap_risk": trap_risk,

        "classification": category

    }


# ------------------------------------------------------------
# DEBUG TEST
# ------------------------------------------------------------

if __name__ == "__main__":

    test_signals = {

        "review_count": 5,
        "authenticity_mentions": 2,
        "crowd_mentions": 1,
        "tourist_trap_mentions": 1,
        "commercial_hype_mentions": 1,
        "local_culture_mentions": 2,

    }

    report = generate_review_intelligence(test_signals)

    print("\nReview Intelligence Report\n")

    for k, v in report.items():
        print(f"{k:25} : {v}")