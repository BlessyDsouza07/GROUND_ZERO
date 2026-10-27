"""Guards for the rules that keep bad coordinates out of the dataset."""
import pytest

from layer0.application.place_ingest import (
    KnownPlace, OsmFeature, build_locality_index, collides_with_other_place, find_existing,
    fold_name, resolve_from_osm, token_sets_equal,
)
from shared.place_taxonomy import canonical_category, is_itinerary_eligible


def _f(name, lat, lon, **tags):
    return OsmFeature("n", abs(hash((name, lat))) % 10**9, (name,), lat, lon, tags)


CITY = (12.8698, 74.8433)


def test_worship_words_map_to_heritage_site_like_the_osm_path():
    for raw in ("temple", "Mosque", "church", "shrine", "other_religious_site"):
        assert canonical_category(raw) == "heritage_site"
    assert canonical_category("Hotel") == "lodging"
    assert canonical_category("") == "uncategorized"


def test_only_real_attractions_are_itinerary_eligible():
    assert is_itinerary_eligible("temple") and is_itinerary_eligible("beach") and is_itinerary_eligible("cafe")
    for bad in ("hotel", "lodging", "hospital", "ev_charger", "bus_stand", "uncategorized", "locality", "local_shop"):
        assert not is_itinerary_eligible(bad)


def test_exact_named_feature_with_matching_tags_resolves():
    feats = [_f("North Bengre Beach", 12.8629, 74.8200, natural="beach")]
    r = resolve_from_osm("North Bengre Beach", "beach", "Bengre, Mangaluru", feats, {})
    assert r.status == "resolved" and (r.lat, r.lon) == (12.8629, 74.82)


def test_generic_only_name_never_matches():
    feats = [_f("Jama Masjid", 12.87, 74.84, amenity="place_of_worship")]
    assert resolve_from_osm("Jamia Masjid", "mosque", "", feats, {}).status == "unresolved"


def test_type_word_conflict_is_rejected():
    feats = [_f("Central Market", 12.8667, 74.8389, amenity="marketplace", tourism="attraction")]
    assert resolve_from_osm("Central Masjid", "mosque", "", feats, {}).status == "unresolved"


def test_extra_distinctive_word_is_rejected():
    feats = [_f("Hotel International", 12.8705, 74.8417, tourism="hotel")]
    assert resolve_from_osm("Hotel Poonja International", "hotel", "", feats, {}).status == "unresolved"


def test_category_must_be_confirmed_by_osm_tags():
    feats = [_f("Beach Cafe", 12.9, 74.8, amenity="restaurant")]
    assert resolve_from_osm("Beach Cafe", "beach", "", feats, {}).status == "unresolved"


def test_same_name_far_from_the_named_locality_is_rejected():
    loc = {"kankanady": (12.8646, 74.8600)}
    feats = [_f("Sri Mahalingeshwara Temple", 13.0356, 74.7954, amenity="place_of_worship")]
    r = resolve_from_osm("Kankanady Sri Mahalingeshwara Devasthana", "temple", "Kankanady, Mangaluru", feats, loc)
    assert r.status == "unresolved"


def test_two_distant_matches_are_ambiguous_not_guessed():
    feats = [_f("Sri Ganesh Temple", 12.87, 74.84, amenity="place_of_worship"),
             _f("Sri Ganesh Temple", 12.95, 74.90, amenity="place_of_worship")]
    r = resolve_from_osm("Ganesh Temple", "temple", "", feats, {})
    assert r.status == "unresolved" and "ambiguous" in r.reason


def test_place_outside_the_city_with_no_locality_is_rejected():
    feats = [_f("Fish Market", 12.7517, 74.9517, amenity="marketplace")]
    assert resolve_from_osm("Mangalore Fish Market", "market", "Mangaluru, Karnataka", feats, {}).status == "unresolved"


def test_first_letter_typo_guard_keeps_pavoor_and_kavoor_apart():
    assert not token_sets_equal({"pavoor"}, {"kavoor"})
    assert token_sets_equal({"hampankatta"}, {"hampankatte"})


def test_dedup_by_name_and_by_spot():
    known = [KnownPlace("Shri Venkataramana Temple", "heritage_site", 12.8702, 74.8388)]
    assert find_existing("Sri Venkataramana Temple", "temple", None, None, known, set())
    assert find_existing("Venkataramana Temple", "temple", 12.87025, 74.83885, known, set())
    assert not find_existing("Different Cafe", "cafe", 12.95, 74.9, known, set())


def test_a_different_place_on_the_same_pin_is_flagged_as_collision():
    known = [KnownPlace("Itsy Bitsy", "local_shop", 12.8815, 74.8464)]
    assert collides_with_other_place(12.88150, 74.84640, "Kalpana Book Shop", known)
    assert not collides_with_other_place(12.88150, 74.84640, "Itsy Bitsy", known)


def test_locality_index_drops_a_homonymous_far_away_node():
    feats = [_f("Balmatta", 12.9575, 74.9043, place="hamlet")]
    feats += [_f(f"Balmatta Road {i}", 12.8753 + i * 0.0005, 74.8557) for i in range(4)]
    assert "balmatta" not in build_locality_index(feats)


def test_curator_word_is_kept_as_tag_after_etl_canonicalisation():
    import asyncio
    from layer0.application import etl_orchestrator as E
    from layer0.application.bias_signal_estimator import BiasSignalEstimator
    from layer0.application.opening_hours_parser import OpeningHoursParser
    from layer0.application.place_enricher import PlaceEnricher
    from layer0.infrastructure.collectors.local_listings_collector import ListingRecord
    rec = ListingRecord(name="X Masjid", category="mosque", lat=12.87, lon=74.84, address=None, description=None,
                        source_url="", source_name="t")
    p = E._listing_record_to_place(rec, PlaceEnricher(), BiasSignalEstimator(), OpeningHoursParser())
    assert p.category == "heritage_site" and "mosque" in p.tags
