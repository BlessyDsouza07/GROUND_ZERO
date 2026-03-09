def age_safety_check(user_age: int, category: str) -> str:
    """
    Determines if a place category is safe for the user's age.

    Parameters:
    - user_age: age of the user
    - category: place category

    Returns:
    - Safety decision
    """

    if not isinstance(user_age, int) or user_age <= 0:
        return "Unknown"

    # Categories not suitable for minors
    restricted_for_minors = [
        "Nightlife",
        "Isolated",
        "Adult Entertainment"
    ]

    if user_age < 18 and category in restricted_for_minors:
        return "Restricted"

    return "Allowed"
