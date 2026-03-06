"""
Tourist Flow Prediction Engine
--------------------------------

Predicts future crowd levels at tourist locations
using contextual signals.

Signals used:
- sunset timing
- weekend patterns
- weather forecast
- current crowd state
"""

import os
import requests
from datetime import datetime, timedelta

from live_intelligence.location_registry import LOCATIONS
from live_intelligence.crowd_signal_fusion import get_live_crowd

WEATHER_KEY = os.getenv("OPENWEATHER_KEY")


# ------------------------------------------------
# WEATHER FORECAST SIGNAL
# ------------------------------------------------

def get_weather_forecast(lat, lng):

    if not WEATHER_KEY:
        return "clear"

    url = "https://api.openweathermap.org/data/2.5/forecast"

    params = {
        "lat": lat,
        "lon": lng,
        "appid": WEATHER_KEY,
        "units": "metric"
    }

    try:

        r = requests.get(url, params=params, timeout=5)

        data = r.json()

        weather = data["list"][0]["weather"][0]["main"]

        return weather

    except:

        return "clear"


# ------------------------------------------------
# WEEKEND SIGNAL
# ------------------------------------------------

def weekend_signal():

    today = datetime.now().weekday()

    if today in [5, 6]:  # Saturday Sunday
        return 0.3

    return 0


# ------------------------------------------------
# SUNSET CROWD SIGNAL
# ------------------------------------------------

def sunset_signal(location):

    hour = datetime.now().hour

    if location["category"] == "beach":

        if 16 <= hour <= 18:
            return 0.5

    return 0


# ------------------------------------------------
# WEATHER CROWD MODIFIER
# ------------------------------------------------

def weather_modifier(weather):

    if weather in ["Rain", "Thunderstorm"]:
        return -0.4

    if weather in ["Clouds"]:
        return -0.1

    return 0.1


# ------------------------------------------------
# PREDICTION ENGINE
# ------------------------------------------------

def predict_crowd_next_hours(hours=2):

    live = get_live_crowd()

    predictions = []

    for loc in LOCATIONS:

        current = next(
            x for x in live
            if x["place"] == loc["name"]
        )

        score = current["crowd_score"]

        score += weekend_signal()

        score += sunset_signal(loc)

        weather = get_weather_forecast(loc["lat"], loc["lng"])

        score += weather_modifier(weather)

        score = max(0, min(score, 1))

        predictions.append({

            "place": loc["name"],

            "current_level": current["crowd_level"],

            "predicted_level": classify_prediction(score),

            "weather": weather,

            "prediction_hours": hours

        })

    return predictions


# ------------------------------------------------
# CLASSIFY PREDICTION
# ------------------------------------------------

def classify_prediction(score):

    if score > 0.85:
        return "very_high"

    if score > 0.65:
        return "high"

    if score > 0.45:
        return "medium"

    return "low"


# ------------------------------------------------
# MAIN
# ------------------------------------------------

if __name__ == "__main__":

    result = predict_crowd_next_hours()

    for r in result:

        print(r)