def should_notify(context: dict) -> bool:
    """
    Determines whether the system should notify the user
    or remain silent.

    Parameters:
    - context: dictionary containing evaluated signals

    Expected keys:
    - time_signal
    - energy_signal
    - crowd_signal
    - safety_signal

    Returns:
    - True  → Notify user
    - False → Stay silent
    """

    # Safety always overrides silence
    if context.get("safety_signal") == "Restricted":
        return True

    # Ideal timing + good energy match → gentle suggestion
    if (
        context.get("time_signal") in ["Best time", "Ideal", "Good time"]
        and context.get("energy_signal") == "Good fit"
        and context.get("crowd_signal") != "Very crowded"
    ):
        return True

    # Emergency or always-available contexts
    if context.get("time_signal") == "Always available":
        return True

    # Default behavior: stay silent
    return False
