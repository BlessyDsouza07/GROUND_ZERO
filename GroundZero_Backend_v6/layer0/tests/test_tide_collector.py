from datetime import datetime, timezone

import pytest

from layer0.infrastructure.collectors.tide_collector import (
    SOURCE_NAME,
    SOURCE_NAME_FALLBACK,
    TideCollector,
)
from layer0.infrastructure.http_client import SourceUnavailable


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeHttpClient:
    """Routes by `source` (the first positional arg TideCollector passes to
    `.request()`), matching the FakeHttpClient pattern used elsewhere in
    this test suite (see test_osm_collector.py)."""

    def __init__(self, responses: dict[str, dict], fail_sources: set[str] | None = None):
        self.responses = responses
        self.fail_sources = fail_sources or set()
        self.calls: list[str] = []

    async def request(self, source, method, url, *, params=None, json_body=None):
        self.calls.append(source)
        if source in self.fail_sources:
            raise SourceUnavailable(source, "simulated failure")
        return FakeResponse(self.responses[source])


WORLDTIDES_PAYLOAD = {
    "extremes": [
        {"dt": 1758510000, "type": "High", "height": 1.8},
        {"dt": 1758531600, "type": "Low", "height": 0.3},
    ]
}

# A day-ish of hourly sea-level heights with one clean peak and one clean
# trough — enough to prove the local-extrema detector finds both and
# ignores everything in between.
MARINE_TIMES = [f"2026-09-22T{h:02d}:00" for h in range(8)]
MARINE_HEIGHTS = [0.2, 0.5, 0.9, 1.1, 0.8, 0.4, 0.1, 0.3]
#                  0    1    2    3    4    5    6    7
# rises to a peak at index 3 (1.1), falls to a trough at index 6 (0.1)
MARINE_PAYLOAD = {"hourly": {"time": MARINE_TIMES, "sea_level_height_msl": MARINE_HEIGHTS}}

MARINE_NO_DATA_PAYLOAD = {"hourly": {"time": MARINE_TIMES, "sea_level_height_msl": [None] * len(MARINE_TIMES)}}


@pytest.mark.asyncio
async def test_uses_worldtides_when_api_key_configured():
    http = FakeHttpClient({SOURCE_NAME: WORLDTIDES_PAYLOAD})
    collector = TideCollector(http, "https://www.worldtides.info/api/v3", api_key="real-key")

    extremes = await collector.extremes(12.9, 74.8)

    assert http.calls == [SOURCE_NAME]
    assert len(extremes) == 2
    assert extremes[0].kind == "High"
    assert extremes[0].height_meters == 1.8
    assert extremes[0].source == SOURCE_NAME
    assert extremes[0].timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_falls_back_to_openmeteo_marine_when_no_api_key():
    http = FakeHttpClient({SOURCE_NAME_FALLBACK: MARINE_PAYLOAD})
    collector = TideCollector(http, "https://www.worldtides.info/api/v3", api_key=None)

    extremes = await collector.extremes(12.9, 74.8)

    assert http.calls == [SOURCE_NAME_FALLBACK]  # never even tried WorldTides
    assert all(e.source == SOURCE_NAME_FALLBACK for e in extremes)


@pytest.mark.asyncio
async def test_falls_back_when_worldtides_itself_is_unreachable():
    http = FakeHttpClient(
        {SOURCE_NAME_FALLBACK: MARINE_PAYLOAD},
        fail_sources={SOURCE_NAME},
    )
    collector = TideCollector(http, "https://www.worldtides.info/api/v3", api_key="real-key-but-service-down")

    extremes = await collector.extremes(12.9, 74.8)

    assert http.calls == [SOURCE_NAME, SOURCE_NAME_FALLBACK]  # tried WorldTides first, then fell back
    assert len(extremes) > 0
    assert all(e.source == SOURCE_NAME_FALLBACK for e in extremes)


@pytest.mark.asyncio
async def test_local_extrema_detection_finds_the_one_peak_and_one_trough():
    http = FakeHttpClient({SOURCE_NAME_FALLBACK: MARINE_PAYLOAD})
    collector = TideCollector(http, "https://www.worldtides.info/api/v3", api_key=None)

    extremes = await collector.extremes(12.9, 74.8)

    highs = [e for e in extremes if e.kind == "High"]
    lows = [e for e in extremes if e.kind == "Low"]
    assert len(highs) == 1 and highs[0].height_meters == 1.1
    assert len(lows) == 1 and lows[0].height_meters == 0.1


@pytest.mark.asyncio
async def test_raises_when_coordinate_is_off_the_marine_grid():
    http = FakeHttpClient({SOURCE_NAME_FALLBACK: MARINE_NO_DATA_PAYLOAD})
    collector = TideCollector(http, "https://www.worldtides.info/api/v3", api_key=None)

    with pytest.raises(SourceUnavailable):
        await collector.extremes(12.9, 74.8)  # e.g. a river-mouth pixel with no ocean-model data


@pytest.mark.asyncio
async def test_current_state_works_on_fallback_extremes_without_tz_crash():
    http = FakeHttpClient({SOURCE_NAME_FALLBACK: MARINE_PAYLOAD})
    collector = TideCollector(http, "https://www.worldtides.info/api/v3", api_key=None)
    extremes = await collector.extremes(12.9, 74.8)

    # a moment between the peak (index 3, 03:00) and the trough (index 6, 06:00) -> falling
    now = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
    assert collector.current_state(extremes, now=now) == "falling"
