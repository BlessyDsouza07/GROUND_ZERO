"""
CONSENSUS ENGINE
Evaluates whether place information is reliable
based on multi-source agreement.
"""

from bias_guard.source_registry import validate_sources

# Minimum number of neutral sources required
MIN_SOURCE_THRESHOLD = 2


def has_consensus(source_list):
    """
    Determines if a place has sufficient
    neutral source agreement.

    Args:
        source_list (list): list of source categories

    Returns:
        bool: True if consensus exists, False otherwise
    """

    valid_source_count = validate_sources(source_list)

    if valid_source_count >= MIN_SOURCE_THRESHOLD:
        return True

    return False
