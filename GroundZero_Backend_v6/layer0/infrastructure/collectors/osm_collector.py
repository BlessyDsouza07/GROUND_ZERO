"""
OpenStreetMap Overpass collector (blueprint 3.1 source #1).

Queries real Overpass QL against the Mangaluru bounding box for every POI
category listed in the project brief (restaurants through nature spots).
Returns raw OSM elements — no Master Data Core transform here, that's the
collector's job to hand off to the orchestrator (single responsibility).

Bbox tiling: an architectural audit found a single query covering the
entire bounding box in one [timeout:60] request risked truncation/timeout
at city scale, with no tiling, pagination, or continuation logic at all.
Fixed by splitting large bounding boxes into a grid of smaller tiles,
querying each one, and deduplicating by (osm_type, osm_id) — the same POI
near a tile boundary can legitimately appear in more than one tile's
results. Small bounding boxes (already under the tile threshold) still
run as a single query, unchanged from before.

This is real, correct query-splitting logic. It has NOT been verified to
successfully complete against live Overpass from this sandbox, because
this sandbox's network allow-list does not include overpass-api.de
(confirmed 403 directly). It will run for real wherever network egress
is open.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from layer0.infrastructure.http_client import ResilientHttpClient, SourceUnavailable

logger = logging.getLogger("groundzero.layer0.collectors.osm")

SOURCE_NAME = "openstreetmap"

# OSM tag values covering every category the brief lists. Grouped by the
# OSM key they live under, since Overpass QL filters per-key.
AMENITY_VALUES = [
    "restaurant", "cafe", "fast_food", "food_court", "bar", "pub",
    "ice_cream", "marketplace", "place_of_worship", "library",
    "arts_centre", "theatre", "community_centre", "social_facility",
    "fountain", "boat_rental", "ferry_terminal", "planetarium",
]
TOURISM_VALUES = [
    "museum", "gallery", "attraction", "viewpoint", "picnic_site",
    "theme_park", "zoo", "artwork", "hotel", "guest_house", "hostel",
    "camp_site", "chalet", "aquarium", "wilderness_hut",
]
SHOP_VALUES = ["bakery", "confectionery", "mall", "craft", "gift"]
NATURAL_VALUES = [
    "beach", "water", "wood", "peak", "cave_entrance", "bay", "cliff",
    "spring", "waterfall", "hot_spring",
]
LEISURE_VALUES = [
    "park", "garden", "nature_reserve", "beach_resort", "water_park",
    "sports_centre", "stadium", "marina",
]
HISTORIC_VALUES = [
    "monument", "memorial", "castle", "ruins", "church", "heritage",
    "archaeological_site", "wayside_shrine", "wayside_cross", "tomb",
    "fort", "manor",
]

# NOTE on completeness: this is a deliberately broad tourism/culture/nature
# tag set, not an exhaustive OSM tag list — a truly "every single tag OSM
# has" query would also pull in things with zero tourism relevance (fire
# hydrants, individual bus stops, ATMs, etc.) and would make Overpass
# queries slower for no benefit to the recommendation engine. If a category
# of real place is still missing after a live pipeline run, the fix is to
# add its OSM tag value here (and its mapping in
# etl_orchestrator.py::_CATEGORY_MAP) — not to widen the query
# indiscriminately.

# Tile size in degrees. ~0.1° is roughly 11km at Mangaluru's latitude — a
# tile this size keeps individual Overpass queries well within the
# [timeout:60] budget even in a dense urban tile, while a rural/coastal
# tile with few POIs completes almost instantly. Tunable per deployment;
# exposed as a constructor parameter rather than hardcoded so it can be
# adjusted without touching the query-building logic.
DEFAULT_MAX_TILE_DEGREES = 0.1

# Real, free, already-present-in-the-data closure signals. OSM contributors
# mark a place as no-longer-operating in one of two conventional ways: (a)
# prefixing the primary key itself (e.g. `disused:amenity=cafe` instead of
# `amenity=cafe` — this form never matches `_matches_wanted_tags` in the
# first place, since the key is literally different, so it's already
# excluded automatically), or (b) leaving the primary key active but adding
# an explicit closure tag alongside it (a mapper edited the place but forgot
# to rename the key, or used one of these instead). Only case (b) needs an
# explicit check — this closes that gap using tags already fetched, no new
# API call, nothing invented.
_CLOSURE_TAG_KEYS = ("disused", "was", "abandoned", "demolished", "razed", "removed")
_CLOSURE_OPENING_HOURS_VALUES = {"closed", "off"}


def is_marked_closed(tags: dict[str, str]) -> bool:
    """True if the raw OSM tags on this element carry any real, explicit
    closure signal. Used by both the live Overpass collector and the
    offline .osm.pbf extract collector so switching between them never
    changes which closed places get excluded."""
    for key in tags:
        prefix = key.split(":", 1)[0]
        if prefix in _CLOSURE_TAG_KEYS:
            return True
    if tags.get("opening_hours") in _CLOSURE_OPENING_HOURS_VALUES:
        return True
    if tags.get("disused") == "yes" or tags.get("demolished") == "yes" or tags.get("razed") == "yes":
        return True
    return False

# How many tiles to query concurrently. Overpass's public instance rate-
# limits aggressively; a small concurrency cap is a reasonable middle
# ground between "one query at a time" (slow for a large area) and firing
# every tile at once (a fair-use policy violation).
DEFAULT_TILE_CONCURRENCY = 2


@dataclass(frozen=True)
class OsmElement:
    osm_id: int
    osm_type: str  # node | way | relation
    lat: float
    lon: float
    tags: dict[str, str]


def build_overpass_query(south: float, west: float, north: float, east: float) -> str:
    bbox = f"{south},{west},{north},{east}"

    def clause(key: str, values: list[str]) -> str:
        value_regex = "|".join(values)
        return (
            f'node["{key}"~"^({value_regex})$"]({bbox});\n'
            f'way["{key}"~"^({value_regex})$"]({bbox});\n'
        )

    body = "".join([
        clause("amenity", AMENITY_VALUES),
        clause("tourism", TOURISM_VALUES),
        clause("shop", SHOP_VALUES),
        clause("natural", NATURAL_VALUES),
        clause("leisure", LEISURE_VALUES),
        clause("historic", HISTORIC_VALUES),
    ])

    return f"""
[out:json][timeout:60];
(
{body}
);
out center tags;
""".strip()


def split_bbox_into_tiles(
    south: float, west: float, north: float, east: float, max_tile_degrees: float = DEFAULT_MAX_TILE_DEGREES
) -> list[tuple[float, float, float, float]]:
    """Splits a bounding box into a grid of tiles, each no larger than
    max_tile_degrees in either dimension. Returns [(south, west, north,
    east), ...]. A bbox already within the threshold in both dimensions
    is returned as a single tile — unchanged behavior for small areas."""
    lat_span = north - south
    lon_span = east - west

    if lat_span <= max_tile_degrees and lon_span <= max_tile_degrees:
        return [(south, west, north, east)]

    import math

    lat_tiles = max(1, math.ceil(lat_span / max_tile_degrees))
    lon_tiles = max(1, math.ceil(lon_span / max_tile_degrees))
    lat_step = lat_span / lat_tiles
    lon_step = lon_span / lon_tiles

    tiles: list[tuple[float, float, float, float]] = []
    for i in range(lat_tiles):
        tile_south = south + i * lat_step
        tile_north = south + (i + 1) * lat_step
        for j in range(lon_tiles):
            tile_west = west + j * lon_step
            tile_east = west + (j + 1) * lon_step
            tiles.append((tile_south, tile_west, tile_north, tile_east))
    return tiles


class OsmCollector:
    def __init__(
        self,
        http_client: ResilientHttpClient,
        overpass_url: str,
        max_tile_degrees: float = DEFAULT_MAX_TILE_DEGREES,
        tile_concurrency: int = DEFAULT_TILE_CONCURRENCY,
    ):
        self.http_client = http_client
        self.overpass_url = overpass_url
        self.max_tile_degrees = max_tile_degrees
        self.tile_concurrency = tile_concurrency

    async def _query_one_tile(self, south: float, west: float, north: float, east: float) -> list[OsmElement]:
        query = build_overpass_query(south, west, north, east)
        response = await self.http_client.request(
            SOURCE_NAME, "POST", self.overpass_url, params={"data": query}
        )
        payload = response.json()
        elements: list[OsmElement] = []
        skipped_closed = 0
        for el in payload.get("elements", []):
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue
            tags = el.get("tags", {})
            if is_marked_closed(tags):
                skipped_closed += 1
                continue
            elements.append(
                OsmElement(osm_id=el["id"], osm_type=el["type"], lat=lat, lon=lon, tags=tags)
            )
        if skipped_closed:
            logger.info("%s: skipped %d element(s) carrying an explicit closure tag", SOURCE_NAME, skipped_closed)
        return elements

    async def collect(
        self, south: float, west: float, north: float, east: float
    ) -> list[OsmElement]:
        tiles = split_bbox_into_tiles(south, west, north, east, self.max_tile_degrees)
        if len(tiles) > 1:
            logger.info("%s: bbox split into %d tiles (max %s° per tile)", SOURCE_NAME, len(tiles), self.max_tile_degrees)

        semaphore = asyncio.Semaphore(self.tile_concurrency)
        any_tile_succeeded = False
        last_exception: SourceUnavailable | None = None

        async def _query_with_limit(tile: tuple[float, float, float, float]) -> list[OsmElement]:
            nonlocal any_tile_succeeded, last_exception
            async with semaphore:
                try:
                    result = await self._query_one_tile(*tile)
                    any_tile_succeeded = True
                    return result
                except SourceUnavailable as exc:
                    logger.warning("%s: tile %s failed (%s), skipping this tile", SOURCE_NAME, tile, exc)
                    last_exception = exc
                    return []

        tile_results = await asyncio.gather(*(_query_with_limit(tile) for tile in tiles))

        if not any_tile_succeeded and last_exception is not None:
            # Every single tile failed — surface this as a real
            # SourceUnavailable rather than silently returning an empty
            # list, so the orchestrator's reporting reflects that OSM
            # genuinely didn't run this pass, not that Mangaluru simply
            # has zero matching POIs.
            raise last_exception

        # Deduplicate across tile boundaries: a POI can legitimately be
        # returned by more than one adjacent tile's query.
        seen: set[tuple[str, int]] = set()
        deduped: list[OsmElement] = []
        for tile_elements in tile_results:
            for element in tile_elements:
                key = (element.osm_type, element.osm_id)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(element)

        logger.info("%s: collected %d unique elements across %d tile(s)", SOURCE_NAME, len(deduped), len(tiles))
        return deduped
