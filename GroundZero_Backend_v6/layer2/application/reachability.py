"""
Reachability radius filter (closes the gap in blueprint 5.1's second Hard
Filter bullet: "Place is outside the tourist's reachable time-and-distance
budget for their trip_duration" — this was never implemented; no code
anywhere read a tourist's location at recommendation time).

This is the "geofence around the tourist" Carol asked for: as soon as the
app has the tourist's current position, HIVE should only even consider
places within a real radius of it — not the whole Master Data Core — and
that radius should be FIXED by default (driven by how much time the
tourist has) but ADJUST wider if the immediate area is too sparse to fill
the day. This is distinct from `layer5/geofencing.py`, which is the
100m-per-place proximity trigger that fires narration once the tourist is
already near a specific recommended place (blueprint Section 6) — that
module already exists and is unrelated to this one. This module runs once,
at recommendation-build time, to shrink the *candidate pool* itself.

Pure math, no I/O — reuses the same haversine implementation already used
by dedup.py and transport_tagger.py rather than a third copy.
"""
from __future__ import annotations

from dataclasses import dataclass

from layer0.application.dedup import haversine_meters
from layer0.domain.entities import Place
from layer1.domain.entities import TripDuration

# Base radius by trip length — how far a tourist can realistically range
# and return from within their day, at Mangaluru's city-scale road/auto/cab
# mix. These are starting points, not hard caps (see MAX_RADIUS_KM below).
_BASE_RADIUS_KM = {
    TripDuration.HALF_DAY: 6.0,
    TripDuration.FULL_DAY: 12.0,
    TripDuration.MULTI_DAY: 10.0,  # per day
}

# If the base radius doesn't contain at least this many candidates, widen
# it — a tourist standing somewhere genuinely sparse (e.g. the coast at the
# edge of the bbox) still needs a full day built for them, not an empty
# list. This is the "adjustable depending on what's actually nearby" part.
MIN_CANDIDATES_IN_RADIUS = 25
RADIUS_STEP_KM = 4.0
MAX_RADIUS_KM = 30.0  # hard ceiling — past this it's not "a day trip" anymore


@dataclass(frozen=True)
class ReachabilityResult:
    places: list[Place]
    radius_km_used: float
    was_expanded: bool


class ReachabilityService:
    def filter_by_radius(
        self,
        places: list[Place],
        center_latitude: float,
        center_longitude: float,
        trip_duration: TripDuration,
    ) -> ReachabilityResult:
        radius_km = _BASE_RADIUS_KM.get(trip_duration, _BASE_RADIUS_KM[TripDuration.FULL_DAY])
        was_expanded = False

        while True:
            within = [
                place
                for place in places
                if haversine_meters(
                    center_latitude, center_longitude,
                    place.coordinates.latitude, place.coordinates.longitude,
                ) <= radius_km * 1000.0
            ]
            if len(within) >= MIN_CANDIDATES_IN_RADIUS or radius_km >= MAX_RADIUS_KM:
                if not within:
                    # Even the widest allowed radius found NOTHING. In
                    # practice this almost never means "a tourist standing
                    # in a genuinely empty part of Mangaluru" — the dataset
                    # covers the whole city — it means the given coordinates
                    # aren't in (or anywhere near) the dataset's coverage
                    # area at all: a simulator/emulator's default location
                    # (e.g. Apple's Cupertino default, an Android emulator's
                    # (0,0) or Mountain View default), a stale/cell-tower
                    # GPS fix grabbed before a real fix locked in, or a
                    # genuine location far outside Mangaluru. A geofence
                    # that can silently zero out every place in the
                    # dataset — turning "recommend me a day" into
                    # "recommend me nothing, for any survey answer" — is
                    # worse than not geofencing at all. Fall back to the
                    # full candidate pool rather than handing back an empty
                    # queue; radius_km_used=None signals to callers that no
                    # effective geofence was applied.
                    return ReachabilityResult(places=list(places), radius_km_used=None, was_expanded=was_expanded)
                return ReachabilityResult(places=within, radius_km_used=radius_km, was_expanded=was_expanded)
            radius_km = min(MAX_RADIUS_KM, radius_km + RADIUS_STEP_KM)
            was_expanded = True
