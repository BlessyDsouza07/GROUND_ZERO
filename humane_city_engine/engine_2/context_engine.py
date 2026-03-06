from signals.time_signal import time_suitability
from signals.energy_signal import energy_match
from signals.crowd_signal import crowd_estimate
from signals.safety_signal import age_safety_check
from signals.silence_engine import should_notify


def evaluate_context(user: dict, place: dict, environment: dict):
    """
    Aggregates all context signals and decides whether
    to notify the user.

    Parameters:
    - user: { "age": int, "energy": str }
    - place: { "category": str, "osm_edits": int, "photo_count": int }
    - environment: { "hour": int }

    Returns:
    - notify (bool)
    - context (dict)
    """

    context = {
        "time_signal": time_suitability(
            place.get("category"),
            environment.get("hour")
        ),
        "energy_signal": energy_match(
            user.get("energy"),
            place.get("category")
        ),
        "crowd_signal": crowd_estimate(
            place.get("osm_edits", 0),
            place.get("photo_count", 0)
        ),
        "safety_signal": age_safety_check(
            user.get("age"),
            place.get("category")
        )
    }

    notify = should_notify(context)

    return notify, context
