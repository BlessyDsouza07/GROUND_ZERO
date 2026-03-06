"""
SOURCE REGISTRY
Defines and validates neutral data source categories.
No platform names. No bias. Fully scalable.
"""

# Allowed neutral source categories
ALLOWED_SOURCE_TYPES = {
    "government",        # tourism boards, municipal data
    "community_map",     # open maps, civic mapping
    "public_media",      # news articles, documentaries
    "field_observation", # physical presence, sensors
    "user_behavior"      # in-app user actions
}


def validate_sources(source_list):
    """
    Counts how many VALID and UNIQUE neutral sources
    are contributing to a place's information.

    Args:
        source_list (list): list of source category strings

    Returns:
        int: number of valid unique sources
    """

    if not isinstance(source_list, list):
        return 0

    valid_sources = set()

    for source in source_list:
        if source in ALLOWED_SOURCE_TYPES:
            valid_sources.add(source)

    return len(valid_sources)

