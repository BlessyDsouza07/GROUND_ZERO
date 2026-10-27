from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

OSRM_BASE_URL = os.getenv("LAYER4_OSRM_BASE_URL", "https://router.project-osrm.org/route/v1/driving").rstrip("/")
OSRM_FALLBACK_URL = os.getenv("LAYER4_OSRM_FALLBACK_URL", "https://routing.openstreetmap.de/routed-car/route/v1/driving").rstrip("/")
TIMEOUT_S = float(os.getenv("LAYER4_ROUTING_TIMEOUT_S", "8"))


def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000.0 * 2 * math.asin(math.sqrt(h))



def dfs_shortest_path(graph: Dict[Any, Sequence[Tuple[Any, float]]], start: Any, goal: Any) -> Tuple[float, List[Any]]:
    """Exact weighted shortest path using depth-first branch-and-bound.

    This is used as the algorithmic fallback primitive for small local graphs;
    production road-network shortest paths come from OSM/OSRM because the full
    OSM graph is far too large to materialize inside the mobile app.
    """
    best_cost = math.inf
    best_path: List[Any] = []

    def dfs(node: Any, cost: float, path: List[Any], seen: set) -> None:
        nonlocal best_cost, best_path
        if cost >= best_cost:
            return
        if node == goal:
            best_cost, best_path = cost, path.copy()
            return
        for nxt, weight in graph.get(node, ()): 
            if nxt in seen:
                continue
            seen.add(nxt)
            path.append(nxt)
            dfs(nxt, cost + float(weight), path, seen)
            path.pop()
            seen.remove(nxt)

    dfs(start, 0.0, [start], {start})
    return best_cost, best_path

def _dfs_priority_order(points: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Depth-first traversal of the already-ranked queue.

    The itinerary is a priority list, so DFS is deliberately *not* allowed to
    reorder it.  It simply walks the next pending node, then its successor.
    Shortest road-path selection is delegated to OSM/OSRM for each leg.
    """
    out: List[Dict[str, Any]] = []

    def visit(i: int) -> None:
        if i >= len(points):
            return
        out.append(points[i])
        visit(i + 1)

    visit(0)
    return out


def _fallback_route(coords: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    geometry = [[lng, lat] for lat, lng in coords]
    distance = sum(haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))
    # Conservative city speed; only used when both OSM route servers fail.
    duration = distance / 5.0 * 3.6
    legs = []
    for i in range(len(coords) - 1):
        d = haversine_m(coords[i], coords[i + 1])
        legs.append({"distance": d, "duration": d / 5.0 * 3.6, "steps": []})
    return {"distance": distance, "duration": duration, "geometry": geometry, "legs": legs, "routed": False, "provider": "haversine-fallback"}


async def _osrm(url: str, coords: Sequence[Tuple[float, float]]) -> Optional[Dict[str, Any]]:
    coord_text = ";".join(f"{lng},{lat}" for lat, lng in coords)
    full = f"{url}/{coord_text}"
    params = {"overview": "full", "geometries": "geojson", "steps": "true", "annotations": "false"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=True) as client:
            r = await client.get(full, params=params)
            r.raise_for_status()
            body = r.json()
        if body.get("code") != "Ok" or not body.get("routes"):
            return None
        route = body["routes"][0]
        return {
            "distance": float(route.get("distance", 0)),
            "duration": float(route.get("duration", 0)),
            "geometry": route.get("geometry", {}).get("coordinates", []),
            "legs": route.get("legs", []),
            "routed": True,
            "provider": "osrm-osm",
        }
    except Exception:
        return None


async def shortest_priority_route(origin: Tuple[float, float], destinations: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    ordered = _dfs_priority_order(destinations)
    points: List[Tuple[float, float]] = [origin]
    for item in ordered:
        lat = item.get("lat")
        lng = item.get("lng")
        if lat is not None and lng is not None:
            points.append((float(lat), float(lng)))

    if len(points) < 2:
        return {"distance": 0, "duration": 0, "geometry": [], "legs": [], "routed": False, "provider": "none", "priority_order": ordered}

    route = await _osrm(OSRM_BASE_URL, points)
    if route is None and OSRM_FALLBACK_URL and OSRM_FALLBACK_URL != OSRM_BASE_URL:
        route = await _osrm(OSRM_FALLBACK_URL, points)
    if route is None:
        route = _fallback_route(points)
    route["priority_order"] = ordered
    route["origin"] = {"lat": origin[0], "lng": origin[1]}
    return route
