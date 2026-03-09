def crowd_estimate(osm_edit_count: int, photo_count: int) -> str:
    """
    Estimates crowd level using neutral proxy signals.

    Parameters:
    - osm_edit_count: number of OSM edits for the place
    - photo_count: number of public-domain images (e.g., Wikimedia)

    Returns:
    - Crowd level classification
    """

    # Defensive handling
    if osm_edit_count is None:
        osm_edit_count = 0
    if photo_count is None:
        photo_count = 0

    score = (osm_edit_count * 0.6) + (photo_count * 0.4)

    if score >= 80:
        return "Very crowded"
    elif score >= 40:
        return "Moderately crowded"
    else:
        return "Calm"
