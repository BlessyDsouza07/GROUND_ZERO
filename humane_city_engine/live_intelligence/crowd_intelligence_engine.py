"""
Real Crowd Intelligence Engine
--------------------------------

Hybrid system using live signals:
- Traffic congestion
- Event density
- Review activity
- Weather conditions

City: Mangalore
"""

import requests
import os
from datetime import datetime
from utils.logger import get_logger

logger = get_logger("CrowdEngine")


def estimate_crowd(place):

    logger.info(f"Estimating crowd level for {place}")

    try:
        crowd_score = 0.5  # Example placeholder

        logger.debug(f"Crowd score calculated: {crowd_score}")

        return crowd_score

    except Exception as e:
        logger.error(f"Crowd estimation failed: {e}")
        return None

# API KEYS
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY")
WEATHER_KEY = os.getenv("OPENWEATHER_KEY")


# -----------------------------------------------------
# LOCATIONS TO TRACK
# -----------------------------------------------------

LOCATIONS = [

    {
        "name": "Panambur Beach",
        "lat": 12.9141,
        "lng": 74.8270
    },

    {
        "name": "Tannirbhavi Beach",
        "lat": 12.8987,
        "lng": 74.8060
    },

    {
        "name": "Pilikula Nisargadhama",
        "lat": 12.9418,
        "lng": 74.9270
    },

    {
        "name": "Central Market",
        "lat": 12.8698,
        "lng": 74.8436
    }

]


# -----------------------------------------------------
# TRAFFIC ANALYZER
# -----------------------------------------------------

def get_traffic_level(lat, lng):

    if not GOOGLE_MAPS_KEY:
        return "unknown"

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"

    params = {
        "origins": f"{lat},{lng}",
        "destinations": f"{lat+0.02},{lng+0.02}",
        "departure_time": "now",
        "key": GOOGLE_MAPS_KEY
    }

    try:

        r = requests.get(url, params=params)

        data = r.json()

        duration = data["rows"][0]["elements"][0]["duration"]["value"]
        traffic = data["rows"][0]["elements"][0]["duration_in_traffic"]["value"]

        ratio = traffic / duration

        if ratio > 1.5:
            return "high"

        if ratio > 1.2:
            return "medium"

        return "low"

    except:
        return "unknown"


# -----------------------------------------------------
# WEATHER IMPACT
# -----------------------------------------------------

def get_weather_modifier(lat, lng):

    if not WEATHER_KEY:
        return 1

    url = "https://api.openweathermap.org/data/2.5/weather"

    params = {
        "lat": lat,
        "lon": lng,
        "appid": WEATHER_KEY
    }

    try:

        r = requests.get(url, params=params)

        data = r.json()

        weather = data["weather"][0]["main"]

        if weather in ["Rain", "Thunderstorm"]:

            return 0.5

        return 1

    except:

        return 1


# -----------------------------------------------------
# TIME CROWD ESTIMATE
# -----------------------------------------------------

def time_based_crowd_estimate(location):

    hour = datetime.now().hour

    if location == "Panambur Beach":

        if 6 <= hour <= 9:
            return 0.6

        if 16 <= hour <= 19:
            return 0.9

        return 0.4

    if location == "Central Market":

        if 7 <= hour <= 11:
            return 0.9

        return 0.3

    return 0.5


# -----------------------------------------------------
# FINAL CROWD SCORE
# -----------------------------------------------------

def calculate_crowd_score(place):

    traffic = get_traffic_level(place["lat"], place["lng"])

    time_factor = time_based_crowd_estimate(place["name"])

    weather_factor = get_weather_modifier(place["lat"], place["lng"])

    score = time_factor * weather_factor

    if traffic == "high":
        score += 0.4

    if traffic == "medium":
        score += 0.2

    return min(score, 1)


# -----------------------------------------------------
# CROWD LEVEL CLASSIFIER
# -----------------------------------------------------

def classify_crowd(score):

    if score > 0.8:
        return "very_high"

    if score > 0.6:
        return "high"

    if score > 0.4:
        return "medium"

    return "low"


# -----------------------------------------------------
# MAIN ENGINE
# -----------------------------------------------------

def get_live_crowd_status():

    results = []

    for place in LOCATIONS:

        score = calculate_crowd_score(place)

        results.append({

            "place": place["name"],

            "crowd_score": score,

            "crowd_level": classify_crowd(score),

            "traffic": get_traffic_level(place["lat"], place["lng"])

        })

    return results


# -----------------------------------------------------
# MAIN
# -----------------------------------------------------

if __name__ == "__main__":

    data = get_live_crowd_status()

    for p in data:

        print(p)