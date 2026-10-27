"""
Weather collector (blueprint 3.1 source #5). Used by:
  - Layer 0 to tag season_suitability during ingestion
  - Layer 2 weather-adaptive scheduling (blueprint 5.4) — that consumer
    calls this same collector at HIVE-run time, not just during ETL.

Real Open-Meteo Forecast API (https://open-meteo.com). Chosen over
OpenWeatherMap's One Call 3.0 endpoint because One Call 3.0 requires a
billing-enabled account and API key even on its "free" tier — it was
never actually a no-cost source, which is why OPENWEATHERMAP_API_KEY sat
blank and every call raised SourceUnavailable. Open-Meteo's forecast
endpoint needs no signup, no key, and no card on file for non-commercial
use, so there is nothing left to configure for this collector to work.
Still raises SourceUnavailable (never a fake forecast) if the network
call itself fails.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from layer0.infrastructure.http_client import ResilientHttpClient, SourceUnavailable

logger = logging.getLogger("groundzero.layer0.collectors.weather")

SOURCE_NAME = "weather_api"

# WMO weather codes (https://open-meteo.com/en/docs — "WMO Weather
# interpretation codes"), grouped into the same condition_main /
# is_rain / is_severe shape the rest of the codebase already consumes.
_RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
_THUNDERSTORM_CODES = {95, 96, 99}
_SNOW_CODES = {71, 73, 75, 77, 85, 86}
_FOG_CODES = {45, 48}
_CLOUD_CODES = {1, 2, 3}


def _condition_for(code: int) -> str:
    if code in _THUNDERSTORM_CODES:
        return "Thunderstorm"
    if code in _RAIN_CODES:
        return "Rain"
    if code in _SNOW_CODES:
        return "Snow"
    if code in _FOG_CODES:
        return "Fog"
    if code in _CLOUD_CODES:
        return "Clouds"
    if code == 0:
        return "Clear"
    return "Unknown"


@dataclass(frozen=True)
class HourlyForecast:
    timestamp: datetime
    condition_main: str      # "Rain", "Clear", "Clouds", ...
    is_rain: bool
    is_severe: bool
    temperature_celsius: float


class WeatherCollector:
    def __init__(self, http_client: ResilientHttpClient, api_url: str, api_key: str | None = None):
        # api_key is accepted only for backward-compatible construction —
        # Open-Meteo's forecast endpoint does not use one. Kept as a
        # parameter (rather than removed) so layer2/api/dependencies.py
        # does not need to change at all.
        self.http_client = http_client
        self.api_url = api_url
        self.api_key = api_key

    async def hourly_forecast(self, lat: float, lon: float, hours: int = 12) -> list[HourlyForecast]:
        try:
            response = await self.http_client.request(
                SOURCE_NAME, "GET", self.api_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "temperature_2m,weathercode",
                    "timezone": "auto",
                    "forecast_days": 2,
                },
            )
        except SourceUnavailable:
            logger.warning("%s: source unavailable this run", SOURCE_NAME)
            raise

        data = response.json()
        hourly = data.get("hourly", {})
        times: list[str] = hourly.get("time", [])
        temps: list[float] = hourly.get("temperature_2m", [])
        codes: list[int] = hourly.get("weathercode", [])

        forecasts: list[HourlyForecast] = []
        for time_str, temp, code in zip(times, temps, codes):
            forecasts.append(
                HourlyForecast(
                    timestamp=datetime.fromisoformat(time_str),
                    condition_main=_condition_for(int(code)),
                    is_rain=int(code) in _RAIN_CODES or int(code) in _THUNDERSTORM_CODES,
                    is_severe=int(code) in _THUNDERSTORM_CODES,
                    temperature_celsius=float(temp),
                )
            )

        # Open-Meteo's hourly array always starts at local midnight, not
        # "now" — find the first entry at or after the current local
        # hour and return the next `hours` from there.
        current_hour_str = datetime.now().strftime("%Y-%m-%dT%H:00")
        start_idx = next((i for i, t in enumerate(times) if t >= current_hour_str), 0)
        return forecasts[start_idx:start_idx + hours]