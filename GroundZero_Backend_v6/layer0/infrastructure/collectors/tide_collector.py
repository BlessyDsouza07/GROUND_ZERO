"""
Tide collector (blueprint 3.1 source #6) — "critical for Mangaluru coastal
spots" per the blueprint. Used for `tide_dependency` places (beaches,
coastal viewpoints) both during Layer 0 ingestion tagging and by Layer 2/3
for tide-suitability scoring (Table 6: "Tide state").

Primary source: WorldTides API v3 — real harmonic tide-station predictions,
the closest thing to an official tide table. Requires `tide_api_key`
(WorldTides' free tier is a small one-time credit grant, not a renewing
daily quota — fine for demoing, not for sustained production polling).

Fallback (2026-09-22, same reasoning as weather_collector.py's Open-Meteo
swap): when no `tide_api_key` is configured, or WorldTides itself is
unreachable, fall back to Open-Meteo's free, keyless Marine Weather API
(https://open-meteo.com/en/docs/marine-weather-api), reading its
`sea_level_height_msl` hourly series. This is a real, live, physically
grounded ocean-model output — NOT a fabricated number — but it is honestly
a different thing from a WorldTides extreme: it's referenced to mean sea
level rather than the harmonic tide-station datum, and "extremes" here are
detected as local peaks/troughs in the hourly series rather than looked up
from a station's harmonic constituents. Good enough for a rising/falling
suitability signal (which is all Table 6's "Tide state" needs); not a
substitute for an official tide table if Ground Zero ever needs one.
`TideExtreme.source` tells the caller which one it got.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from layer0.infrastructure.http_client import ResilientHttpClient, SourceUnavailable

logger = logging.getLogger("groundzero.layer0.collectors.tide")

SOURCE_NAME = "tide_api"
SOURCE_NAME_FALLBACK = "tide_api_openmeteo_marine_fallback"

DEFAULT_MARINE_FALLBACK_URL = "https://marine-api.open-meteo.com/v1/marine"


@dataclass(frozen=True)
class TideExtreme:
    timestamp: datetime
    kind: str    # "High" | "Low"
    height_meters: float
    source: str = SOURCE_NAME  # SOURCE_NAME (WorldTides) or SOURCE_NAME_FALLBACK (Open-Meteo Marine)


class TideCollector:
    def __init__(
        self,
        http_client: ResilientHttpClient,
        api_url: str,
        api_key: str | None,
        marine_fallback_url: str = DEFAULT_MARINE_FALLBACK_URL,
    ):
        self.http_client = http_client
        self.api_url = api_url
        self.api_key = api_key
        self.marine_fallback_url = marine_fallback_url

    async def extremes(self, lat: float, lon: float, days: int = 1) -> list[TideExtreme]:
        if self.api_key:
            try:
                return await self._extremes_worldtides(lat, lon, days)
            except SourceUnavailable:
                logger.warning("%s: WorldTides unavailable this run, trying free fallback", SOURCE_NAME)
                # fall through to the free fallback rather than give up outright
        else:
            logger.info("%s: TIDE_API_KEY not configured, using free Open-Meteo Marine fallback", SOURCE_NAME)

        return await self._extremes_openmeteo_marine(lat, lon, days)

    async def _extremes_worldtides(self, lat: float, lon: float, days: int) -> list[TideExtreme]:
        response = await self.http_client.request(
            SOURCE_NAME, "GET", self.api_url,
            params={"extremes": "", "lat": lat, "lon": lon, "days": days, "key": self.api_key},
        )
        data = response.json()
        extremes: list[TideExtreme] = []
        for entry in data.get("extremes", []):
            extremes.append(
                TideExtreme(
                    timestamp=datetime.fromtimestamp(entry["dt"], tz=timezone.utc),
                    kind=entry.get("type", "Unknown"),
                    height_meters=entry.get("height", 0.0),
                    source=SOURCE_NAME,
                )
            )
        return extremes

    async def _extremes_openmeteo_marine(self, lat: float, lon: float, days: int) -> list[TideExtreme]:
        try:
            response = await self.http_client.request(
                SOURCE_NAME_FALLBACK, "GET", self.marine_fallback_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "sea_level_height_msl",
                    "timezone": "UTC",  # explicit UTC (not "auto") so timestamps below are unambiguous
                    "forecast_days": max(1, days),
                },
            )
        except SourceUnavailable:
            logger.warning("%s: source unavailable this run", SOURCE_NAME_FALLBACK)
            raise

        data = response.json()
        hourly = data.get("hourly", {})
        times: list[str] = hourly.get("time", [])
        heights: list[float | None] = hourly.get("sea_level_height_msl", [])

        if not times or not heights or all(h is None for h in heights):
            # Coordinate is off the marine model's ocean grid (e.g. a river
            # mouth or lagoon pixel) — same "don't fake it" rule as
            # everywhere else in this codebase: no data in, no data out.
            raise SourceUnavailable(SOURCE_NAME_FALLBACK, "no marine grid data at this coordinate")

        return self._local_extrema(times, heights)

    @staticmethod
    def _local_extrema(times: list[str], heights: list[float | None]) -> list[TideExtreme]:
        """Turn an hourly sea-level series into High/Low points by finding
        local peaks and troughs — the same shape a real tide curve has,
        just derived from a continuous series instead of looked up from
        harmonic constituents."""
        extremes: list[TideExtreme] = []
        for i in range(1, len(heights) - 1):
            prev_h, curr_h, next_h = heights[i - 1], heights[i], heights[i + 1]
            if prev_h is None or curr_h is None or next_h is None:
                continue
            if curr_h > prev_h and curr_h >= next_h:
                kind = "High"
            elif curr_h < prev_h and curr_h <= next_h:
                kind = "Low"
            else:
                continue
            extremes.append(
                TideExtreme(
                    # UTC requested explicitly above, so this is always
                    # naive-but-actually-UTC — attach tzinfo so it compares
                    # cleanly against the tz-aware `now` in current_state().
                    timestamp=datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc),
                    kind=kind,
                    height_meters=round(curr_h, 3),
                    source=SOURCE_NAME_FALLBACK,
                )
            )
        return extremes

    def current_state(self, extremes: list[TideExtreme], now: datetime | None = None) -> str:
        """Rough state ('rising'/'falling'/'unknown') from surrounding
        extremes — good enough for a suitability signal, not a navigation
        chart."""
        now = now or datetime.now(timezone.utc)
        future = sorted((e for e in extremes if e.timestamp >= now), key=lambda e: e.timestamp)
        if not future:
            return "unknown"
        return "falling" if future[0].kind == "Low" else "rising"
