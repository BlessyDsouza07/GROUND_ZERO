def energy_match(user_energy: str, category: str) -> str:
    """
    Matches user energy level with place category.

    Parameters:
    - user_energy: 'low', 'medium', or 'high'
    - category: place category

    Returns:
    - Match decision
    """

    if user_energy not in ["low", "medium", "high"]:
        return "Unknown"

    if user_energy == "low":
        if category in ["Nature", "Leisure", "Spiritual"]:
            return "Good fit"
        return "Avoid"

    if user_energy == "medium":
        if category in ["Explore", "Local Life", "Leisure"]:
            return "Good fit"
        return "Neutral"

    if user_energy == "high":
        return "Any suitable"

    return "Neutral"
