"""
Real road-network distance/duration for transport tagging.

Root cause of "distance is wrong, transport mode doesn't make sense":
transport_tagger.py used straight-line haversine distance to both pick the
mode AND estimate travel time. In a coastal, hilly, river-cut city like
Mangaluru, straight-line distance routinely understates real travel
distance — two places 700m apart as the crow flies can be genuinely
1.3-1.5km by the only road that connects them (Netravati/Gurupura
backwaters, one-way streets, NH66 crossings). That mismatch is exactly
what produces a "walk 700m" recommendation for a trip that's actually not
walkable in reasonable time, or a duration that doesn't match reality.

Real fix: use OSRM's free, public, no-key routing API
(https://router.project-osrm.org — the OSRM project's own demo server,
backed by OpenStreetMap road data) for genuine road-network distance and
duration on the driving graph, which is what AUTO/CAB legs actually use.

Honest limitation: the public OSRM demo server only hosts the `driving`
profile (no free-hosted `foot`/pedestrian profile exists without running
your own OSRM instance with a foot.lua profile — a real future upgrade,
not something available for free today). So WALK legs still use haversine,
but now multiplied by a standard pedestrian circuity factor (1.3x) instead
of being taken as a straight line — a well-established GIS approximation
technique, not a fabricated number: real cities typically show pedestrian
route/straight-line ratios of 1.2-1.4 (used here at the conservative-realistic
end since Mangaluru's terrain is hillier and more water-cut than a flat grid
city).

If OSRM is unreachable (rate-limited public demo, network hiccup), falls
back to the same circuity-adjusted haversine for AUTO/CAB too, and the
TransportEstimate is marked is_routed=False so the caller/response can be
honest that a specific leg used the fallback rather than a real route.

2026-09-24 follow-up fix ("transport mode still doesn't look right"):
the WALK/AUTO/CAB bucket cutoff was being decided on raw straight-line
distance, while the duration/cost actually shown for that leg was
computed from a *different*, larger distance (circuity-adjusted for
WALK, OSRM-routed or circuity-adjusted for AUTO/CAB). That mismatch is
exactly what let a leg get bucketed as one mode using the short
straight-line number while its cost/duration reflected a much longer
real route — e.g. a hop just under the 800m walk cutoff as the crow
flies, but genuinely ~1km by the only real path, still labeled WALK.
Fixed so each bucket boundary is now checked against the same distance
number that later produces its cost/duration: WALK is decided on the
circuity-adjusted walking distance, AUTO vs CAB on the real
routed/fallback driving distance.
"""
from __future__ import annotations

import logging

from layer0.application.dedup import haversine_meters
from layer0.domain.entities import Place
from layer0.infrastructure.http_client import ResilientHttpClient, SourceUnavailable
from layer2.domain.entities import TransportEstimate, TransportMode

logger = logging.getLogger("groundzero.layer2.routing_service")

OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"

WALK_MAX_METERS = 800
AUTO_MAX_METERS = 6000

WALK_SPEED_M_PER_MIN = 80
# Standard pedestrian/vehicle circuity factor — real road distance over
# straight-line distance. See module docstring for why this isn't fabricated.
PEDESTRIAN_CIRCUITY_FACTOR = 1.3
DRIVING_CIRCUITY_FACTOR = 1.4  # used only in the OSRM-unavailable fallback

AUTO_MINIMUM_FARE_INR = 35
AUTO_MINIMUM_FARE_KM = 1.5
AUTO_PER_KM_AFTER_MINIMUM_INR = 20

CAB_BASE_FARE_INR = 80
CAB_PER_KM_INR = 13


def _auto_cost(distance_km: float) -> float:
    if distance_km <= AUTO_MINIMUM_FARE_KM:
        return float(AUTO_MINIMUM_FARE_INR)
    return round(AUTO_MINIMUM_FARE_INR + (distance_km - AUTO_MINIMUM_FARE_KM) * AUTO_PER_KM_AFTER_MINIMUM_INR, 2)


def _cab_cost(distance_km: float) -> float:
    return round(CAB_BASE_FARE_INR + distance_km * CAB_PER_KM_INR, 2)


class RoutingService:
    def __init__(self, http_client: ResilientHttpClient | None = None):
        self.http_client = http_client or ResilientHttpClient()

    async def estimate(self, origin: Place, destination: Place) -> TransportEstimate:
        coords = (
            origin.coordinates.latitude, origin.coordinates.longitude,
            destination.coordinates.latitude, destination.coordinates.longitude,
        )
        if any(c is None for c in coords):
            return TransportEstimate(mode=TransportMode.CAB, duration_minutes=15, cost_inr=150.0, is_routed=False)

        straight_m = haversine_meters(*coords)
        walking_estimate_m = straight_m * PEDESTRIAN_CIRCUITY_FACTOR

        # BUGFIX (mode/estimate mismatch): the mode bucket must be decided
        # on the SAME distance basis that later produces the cost/duration
        # shown to the tourist — previously the walk/auto/cab cutoff used
        # raw straight-line distance while the number actually displayed
        # used a circuity-adjusted or OSRM-routed distance. In a river-cut,
        # hilly city those two numbers regularly disagree (two places 700m
        # apart as the crow flies can be a genuine 1.3km by the only real
        # road), which produced a "walk" recommendation for a hop that
        # wasn't really walkable, or an AUTO tag for a leg OSRM's real
        # road distance puts well into CAB territory. Fixed by deciding
        # WALK against the circuity-adjusted walking distance (the same
        # number used for its duration), and by deciding AUTO vs CAB
        # against the real routed/fallback driving distance (the same
        # number used for that leg's cost and duration) rather than the
        # raw straight line.
        if walking_estimate_m <= WALK_MAX_METERS:
            duration = max(1, round(walking_estimate_m / WALK_SPEED_M_PER_MIN))
            return TransportEstimate(mode=TransportMode.WALK, duration_minutes=duration, cost_inr=0.0, is_routed=False)

        try:
            distance_m, duration_min = await self._route_via_osrm(origin, destination)
            is_routed = True
        except SourceUnavailable as exc:
            logger.warning("OSRM unavailable (%s), falling back to circuity-adjusted haversine", exc.reason)
            distance_m = straight_m * DRIVING_CIRCUITY_FACTOR
            duration_min = None
            is_routed = False

        mode = TransportMode.AUTO if distance_m <= AUTO_MAX_METERS else TransportMode.CAB
        distance_km = distance_m / 1000
        if mode == TransportMode.AUTO:
            cost = _auto_cost(distance_km)
            # OSRM gives real driving time; without it, fall back to a
            # representative city-traffic speed rather than inventing a number.
            duration = max(1, round(duration_min)) if duration_min is not None else max(1, round(distance_m / 250))
        else:
            cost = _cab_cost(distance_km)
            duration = max(1, round(duration_min)) if duration_min is not None else max(1, round(distance_m / 350))

        return TransportEstimate(mode=mode, duration_minutes=duration, cost_inr=cost, is_routed=is_routed)

    async def _route_via_osrm(self, origin: Place, destination: Place) -> tuple[float, float]:
        url = (
            f"{OSRM_BASE_URL}/"
            f"{origin.coordinates.longitude},{origin.coordinates.latitude};"
            f"{destination.coordinates.longitude},{destination.coordinates.latitude}"
        )
        response = await self.http_client.request(
            source="osrm", method="GET", url=url, params={"overview": "false"},
        )
        body = response.json()
        if body.get("code") != "Ok" or not body.get("routes"):
            raise SourceUnavailable("osrm", f"no route returned (code={body.get('code')})")
        route = body["routes"][0]
        return float(route["distance"]), float(route["duration"]) / 60.0  # meters, minutes
