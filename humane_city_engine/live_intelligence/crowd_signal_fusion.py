"""
Crowd Signal Fusion Engine
--------------------------

Combines multiple real-time signals
to estimate crowd density at tourist locations.
"""

from datetime import datetime

from live_intelligence.location_registry import LOCATIONS
from live_intelligence.traffic_signal_collector import (
    get_traffic_ratio,
    classify_traffic
)


def time_based_signal(category):

    hour = datetime.now().hour

    if category == "beach":

        if 16 <= hour <= 19:
            return 0.9

        if 6 <= hour <= 9:
            return 0.7

        return 0.4

    if category == "market":

        if 7 <= hour <= 11:
            return 0.9

        return 0.4

    if category == "mall":

        if 17 <= hour <= 21:
            return 0.8

        return 0.5

    if category == "temple":

        if 6 <= hour <= 9:
            return 0.8

        if 17 <= hour <= 19:
            return 0.7

        return 0.4

    return 0.5


def classify_crowd(score):

    if score >= 0.85:
        return "very_high"

    if score >= 0.65:
        return "high"

    if score >= 0.45:
        return "medium"

    return "low"


def get_live_crowd():

    results = []

    for loc in LOCATIONS:

        origin = f"{loc['lat']},{loc['lng']}"
        destination = f"{loc['lat']+0.01},{loc['lng']+0.01}"

        traffic_ratio = get_traffic_ratio(origin, destination)

        traffic_level = classify_traffic(traffic_ratio)

        time_signal = time_based_signal(loc["category"])

        score = time_signal

        if traffic_level == "very_high":
            score += 0.4

        elif traffic_level == "high":
            score += 0.25

        elif traffic_level == "medium":
            score += 0.15

        score = min(score, 1)

        results.append({

            "place": loc["name"],

            "category": loc["category"],

            "traffic_level": traffic_level,

            "crowd_score": score,

            "crowd_level": classify_crowd(score)

        })

    return results


if __name__ == "__main__":

    data = get_live_crowd()

    for place in data:

        print(place)