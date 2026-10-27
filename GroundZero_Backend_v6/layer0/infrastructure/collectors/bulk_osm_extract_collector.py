"""
Offline OSM extract collector — the genuinely rate-limit-free, API-free
path for the widest legal free data source (OpenStreetMap).

Why this exists: the live Overpass collector (`osm_collector.py`) is
already free, legal, and respectful (tiled queries, concurrency-capped),
and for a single city it will not realistically hit Overpass's fair-use
quota. But it still makes a live network call to a third-party server
every time the pipeline runs, and Carol explicitly asked for a path with
**no API call and no rate-limit exposure at all**. This module is that
path.

How it works: OpenStreetMap publishes free, legal, ODbL-licensed bulk
extract files (`.osm.pbf` / `.osm` / `.osm.xml.gz`) that you download
*once* (or occasionally, to refresh) — not queried per-request. Once
downloaded, every read of that file happens **entirely offline, locally,
unlimited times, with zero network calls and zero rate limit** — this
is the actual mechanism, not a workaround.

Where to get the file (free, legal, no account/API key needed):

  1. Custom-area extract (recommended — smaller file, exactly your bbox):
     https://extract.bbbike.org/  → paste/draw the Mangaluru bounding box
     → format ".osm.pbf" → request extract → download the emailed link.
  2. Whole-country extract, clipped locally afterwards:
     https://download.geofabrik.de/asia/india.html → download
     `india-latest.osm.pbf` (large, ~1-2 GB) → clip it to Mangaluru
     yourself with the `osmium` CLI tool (see docs/GROWING_THE_DATABASE.md
     for the exact command) — this clipping step is also fully offline,
     no API, no rate limit.

Either way, once you have a local file, point `OSM_EXTRACT_FILE_PATH` in
`.env` at it and this collector takes over from the live Overpass one —
see `layer0/api/dependencies.py`.

This returns the exact same `OsmElement` shape the live Overpass
collector does, so nothing downstream (etl_orchestrator, dedup, bias
audit) needs to know or care which one produced a given element.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import osmium

from layer0.infrastructure.collectors.osm_collector import (
    AMENITY_VALUES,
    HISTORIC_VALUES,
    LEISURE_VALUES,
    NATURAL_VALUES,
    SHOP_VALUES,
    TOURISM_VALUES,
    OsmElement,
    is_marked_closed,
)

logger = logging.getLogger("groundzero.layer0.collectors.bulk_osm_extract")

SOURCE_NAME = "openstreetmap_offline_extract"

# Same tag vocabulary as the live Overpass collector (imported, not
# duplicated) — so switching between "live Overpass" and "offline
# extract" never changes which categories of place get collected, only
# how the raw OSM data is obtained.
_TAG_VALUES_BY_KEY: dict[str, set[str]] = {
    "amenity": set(AMENITY_VALUES),
    "tourism": set(TOURISM_VALUES),
    "shop": set(SHOP_VALUES),
    "natural": set(NATURAL_VALUES),
    "leisure": set(LEISURE_VALUES),
    "historic": set(HISTORIC_VALUES),
}


def _matches_wanted_tags(tags: osmium.osm.TagList) -> bool:
    for key, wanted_values in _TAG_VALUES_BY_KEY.items():
        value = tags.get(key)
        if value and value in wanted_values:
            return True
    return False


def _in_bbox(lat: float, lon: float, south: float, west: float, north: float, east: float) -> bool:
    return south <= lat <= north and west <= lon <= east


class _ExtractHandler(osmium.SimpleHandler):
    """Reads nodes and ways matching our tag vocabulary + bounding box
    directly out of a local extract file. Ways use their first available
    node location as a simple, dependency-free centroid approximation
    (good enough for a POI marker; not meant for precise polygon
    geometry)."""

    def __init__(self, south: float, west: float, north: float, east: float):
        super().__init__()
        self.south, self.west, self.north, self.east = south, west, north, east
        self.elements: list[OsmElement] = []

    def node(self, n: osmium.osm.Node) -> None:  # noqa: N802 - osmium's callback naming
        if not n.tags.get("name"):
            return
        if not _matches_wanted_tags(n.tags):
            return
        tags = dict(n.tags)
        if is_marked_closed(tags):
            return
        if not n.location.valid():
            return
        lat, lon = n.location.lat, n.location.lon
        if not _in_bbox(lat, lon, self.south, self.west, self.north, self.east):
            return
        self.elements.append(
            OsmElement(osm_id=n.id, osm_type="node", lat=lat, lon=lon, tags=tags)
        )

    def way(self, w: osmium.osm.Way) -> None:  # noqa: N802
        if not w.tags.get("name"):
            return
        if not _matches_wanted_tags(w.tags):
            return
        tags = dict(w.tags)
        if is_marked_closed(tags):
            return
        # True centroid of every valid node, not just the first one. A
        # large way (a park boundary, a temple complex perimeter, a beach
        # frontage) can span hundreds of metres — pinning it at whichever
        # node osmium happens to iterate to first can land the marker at a
        # far corner rather than the middle, which then feeds a genuinely
        # wrong distance into transport tagging for every neighbouring
        # slot. Averaging all valid node coordinates is a real, standard
        # polygon-centroid approximation (not exact for concave shapes,
        # but far closer to "where you'd actually enter this place" than
        # an arbitrary boundary vertex).
        lat_sum, lon_sum, count = 0.0, 0.0, 0
        for node_ref in w.nodes:
            if node_ref.location.valid():
                lat_sum += node_ref.location.lat
                lon_sum += node_ref.location.lon
                count += 1
        if count == 0:
            return
        lat, lon = lat_sum / count, lon_sum / count
        if _in_bbox(lat, lon, self.south, self.west, self.north, self.east):
            self.elements.append(
                OsmElement(osm_id=w.id, osm_type="way", lat=lat, lon=lon, tags=tags)
            )


class BulkOsmExtractCollector:
    """Drop-in replacement for `OsmCollector` with the identical
    `collect(south, west, north, east) -> list[OsmElement]` interface,
    backed by a local file instead of a live Overpass query."""

    def __init__(self, extract_file_path: str | Path):
        self.extract_file_path = Path(extract_file_path)

    def _collect_sync(self, south: float, west: float, north: float, east: float) -> list[OsmElement]:
        if not self.extract_file_path.exists():
            raise FileNotFoundError(
                f"OSM extract file not found at {self.extract_file_path}. "
                "Download one first — see the module docstring in "
                "bulk_osm_extract_collector.py or docs/GROWING_THE_DATABASE.md."
            )

        handler = _ExtractHandler(south, west, north, east)
        # locations=True resolves way-node coordinates as the file streams,
        # entirely in-memory/offline — no network access of any kind.
        handler.apply_file(str(self.extract_file_path), locations=True)

        # De-duplicate the same (osm_type, osm_id) potentially seen from
        # more than one way-node during the scan.
        seen: set[tuple[str, int]] = set()
        deduped: list[OsmElement] = []
        for element in handler.elements:
            key = (element.osm_type, element.osm_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(element)

        logger.info(
            "%s: read %d unique tagged element(s) from %s within bbox",
            SOURCE_NAME, len(deduped), self.extract_file_path,
        )
        return deduped

    async def collect(
        self, south: float, west: float, north: float, east: float
    ) -> list[OsmElement]:
        # osmium's file parsing is synchronous, CPU/IO-bound C++ code —
        # run it off the event loop so it doesn't block other async work
        # (e.g. concurrent Wikidata/Wikipedia enrichment calls) while a
        # large extract file is being scanned.
        return await asyncio.to_thread(self._collect_sync, south, west, north, east)
