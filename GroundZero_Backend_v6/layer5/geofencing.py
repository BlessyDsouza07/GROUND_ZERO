"""
Layer 5 Feature: Geofencing Engine

Phase 4 Implementation (Aug 5 2026): GPS-based place detection
Triggers narration when user enters/exits geofence around places.

Key features:
- Real-time GPS tracking (background)
- Geofence boundary detection
- Entry/exit event triggers
- Optimized battery usage
- Offline geofence caching
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, TYPE_CHECKING, Iterable
import math

if TYPE_CHECKING:  # pragma: no cover
    from layer0.domain.entities import Place

logger = logging.getLogger("groundzero.layer5.geofencing")

# Geofence radius in meters (default: 100m around each place)
DEFAULT_GEOFENCE_RADIUS_M = 100
# Minimum accuracy for GPS coordinates (meters)
MIN_GPS_ACCURACY_M = 50
# Check interval for geofence updates (seconds)
CHECK_INTERVAL_S = 5


@dataclass
class GPSCoordinate:
    """GPS location with accuracy."""
    latitude: float
    longitude: float
    accuracy_m: float
    timestamp: datetime

    def distance_to(self, lat: float, lon: float) -> float:
        """Calculate distance to coordinates in meters using Haversine formula."""
        R = 6371000  # Earth radius in meters
        
        lat1, lon1 = self.latitude, self.longitude
        lat2, lon2 = lat, lon
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c

    @property
    def is_accurate_enough(self) -> bool:
        """Check if accuracy is good enough for geofencing."""
        return self.accuracy_m <= MIN_GPS_ACCURACY_M


@dataclass
class Geofence:
    """Geofence definition for a place."""
    place_id: str
    place_name: str
    latitude: float
    longitude: float
    radius_m: float = DEFAULT_GEOFENCE_RADIUS_M
    narration_text: str = ""
    narration_audio_url: Optional[str] = None


@dataclass
class GeofenceEvent:
    """Geofence entry/exit event."""
    event_type: str  # "entry" or "exit"
    place_id: str
    place_name: str
    timestamp: datetime
    latitude: float
    longitude: float


class GeofencingEngine:
    """
    Manages geofences and detects when user enters/exits them.
    """

    def __init__(self):
        self.geofences: dict[str, Geofence] = {}
        self.active_geofences: set[str] = set()  # Currently inside
        self.on_entry_callback: Optional[Callable[[GeofenceEvent], None]] = None
        self.on_exit_callback: Optional[Callable[[GeofenceEvent], None]] = None
        self.is_running = False
        self.last_gps: Optional[GPSCoordinate] = None

    def add_geofence(self, geofence: Geofence) -> None:
        """Add a geofence for a place."""
        self.geofences[geofence.place_id] = geofence
        logger.debug("Added geofence for %s (%s)", geofence.place_name, geofence.place_id)

    def remove_geofence(self, place_id: str) -> None:
        """Remove a geofence."""
        if place_id in self.geofences:
            del self.geofences[place_id]
            self.active_geofences.discard(place_id)
            logger.debug("Removed geofence for %s", place_id)

    def add_geofences(self, geofences: list[Geofence]) -> None:
        """Add multiple geofences."""
        for geofence in geofences:
            self.add_geofence(geofence)
        logger.info("Added %d geofences", len(geofences))

    def update_gps(self, gps: GPSCoordinate) -> list[GeofenceEvent]:
        """
        Update current GPS location and check geofence intersections.
        
        Returns list of geofence events (entries/exits).
        """
        self.last_gps = gps
        events = []

        if not gps.is_accurate_enough:
            logger.debug("GPS accuracy %.1fm insufficient (need <%dm)", gps.accuracy_m, MIN_GPS_ACCURACY_M)
            return events

        # Check all geofences
        for place_id, geofence in self.geofences.items():
            distance = gps.distance_to(geofence.latitude, geofence.longitude)
            is_inside = distance <= geofence.radius_m
            was_inside = place_id in self.active_geofences

            if is_inside and not was_inside:
                # Entry event
                self.active_geofences.add(place_id)
                event = GeofenceEvent(
                    event_type="entry",
                    place_id=place_id,
                    place_name=geofence.place_name,
                    timestamp=datetime.now(timezone.utc),
                    latitude=gps.latitude,
                    longitude=gps.longitude,
                )
                events.append(event)
                logger.info("Geofence ENTRY: %s (distance: %.0fm)", geofence.place_name, distance)
                if self.on_entry_callback:
                    self.on_entry_callback(event)

            elif not is_inside and was_inside:
                # Exit event
                self.active_geofences.discard(place_id)
                event = GeofenceEvent(
                    event_type="exit",
                    place_id=place_id,
                    place_name=geofence.place_name,
                    timestamp=datetime.now(timezone.utc),
                    latitude=gps.latitude,
                    longitude=gps.longitude,
                )
                events.append(event)
                logger.info("Geofence EXIT: %s (distance: %.0fm)", geofence.place_name, distance)
                if self.on_exit_callback:
                    self.on_exit_callback(event)

        return events

    async def start_monitoring(self, gps_stream_callback: Callable[[], GPSCoordinate]) -> None:
        """
        Start monitoring geofences with continuous GPS updates.
        
        gps_stream_callback: Async function that returns current GPS coordinate
        """
        self.is_running = True
        logger.info("Geofencing monitoring started")

        try:
            while self.is_running:
                try:
                    # Get current GPS
                    gps = await gps_stream_callback()
                    
                    # Check geofences
                    self.update_gps(gps)
                    
                    # Wait before next check
                    await asyncio.sleep(CHECK_INTERVAL_S)

                except Exception as e:
                    logger.error("Error during geofence check: %s", e)
                    await asyncio.sleep(CHECK_INTERVAL_S)

        finally:
            self.is_running = False
            logger.info("Geofencing monitoring stopped")

    def stop_monitoring(self) -> None:
        """Stop geofence monitoring."""
        self.is_running = False

    def get_active_geofences(self) -> list[Geofence]:
        """Get list of geofences currently active (user inside)."""
        return [self.geofences[place_id] for place_id in self.active_geofences]

    def get_nearby_geofences(self, radius_m: float = 500) -> list[tuple[Geofence, float]]:
        """
        Get geofences within radius, with distances.
        
        Returns list of (geofence, distance_m) tuples sorted by distance.
        """
        if not self.last_gps:
            return []

        nearby = []
        for geofence in self.geofences.values():
            distance = self.last_gps.distance_to(geofence.latitude, geofence.longitude)
            if distance <= radius_m:
                nearby.append((geofence, distance))

        return sorted(nearby, key=lambda x: x[1])


def geofences_from_places(places: Iterable["Place"]) -> list[Geofence]:
    """Build real `Geofence` objects from Layer 0 `Place` records.

    Before this fix, nothing in the codebase ever called `add_geofence`/
    `add_geofences` with real data — `GeofencingEngine` only ever saw
    whatever a caller manually constructed, which was nothing, since no
    caller existed. `layer5/api/routes.py` uses this to seed the engine
    from the real place catalog so entry/exit narration triggers on
    genuine Mangaluru places instead of never firing at all.

    Skips places with no coordinates (shouldn't happen — `Place.coordinates`
    is required — but this stays defensive rather than crashing a whole
    geofence load over one bad record) and never fabricates narration
    text: falls back to a plain "Welcome to {name}" only when the place
    has no `description`, rather than inventing facts about it.
    """
    fences: list[Geofence] = []
    for place in places:
        if place.id is None:
            continue
        if place.coordinates.latitude is None or place.coordinates.longitude is None:
            logger.debug("Skipping geofence for %s — missing coordinates", place.name)
            continue
        narration = place.description or f"Welcome to {place.name}."
        fences.append(
            Geofence(
                place_id=place.id,
                place_name=place.name,
                latitude=place.coordinates.latitude,
                longitude=place.coordinates.longitude,
                narration_text=narration,
            )
        )
    return fences
