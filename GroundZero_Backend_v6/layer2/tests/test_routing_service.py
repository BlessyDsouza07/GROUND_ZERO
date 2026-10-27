"""
Covers the 2026-09-24 fix in routing_service.py: the WALK/AUTO/CAB bucket
must be decided on the SAME distance number that later produces that leg's
cost/duration, not on raw straight-line distance while a different
(circuity-adjusted or OSRM-routed) distance is what's actually shown.
"""
import pytest

from layer0.domain.entities import BiasSignals, Coordinates, OpeningHours, Place, PriceBand
from layer2.application.routing_service import RoutingService
from layer2.domain.entities import TransportMode


def _place(lat, lon) -> Place:
    return Place(
        id="p", name="P", category="cafe", coordinates=Coordinates(latitude=lat, longitude=lon),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.BUDGET, estimated_cost=0.0,
        bias_signals=BiasSignals(),
    )


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeHttpClient:
    """Stand-in for ResilientHttpClient — returns a canned OSRM-shaped
    response instead of making a real network call, so these tests don't
    depend on router.project-osrm.org being reachable."""

    def __init__(self, response_data):
        self._response_data = response_data
        self.calls = 0

    async def request(self, *args, **kwargs):
        self.calls += 1
        return _FakeResponse(self._response_data)


@pytest.mark.asyncio
async def test_mode_decided_on_routed_distance_not_straight_line():
    """~5.8km straight-line (would bucket AUTO on straight-line alone) but
    the real road route is 9km -- must come back CAB, matching the routed
    distance actually used for its cost/duration."""
    origin = _place(12.9141, 74.8560)
    destination = _place(12.95, 74.90)

    client = _FakeHttpClient({"code": "Ok", "routes": [{"distance": 9000.0, "duration": 1200.0}]})
    service = RoutingService(http_client=client)
    estimate = await service.estimate(origin, destination)

    assert estimate.mode == TransportMode.CAB
    assert estimate.is_routed is True
    assert estimate.duration_minutes == 20  # 1200s from OSRM, not a straight-line guess


@pytest.mark.asyncio
async def test_mode_stays_auto_when_routed_distance_is_short():
    origin = _place(12.9141, 74.8560)
    destination = _place(12.95, 74.90)

    client = _FakeHttpClient({"code": "Ok", "routes": [{"distance": 4000.0, "duration": 600.0}]})
    service = RoutingService(http_client=client)
    estimate = await service.estimate(origin, destination)

    assert estimate.mode == TransportMode.AUTO
    assert estimate.is_routed is True


@pytest.mark.asyncio
async def test_walk_decided_on_circuity_adjusted_distance_not_raw_straight_line():
    """~750m straight-line -- under the raw 800m cutoff, but the
    pedestrian-circuity-adjusted distance (~975m) is not, so this must NOT
    be tagged WALK."""
    origin = _place(12.9141, 74.8560)
    destination = _place(12.9141 + 0.00675, 74.8560)

    client = _FakeHttpClient({"code": "Ok", "routes": [{"distance": 1000.0, "duration": 180.0}]})
    service = RoutingService(http_client=client)
    estimate = await service.estimate(origin, destination)

    assert estimate.mode != TransportMode.WALK


@pytest.mark.asyncio
async def test_short_hop_is_still_a_free_walk():
    origin = _place(12.9141, 74.8560)
    destination = _place(12.9145, 74.8563)  # ~50m

    client = _FakeHttpClient({"code": "Ok", "routes": [{"distance": 50.0, "duration": 60.0}]})
    service = RoutingService(http_client=client)
    estimate = await service.estimate(origin, destination)

    assert estimate.mode == TransportMode.WALK
    assert estimate.cost_inr == 0.0
    assert client.calls == 0  # walk decision never needed the routed call
