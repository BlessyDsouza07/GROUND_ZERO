"""Tests for BulkOsmExtractCollector — the fully offline OSM path with
zero network calls and zero rate limit (see
docs/GROWING_THE_DATABASE.md)."""
from __future__ import annotations

import pytest

from layer0.infrastructure.collectors.bulk_osm_extract_collector import BulkOsmExtractCollector

_SAMPLE_OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
  <node id="1" lat="12.8752" lon="74.8482">
    <tag k="amenity" v="place_of_worship"/>
    <tag k="name" v="Test Temple"/>
  </node>
  <node id="2" lat="12.8698" lon="74.8420">
    <tag k="tourism" v="museum"/>
    <tag k="name" v="Test Museum"/>
  </node>
  <node id="3" lat="40.0" lon="-70.0">
    <tag k="amenity" v="restaurant"/>
    <tag k="name" v="Out Of BBox Restaurant"/>
  </node>
  <node id="4" lat="12.87" lon="74.84">
    <tag k="amenity" v="restaurant"/>
  </node>
  <node id="5" lat="12.88" lon="74.85">
    <tag k="shop" v="hairdresser"/>
    <tag k="name" v="Not A Wanted Category"/>
  </node>
  <node id="10" lat="12.86" lon="74.83"/>
  <node id="11" lat="12.861" lon="74.831"/>
  <way id="100">
    <nd ref="10"/>
    <nd ref="11"/>
    <tag k="leisure" v="park"/>
    <tag k="name" v="Test Way Park"/>
  </way>
</osm>
"""


@pytest.fixture
def sample_osm_file(tmp_path):
    path = tmp_path / "sample.osm"
    path.write_text(_SAMPLE_OSM_XML, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_missing_file_raises_clear_error(tmp_path):
    collector = BulkOsmExtractCollector(tmp_path / "does_not_exist.osm")
    with pytest.raises(FileNotFoundError):
        await collector.collect(12.75, 74.78, 13.05, 75.05)


@pytest.mark.asyncio
async def test_reads_named_tagged_nodes_within_bbox(sample_osm_file):
    collector = BulkOsmExtractCollector(sample_osm_file)
    elements = await collector.collect(12.75, 74.78, 13.05, 75.05)

    names = {el.tags.get("name") for el in elements}
    assert "Test Temple" in names
    assert "Test Museum" in names
    # unnamed node dropped
    assert None not in names or all(el.tags.get("name") for el in elements)
    # out-of-bbox node dropped
    assert "Out Of BBox Restaurant" not in names
    # unwanted category (shop=hairdresser isn't in our tag vocabulary) dropped
    assert "Not A Wanted Category" not in names


@pytest.mark.asyncio
async def test_resolves_way_centroid_from_node_locations(sample_osm_file):
    collector = BulkOsmExtractCollector(sample_osm_file)
    elements = await collector.collect(12.75, 74.78, 13.05, 75.05)

    ways = [el for el in elements if el.osm_type == "way"]
    assert len(ways) == 1
    assert ways[0].tags.get("name") == "Test Way Park"
    assert 12.75 <= ways[0].lat <= 13.05
    assert 74.78 <= ways[0].lon <= 75.05


@pytest.mark.asyncio
async def test_bbox_actually_narrows_results(sample_osm_file):
    collector = BulkOsmExtractCollector(sample_osm_file)
    # A bbox that excludes everything
    elements = await collector.collect(0.0, 0.0, 0.1, 0.1)
    assert elements == []
