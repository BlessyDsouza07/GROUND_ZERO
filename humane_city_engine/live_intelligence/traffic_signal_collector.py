"""
Traffic Signal Collector
------------------------

Collects real-time traffic congestion signals
for locations in Mangalore.

API:
Google Maps Distance Matrix
"""

import os
import requests

GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY")


def get_traffic_ratio(origin, destination):

    if not GOOGLE_MAPS_KEY:
        return None

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"

    params = {
        "origins": origin,
        "destinations": destination,
        "departure_time": "now",
        "key": GOOGLE_MAPS_KEY
    }

    try:

        response = requests.get(url, params=params, timeout=5)

        data = response.json()

        element = data["rows"][0]["elements"][0]

        base_time = element["duration"]["value"]
        traffic_time = element["duration_in_traffic"]["value"]

        return traffic_time / base_time

    except Exception:
        return None


def classify_traffic(ratio):

    if ratio is None:
        return "unknown"

    if ratio > 1.6:
        return "very_high"

    if ratio > 1.3:
        return "high"

    if ratio > 1.1:
        return "medium"

    return "low"