"""
bias_guard/source_registry.py

Defines and validates neutral data source categories.
No platform names. No bias. Fully scalable.
"""

# Canonical neutral source categories
ALLOWED_SOURCE_TYPES = {
    "government",         # tourism boards, municipal data
    "community_map",      # OSM, civic mapping, Wikidata
    "public_media",       # Wikipedia, news archives, documentaries
    "field_observation",  # physical presence, sensors
    "user_behavior",      # in-app user actions (Engine 3+)
    "local_knowledge",    # curated local intelligence (hidden gems layer)
}

# Raw source labels → canonical category (defensive mapping)
RAW_TO_CANONICAL = {
    "OSM":              "community_map",
    "community_map":    "community_map",
    "public_media":     "public_media",
    "Government":       "government",
    "TourismBoard":     "government",
    "FieldSurvey":      "field_observation",
    "field_observation":"field_observation",
    "user_behavior":    "user_behavior",
    "local_knowledge":  "local_knowledge",
    "VerifiedAPI":      "community_map",
    "PublicRegistry":   "government",
    "CommunityVerified":"community_map",
}


def validate_sources(source_list) -> int:
    """
    Counts valid unique neutral sources.
    Accepts both canonical names and raw labels (mapped automatically).

    Returns: int — number of valid unique source categories
    """
    if not isinstance(source_list, list):
        return 0

    valid = set()
    for s in source_list:
        canonical = RAW_TO_CANONICAL.get(s, s)
        if canonical in ALLOWED_SOURCE_TYPES:
            valid.add(canonical)

    return len(valid)
