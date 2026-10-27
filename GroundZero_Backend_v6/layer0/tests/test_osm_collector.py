import pytest

from layer0.infrastructure.collectors.osm_collector import (
    OsmCollector,
    OsmElement,
    split_bbox_into_tiles,
)
from layer0.infrastructure.http_client import SourceUnavailable


def test_small_bbox_is_a_single_tile():
    tiles = split_bbox_into_tiles(12.90, 74.80, 12.95, 74.85, max_tile_degrees=0.1)
    assert tiles == [(12.90, 74.80, 12.95, 74.85)]


def test_large_bbox_splits_into_multiple_tiles():
    tiles = split_bbox_into_tiles(12.75, 74.78, 13.05, 75.05, max_tile_degrees=0.1)
    assert len(tiles) > 1


def test_tiles_fully_cover_the_original_bbox():
    south, west, north, east = 12.75, 74.78, 13.05, 75.05
    tiles = split_bbox_into_tiles(south, west, north, east, max_tile_degrees=0.1)

    min_south = min(t[0] for t in tiles)
    min_west = min(t[1] for t in tiles)
    max_north = max(t[2] for t in tiles)
    max_east = max(t[3] for t in tiles)

    assert min_south == pytest.approx(south)
    assert min_west == pytest.approx(west)
    assert max_north == pytest.approx(north)
    assert max_east == pytest.approx(east)


def test_no_tile_exceeds_max_size():
    tiles = split_bbox_into_tiles(12.75, 74.78, 13.05, 75.05, max_tile_degrees=0.1)
    for south, west, north, east in tiles:
        assert (north - south) <= 0.1 + 1e-9
        assert (east - west) <= 0.1 + 1e-9


def test_exact_boundary_bbox_is_single_tile():
    tiles = split_bbox_into_tiles(0.0, 0.0, 0.1, 0.1, max_tile_degrees=0.1)
    assert len(tiles) == 1


class FakeHttpClient:
    """Simulates per-tile Overpass responses, including some tiles failing
    and a duplicate element appearing at a tile boundary. Matches queries
    to configured responses by parsing the bbox out of the query text and
    comparing numerically (with tolerance) rather than via exact string
    matching, since tile boundary coordinates come from float division
    and don't always produce clean decimal strings."""

    def __init__(self, tile_responses: dict, fail_tiles: set | None = None):
        self.tile_responses = {
            tuple(round(float(x), 6) for x in key.split(",")): value
            for key, value in tile_responses.items()
        }
        self.fail_tiles = {tuple(round(float(x), 6) for x in key.split(",")) for key in (fail_tiles or set())}
        self.call_count = 0

    def _extract_bbox(self, query: str) -> tuple[float, ...]:
        import re

        match = re.search(r"\(([\d.]+),([\d.]+),([\d.]+),([\d.]+)\)", query)
        return tuple(round(float(x), 6) for x in match.groups())

    async def request(self, source, method, url, params=None):
        self.call_count += 1
        query = params["data"]
        bbox_key = self._extract_bbox(query)

        if bbox_key in self.fail_tiles:
            raise SourceUnavailable(source, f"simulated failure for {bbox_key}")
        if bbox_key not in self.tile_responses:
            raise AssertionError(f"No fake response configured for bbox: {bbox_key}")

        elements = self.tile_responses[bbox_key]

        class FakeResponse:
            def json(self_inner):
                return {"elements": elements}

        return FakeResponse()


def _element_dict(osm_id, osm_type, lat, lon, name):
    return {"id": osm_id, "type": osm_type, "lat": lat, "lon": lon, "tags": {"name": name}}


@pytest.mark.asyncio
async def test_collect_single_tile_small_bbox():
    client = FakeHttpClient({
        "12.9,74.8,12.95,74.85": [_element_dict(1, "node", 12.91, 74.81, "Place A")],
    })
    collector = OsmCollector(client, "http://fake-overpass", max_tile_degrees=0.1)
    elements = await collector.collect(12.9, 74.8, 12.95, 74.85)
    assert len(elements) == 1
    assert elements[0].tags["name"] == "Place A"


@pytest.mark.asyncio
async def test_collect_deduplicates_across_tile_boundaries():
    """The same OSM element (by osm_id + osm_type) appearing in two
    different tiles' results must only appear once in the final output."""
    shared_element = _element_dict(42, "node", 12.9, 74.8, "Boundary Place")
    client = FakeHttpClient({
        "12.75,74.78,12.9,74.915": [shared_element, _element_dict(1, "node", 12.8, 74.8, "Tile1 Place")],
        "12.75,74.915,12.9,75.05": [shared_element, _element_dict(2, "node", 12.8, 75.0, "Tile2 Place")],
        "12.9,74.78,13.05,74.915": [_element_dict(3, "node", 13.0, 74.8, "Tile3 Place")],
        "12.9,74.915,13.05,75.05": [_element_dict(4, "node", 13.0, 75.0, "Tile4 Place")],
    })
    collector = OsmCollector(client, "http://fake-overpass", max_tile_degrees=0.2, tile_concurrency=4)
    elements = await collector.collect(12.75, 74.78, 13.05, 75.05)

    ids = [e.osm_id for e in elements]
    assert ids.count(42) == 1
    assert len(elements) == 5


@pytest.mark.asyncio
async def test_collect_continues_when_some_tiles_fail():
    client = FakeHttpClient(
        {
            "12.75,74.78,12.9,74.915": [_element_dict(1, "node", 12.8, 74.8, "Good Tile Place")],
            "12.75,74.915,12.9,75.05": [_element_dict(2, "node", 12.8, 75.0, "Also Good")],
            "12.9,74.78,13.05,74.915": [],
            "12.9,74.915,13.05,75.05": [],
        },
        fail_tiles={"12.9,74.78,13.05,74.915"},
    )
    collector = OsmCollector(client, "http://fake-overpass", max_tile_degrees=0.2, tile_concurrency=4)
    elements = await collector.collect(12.75, 74.78, 13.05, 75.05)
    names = {e.tags["name"] for e in elements}
    assert "Good Tile Place" in names
    assert "Also Good" in names


@pytest.mark.asyncio
async def test_collect_raises_when_every_tile_fails():
    class AlwaysFailClient:
        async def request(self, *args, **kwargs):
            raise SourceUnavailable("openstreetmap", "simulated total outage")

    collector = OsmCollector(AlwaysFailClient(), "http://fake-overpass", max_tile_degrees=0.2, tile_concurrency=4)
    with pytest.raises(SourceUnavailable):
        await collector.collect(12.75, 74.78, 13.05, 75.05)


@pytest.mark.asyncio
async def test_elements_without_coordinates_are_filtered_at_collector_level():
    client = FakeHttpClient({
        "12.9,74.8,12.95,74.85": [
            {"id": 1, "type": "node", "lat": 12.91, "lon": 74.81, "tags": {"name": "Has Coords"}},
            {"id": 2, "type": "node", "tags": {"name": "No Coords"}},  # missing lat/lon entirely
        ],
    })
    collector = OsmCollector(client, "http://fake-overpass", max_tile_degrees=0.1)
    elements = await collector.collect(12.9, 74.8, 12.95, 74.85)
    assert len(elements) == 1
    assert elements[0].tags["name"] == "Has Coords"
