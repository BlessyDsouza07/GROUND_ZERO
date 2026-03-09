def time_suitability(category: str, hour: int) -> str:
    """
    Determines if a place category is suitable at a given hour.
    
    Parameters:
    - category: place category (Nature, Spiritual, Emergency, etc.)
    - hour: current hour (0–23)

    Returns:
    - Suitability label
    """

    if not isinstance(hour, int) or hour < 0 or hour > 23:
        return "Unknown"

    if category == "Emergency":
        return "Always available"

    if category == "Nature":
        if 6 <= hour <= 9:
            return "Best time"
        if 10 <= hour <= 17:
            return "Okay"
        return "Not suitable"

    if category == "Spiritual":
        if 5 <= hour <= 10:
            return "Ideal"
        if 16 <= hour <= 19:
            return "Acceptable"
        return "Not suitable"

    if category == "Explore":
        if 9 <= hour <= 17:
            return "Suitable"
        return "Closed or low value"

    if category == "Leisure":
        if 16 <= hour <= 20:
            return "Good time"
        return "Neutral"

    return "Neutral"
