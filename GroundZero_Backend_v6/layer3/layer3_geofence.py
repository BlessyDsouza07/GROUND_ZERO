"""
Geofence — the proximity trigger (Blueprint §6: 300 m approach zone).

Only slots that are still `pending` and have a real place can trigger. A slot that was
already notified / visited / replaced can never trigger again ("geofence silence").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from layer3_bridge import MasterCoreStore
from layer3_utils import haversine_m, place_latlng


@dataclass
class GeoCandidate:
    slot_index: int
    slot: Dict[str, Any]
    place: Dict[str, Any]
    distance_m: float


class GeofenceEngine:
    def __init__(self, radius_m: float, boundary_m: float, release_m: float):
        self.radius_m = radius_m
        self.boundary_m = boundary_m
        self.release_m = release_m

    def candidates(self, queue: List[Dict[str, Any]], master: MasterCoreStore, lat: float, lng: float,
                   only_within_radius: bool = True) -> List[GeoCandidate]:
        out: List[GeoCandidate] = []
        for i, slot in enumerate(queue):
            if slot.get("status") != "pending" or not slot.get("place_id"):
                continue
            place = master.get(slot["place_id"])
            ll = place_latlng(place) if place else None
            if not place or not ll:
                continue
            d = haversine_m(lat, lng, ll[0], ll[1])
            if only_within_radius and d > self.radius_m:
                continue
            out.append(GeoCandidate(i, slot, place, d))
        out.sort(key=lambda c: c.distance_m)
        return out

    @staticmethod
    def next_pending(queue: List[Dict[str, Any]], master: MasterCoreStore, target_place_id: Optional[str] = None) -> Optional[GeoCandidate]:
        """Manual 'I'm here' — the next slot in the queue (or an explicit target), ignoring distance."""
        for i, slot in enumerate(queue):
            if slot.get("status") != "pending" or not slot.get("place_id"):
                continue
            if target_place_id and slot["place_id"] != str(target_place_id):
                continue
            place = master.get(slot["place_id"])
            if place:
                return GeoCandidate(i, slot, place, -1.0)
        return None

    def distance_to(self, place: Dict[str, Any], lat: Optional[float], lng: Optional[float]) -> Optional[float]:
        ll = place_latlng(place)
        if not ll or lat is None or lng is None:
            return None
        return haversine_m(lat, lng, ll[0], ll[1])
