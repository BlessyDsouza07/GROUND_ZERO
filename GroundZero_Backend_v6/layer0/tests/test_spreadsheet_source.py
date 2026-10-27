"""Tests for SpreadsheetListingSource — the free/no-rate-limit CSV
ingestion path (see docs/GROWING_THE_DATABASE.md)."""
from __future__ import annotations

import pytest

from layer0.infrastructure.collectors.spreadsheet_source import SpreadsheetListingSource


@pytest.mark.asyncio
async def test_missing_file_returns_empty_list_not_an_error(tmp_path):
    source = SpreadsheetListingSource(tmp_path / "does_not_exist.csv")
    records = await source.fetch()
    assert records == []


@pytest.mark.asyncio
async def test_parses_a_full_row_with_every_optional_field(tmp_path):
    csv_path = tmp_path / "places.csv"
    csv_path.write_text(
        "name,category,lat,lon,address,description,curator,source_url,opening_hours,"
        "tags,price_band,estimated_cost,energy_requirement,crowd_level,"
        "dwell_time_typical_minutes,tide_dependency,season_suitability,"
        "accessibility_tags,etiquette_tag,best_time,parking,washrooms,food_available,"
        "family_friendly,kid_friendly,photography_allowed,contact_phone,"
        "local_percentage_hint,media_mentions_hint\n"
        "Mrs Lobo's Home Kitchen,local_kitchen,12.87,74.84,Near Kadri,"
        "A tiny home kitchen with two tables,carol,https://example.com,"
        "12:00-15:00,local-food;hidden-gem,budget,150,low,low,40,false,all,,"
        "remove footwear,afternoon,false,false,true,true,true,false,,90,1\n",
        encoding="utf-8",
    )

    source = SpreadsheetListingSource(csv_path)
    records = await source.fetch()

    assert len(records) == 1
    record = records[0]
    assert record.name == "Mrs Lobo's Home Kitchen"
    assert record.lat == 12.87
    assert record.lon == 74.84
    assert record.tags == ("local-food", "hidden-gem")
    assert record.price_band == "budget"
    assert record.estimated_cost == 150.0
    assert record.dwell_time_typical_minutes == 40
    assert record.tide_dependency is False
    assert record.etiquette_tag == "remove footwear"
    assert record.local_percentage_hint == 0.9  # 90 -> fraction
    assert record.media_mentions_hint == 1


@pytest.mark.asyncio
async def test_row_missing_required_fields_is_skipped_not_crashed(tmp_path):
    csv_path = tmp_path / "places.csv"
    csv_path.write_text(
        "name,category,lat,lon\n"
        "Good Place,park,12.9,74.8\n"
        ",park,12.9,74.8\n"  # missing name
        "No Coords Place,park,,74.8\n"  # missing lat
        "Not A Number,park,notanumber,74.8\n",  # bad lat
        encoding="utf-8",
    )

    source = SpreadsheetListingSource(csv_path)
    records = await source.fetch()

    assert len(records) == 1
    assert records[0].name == "Good Place"


@pytest.mark.asyncio
async def test_missing_required_column_skips_whole_file(tmp_path):
    csv_path = tmp_path / "places.csv"
    csv_path.write_text("name,category\nSomewhere,beach\n", encoding="utf-8")  # no lat/lon columns

    source = SpreadsheetListingSource(csv_path)
    records = await source.fetch()

    assert records == []


@pytest.mark.asyncio
async def test_the_shipped_starter_seed_csv_parses_cleanly():
    """data/community_places.csv ships with this repo as a starter batch —
    prove it actually parses into valid records with no silent drops."""
    from pathlib import Path

    seed_path = Path(__file__).resolve().parents[2] / "data" / "community_places.csv"
    source = SpreadsheetListingSource(seed_path)
    records = await source.fetch()

    assert len(records) >= 15
    assert all(r.name and r.lat is not None and r.lon is not None for r in records)
