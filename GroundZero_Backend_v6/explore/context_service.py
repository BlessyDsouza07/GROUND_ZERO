"""The "RIGHT NOW IN MANGALURU" live-context snapshot: weather, tide,
sunset, and today's event count — reusing the exact collectors Layer 0/2
already have (WeatherCollector, TideCollector), plus the standalone
live_events service's own DB. Nothing here is invented: if a source is
unreachable it reports `unavailable`, same "never fake it" rule the
collectors themselves already follow (see weather_collector.py's and
tide_collector.py's own docstrings).

Sunset/sunrise are computed with `astral` — real, offline astronomical
calculation from latitude/longitude/date, not an API call and not a
guess. Added to requirements.txt.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

from layer0.infrastructure.collectors.tide_collector import TideCollector
from layer0.infrastructure.collectors.weather_collector import WeatherCollector
from layer0.infrastructure.http_client import SourceUnavailable

logger = logging.getLogger("groundzero.explore.context")

MANGALURU_TZ = "Asia/Kolkata"


@dataclass(frozen=True)
class RightNow:
    now_local: datetime
    weather_available: bool
    temperature_celsius: Optional[float]
    condition: Optional[str]          # "Clear" / "Rain" / "Clouds" / ...
    is_rain: Optional[bool]
    tide_available: bool
    tide_state: Optional[str]         # "rising" / "falling" / "unknown"
    tide_source: Optional[str]
    sunset_local: datetime
    minutes_to_sunset: int            # negative once past sunset
    sunrise_local: datetime
    events_today_count: Optional[int]  # None if the Live Events module isn't available


class ExploreContextService:
    def __init__(self, weather_collector: WeatherCollector, tide_collector: TideCollector):
        self.weather_collector = weather_collector
        self.tide_collector = tide_collector

    async def right_now(self, lat: float, lon: float, events_today_count: Optional[int]) -> RightNow:
        now_utc = datetime.now(timezone.utc)
        tzinfo = ZoneInfo(MANGALURU_TZ)
        loc = LocationInfo("Mangaluru", "India", MANGALURU_TZ, lat, lon)
        now_local = now_utc.astimezone(tzinfo)
        sun_times = sun(loc.observer, date=now_local.date(), tzinfo=tzinfo)
        sunset_local = sun_times["sunset"]
        sunrise_local = sun_times["sunrise"]
        minutes_to_sunset = int((sunset_local - now_local).total_seconds() // 60)

        temperature: Optional[float] = None
        condition: Optional[str] = None
        is_rain: Optional[bool] = None
        weather_available = False
        try:
            forecast = await asyncio.wait_for(self.weather_collector.hourly_forecast(lat, lon, hours=1), timeout=4.0)
            if forecast:
                current = forecast[0]
                temperature = current.temperature_celsius
                condition = current.condition_main
                is_rain = current.is_rain
                weather_available = True
        except (SourceUnavailable, asyncio.TimeoutError) as exc:
            logger.info("Explore right_now: weather unavailable (%s)", exc)

        tide_state: Optional[str] = None
        tide_source: Optional[str] = None
        tide_available = False
        try:
            extremes = await asyncio.wait_for(self.tide_collector.extremes(lat, lon, days=1), timeout=4.0)
            if extremes:
                tide_state = self.tide_collector.current_state(extremes, now=now_utc)
                tide_source = extremes[0].source
                tide_available = True
        except (SourceUnavailable, asyncio.TimeoutError) as exc:
            logger.info("Explore right_now: tide unavailable (%s)", exc)

        return RightNow(
            now_local=now_local,
            weather_available=weather_available,
            temperature_celsius=temperature,
            condition=condition,
            is_rain=is_rain,
            tide_available=tide_available,
            tide_state=tide_state,
            tide_source=tide_source,
            sunset_local=sunset_local,
            minutes_to_sunset=minutes_to_sunset,
            sunrise_local=sunrise_local,
            events_today_count=events_today_count,
        )
