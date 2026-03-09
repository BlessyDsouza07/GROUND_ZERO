"""
live_intelligence/weather_collector.py  [NEW FILE]

PURPOSE:
    Fetch live, real weather data for Mangalore.
    Used to modulate crowd scores, safety signals, and tour recommendations.

WHY THIS FILE IS NEW:
    Original crowd_intelligence_engine.py tried to call OpenWeatherMap
    but only worked if OPENWEATHER_KEY env var was set. It returned a
    hardcoded modifier of 1 (neutral) when no key was available — meaning
    weather never actually affected any decision.

    This file uses Open-Meteo (https://open-meteo.com):
    - 100% FREE — no API key required, ever
    - Legal: Apache 2.0 licensed, open data
    - Updated: every hour
    - Covers: Mangalore precisely (coastal climate data)

DATA COLLECTED:
    - Temperature (°C)
    - Precipitation (mm/hour)
    - Wind speed (km/h)
    - Weather condition code (WMO standard)
    - Humidity (%)
    - UV index
    - Visibility

WHAT TO ADD TO city_bootstrap.py:
    from live_intelligence.weather_collector import get_live_weather
    weather = get_live_weather()

WHAT TO CHANGE IN crowd_intelligence_engine.py:
    Replace get_weather_modifier() function — see comment there.
"""

import requests
from datetime import datetime, timezone
from typing import Dict, Optional

# Mangalore coordinates
MANGALORE_LAT = 12.9141
MANGALORE_LON = 74.8560

# Open-Meteo API (free, no key needed)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


# ============================================================
# WMO WEATHER CODE → HUMAN LABEL
# Reference: https://open-meteo.com/en/docs
# ============================================================

WMO_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail"
}


def wmo_to_label(code: int) -> str:
    return WMO_CODE_MAP.get(code, f"Code {code}")


# ============================================================
# CROWD MODIFIER LOGIC
# (replaces OpenWeatherMap-dependent get_weather_modifier)
# ============================================================

def weather_crowd_modifier(condition_code: int, precipitation_mm: float) -> float:
    """
    Returns a multiplier for crowd score based on weather.

    0.2 = very bad weather (monsoon storm) → almost nobody out
    0.5 = rain → fewer people
    0.8 = cloudy / mild → slight reduction
    1.0 = clear → no adjustment
    1.1 = perfect morning weather → slight boost

    Mangalore has heavy monsoon (Jun–Sep), so this is critical.
    """

    # Heavy rain / thunderstorm
    if condition_code in [65, 80, 81, 82, 95, 96, 99] or precipitation_mm > 5:
        return 0.2

    # Moderate rain
    if condition_code in [61, 63] or precipitation_mm > 1:
        return 0.5

    # Drizzle
    if condition_code in [51, 53, 55]:
        return 0.7

    # Foggy
    if condition_code in [45, 48]:
        return 0.6

    # Overcast / cloudy
    if condition_code in [2, 3]:
        return 0.8

    # Mainly clear / clear sky — ideal beach/tourism weather
    return 1.0


# ============================================================
# MAIN FETCH FUNCTION
# ============================================================

def get_live_weather(
    lat: float = MANGALORE_LAT,
    lon: float = MANGALORE_LON
) -> Dict:
    """
    Fetch current weather for Mangalore from Open-Meteo.

    Returns a dict with all weather signals needed by other engines.
    Returns a safe 'neutral' dict if the API is unreachable.

    API: https://open-meteo.com/en/docs
    License: Free, Attribution CC BY 4.0
    No API key needed.
    """

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "visibility",
            "uv_index"
        ],
        "timezone": "Asia/Kolkata",
        "forecast_days": 1
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data.get("current", {})

        condition_code = int(current.get("weather_code", 0))
        precipitation = float(current.get("precipitation", 0))
        temperature = float(current.get("temperature_2m", 28))
        humidity = float(current.get("relative_humidity_2m", 70))
        wind_speed = float(current.get("wind_speed_10m", 10))
        uv_index = float(current.get("uv_index", 5))
        visibility = float(current.get("visibility", 10000))

        condition_label = wmo_to_label(condition_code)
        crowd_modifier = weather_crowd_modifier(condition_code, precipitation)

        return {
            "condition_code": condition_code,
            "condition": condition_label,
            "temperature_c": temperature,
            "humidity": humidity,
            "precipitation_mm": precipitation,
            "wind_speed_kmh": wind_speed,
            "uv_index": uv_index,
            "visibility_m": visibility,
            "crowd_modifier": crowd_modifier,
            "is_good_weather": crowd_modifier >= 0.9,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "Open-Meteo (open-meteo.com)",
            "license": "CC BY 4.0 — free, no API key required"
        }

    except Exception as e:
        print(f"  Weather API error (Open-Meteo): {e} — using neutral defaults")

        # SAFE FALLBACK — returns neutral modifier so engine still works
        return {
            "condition_code": 0,
            "condition": "Unknown",
            "temperature_c": 28,
            "humidity": 70,
            "precipitation_mm": 0,
            "wind_speed_kmh": 10,
            "uv_index": 5,
            "visibility_m": 10000,
            "crowd_modifier": 1.0,
            "is_good_weather": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "fallback_defaults",
            "error": str(e)
        }


# ============================================================
# EXTENDED: HOURLY FORECAST (next 24h)
# Used by tourist_flow_predictor.py
# ============================================================

def get_hourly_forecast(
    lat: float = MANGALORE_LAT,
    lon: float = MANGALORE_LON
) -> list:
    """
    Returns next 24 hours of weather forecast.
    Used to predict crowd windows and alert tourists about rain.
    """

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["temperature_2m", "precipitation_probability", "weather_code"],
        "timezone": "Asia/Kolkata",
        "forecast_days": 1
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        precip_probs = hourly.get("precipitation_probability", [])
        codes = hourly.get("weather_code", [])

        forecast = []

        for i, t in enumerate(times):
            code = int(codes[i]) if i < len(codes) else 0
            forecast.append({
                "time": t,
                "temperature_c": temps[i] if i < len(temps) else 28,
                "precipitation_probability": precip_probs[i] if i < len(precip_probs) else 0,
                "weather_code": code,
                "condition": wmo_to_label(code),
                "crowd_modifier": weather_crowd_modifier(code, 0)
            })

        return forecast

    except Exception as e:
        print(f"  Hourly forecast error: {e}")
        return []


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    import json

    weather = get_live_weather()
    print("\nLive Mangalore Weather:")
    print(json.dumps(weather, indent=2))

    print("\nNext 6 hours forecast:")
    forecast = get_hourly_forecast()
    for h in forecast[:6]:
        print(f"  {h['time']}  {h['condition']}  "
              f"Rain chance: {h['precipitation_probability']}%")