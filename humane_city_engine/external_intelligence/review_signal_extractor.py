"""
external_intelligence/review_signal_extractor.py

Purpose
-------
Extract structured intelligence signals from review text without relying on ratings.
This module supports the Bias-Resistant City Discovery Engine by identifying patterns
that indicate authenticity, hype, crowd pressure, or potential tourist traps.

Key Design Principles
---------------------
• No star ratings used
• No influencer metrics
• No popularity ranking
• Deterministic keyword detection
• Fully explainable signal extraction

Signals Extracted
-----------------
1. Authenticity mentions
2. Crowd mentions
3. Tourist trap indicators
4. Commercial hype indicators
5. Local culture indicators

Output
------
Structured signal dictionary for downstream engines.
"""

import re
from typing import List, Dict


# -------------------------------------------------------------------------
# KEYWORD SIGNAL REGISTRIES
# These are intentionally deterministic and auditable
# -------------------------------------------------------------------------

AUTHENTICITY_KEYWORDS = [
    "authentic",
    "traditional",
    "local",
    "heritage",
    "original",
    "family run",
    "homemade",
    "old style",
    "since",
]

CROWD_KEYWORDS = [
    "crowded",
    "long queue",
    "packed",
    "rush",
    "busy",
    "waiting time",
    "line outside",
]

TOURIST_TRAP_KEYWORDS = [
    "tourist trap",
    "overpriced",
    "not worth",
    "ripoff",
    "too expensive",
    "avoid this place",
]

COMMERCIAL_HYPE_KEYWORDS = [
    "instagrammable",
    "viral",
    "trendy",
    "famous",
    "influencer",
    "social media hype",
]

LOCAL_CULTURE_KEYWORDS = [
    "mangalorean",
    "coastal",
    "tulu",
    "udupi style",
    "kori rotti",
    "neer dosa",
]


# -------------------------------------------------------------------------
# TEXT NORMALIZATION
# -------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Lowercase and remove punctuation for consistent matching.
    """

    if not text:
        return ""

    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)

    return text


# -------------------------------------------------------------------------
# KEYWORD COUNTER
# -------------------------------------------------------------------------

def count_keyword_matches(text: str, keywords: List[str]) -> int:
    """
    Counts how many keywords appear in the text.
    """

    count = 0

    for keyword in keywords:
        if keyword in text:
            count += 1

    return count


# -------------------------------------------------------------------------
# MAIN SIGNAL EXTRACTION FUNCTION
# -------------------------------------------------------------------------

def extract_review_signals(reviews: List[str]) -> Dict:
    """
    Convert raw review texts into structured intelligence signals.

    Parameters
    ----------
    reviews : List[str]
        List of review texts.

    Returns
    -------
    Dict
        Extracted signal counts.
    """

    signals = {
        "review_count": 0,
        "authenticity_mentions": 0,
        "crowd_mentions": 0,
        "tourist_trap_mentions": 0,
        "commercial_hype_mentions": 0,
        "local_culture_mentions": 0,
    }

    if not reviews:
        return signals

    signals["review_count"] = len(reviews)

    for review in reviews:

        try:

            normalized = normalize_text(review)

            signals["authenticity_mentions"] += count_keyword_matches(
                normalized, AUTHENTICITY_KEYWORDS
            )

            signals["crowd_mentions"] += count_keyword_matches(
                normalized, CROWD_KEYWORDS
            )

            signals["tourist_trap_mentions"] += count_keyword_matches(
                normalized, TOURIST_TRAP_KEYWORDS
            )

            signals["commercial_hype_mentions"] += count_keyword_matches(
                normalized, COMMERCIAL_HYPE_KEYWORDS
            )

            signals["local_culture_mentions"] += count_keyword_matches(
                normalized, LOCAL_CULTURE_KEYWORDS
            )

        except Exception:
            # Fail-safe: skip problematic review
            continue

    return signals


# -------------------------------------------------------------------------
# DEBUG / LOCAL TEST MODE
# -------------------------------------------------------------------------

if __name__ == "__main__":

    sample_reviews = [

        "Authentic traditional Mangalorean food. Family run place.",
        "Very crowded during weekends. Long queue outside.",
        "Honestly a tourist trap and overpriced.",
        "Famous instagrammable café with viral desserts.",
        "Great place to try neer dosa and kori rotti."

    ]

    result = extract_review_signals(sample_reviews)

    print("\nReview Intelligence Signals\n")
    for k, v in result.items():
        print(f"{k:30} : {v}")