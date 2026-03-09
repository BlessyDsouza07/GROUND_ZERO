from signals.time_signal import time_suitability
from signals.energy_signal import energy_match
from signals.crowd_signal import crowd_estimate
from signals.safety_signal import age_safety_check
from signals.silence_engine import should_notify
from utils.logger import get_logger

logger = get_logger("ContextEngine")


def evaluate_context(place, user_state):

    logger.info("Context evaluation started")

    try:
        # Example logic
        if user_state["energy"] == "low":
            logger.debug("User energy low, filtering quiet places")

        logger.info("Context evaluation completed")

    except Exception as e:
        logger.error(f"Context engine error: {e}")


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


class ContextEngine:
    """
    Class wrapper around the context evaluation functions.
    Used by run_engine.py to initialize and invoke context evaluation.
    """

    def __init__(self):
        logger.info("ContextEngine initialized")

    def evaluate_context(self, place: dict, user_state: dict):
        """
        Evaluates context for a place and user state.
        Delegates to the module-level evaluate_context function.
        """
        # Build a compatible environment dict from user_state
        environment = {"hour": user_state.get("hour", 12)}
        user = {
            "age": user_state.get("age", 25),
            "energy": user_state.get("energy", "medium")
        }
        notify, context = evaluate_context(user, place, environment)
        return {"notify": notify, "context": context}