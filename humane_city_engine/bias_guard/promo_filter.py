"""
PROMOTIONAL BIAS FILTER
Detects marketing, hype, and influencer-style language.
"""

# Known promotional / influencer keywords
PROMOTIONAL_KEYWORDS = {
    "best",
    "top",
    "must visit",
    "number one",
    "famous",
    "hidden gem",
    "viral",
    "trending",
    "instagrammable",
    "unmissable",
    "luxury",
    "exclusive"
}


def contains_promotional_bias(text):
    """
    Checks if given text contains promotional bias.

    Args:
        text (str): description text

    Returns:
        bool: True if biased, False otherwise
    """

    if not isinstance(text, str):
        return False

    text = text.lower().strip()

    if not text:
        return False

    for keyword in PROMOTIONAL_KEYWORDS:
        if keyword in text:
            return True

    return False
