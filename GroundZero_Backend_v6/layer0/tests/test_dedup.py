from layer0.application.dedup import DedupService, haversine_meters, name_similarity, normalize_name
from layer0.domain.entities import BiasSignals, Coordinates, DataSource, OpeningHours, Place, PriceBand


def _place(name: str, lat: float, lon: float, category: str = "cafe") -> Place:
    return Place(
        id="existing-id" if name == "existing" else None,
        name=name,
        category=category,
        coordinates=Coordinates(latitude=lat, longitude=lon),
        opening_hours=OpeningHours(raw=""),
        price_band=PriceBand.BUDGET,
        estimated_cost=100.0,
        bias_signals=BiasSignals(),
        source=[DataSource.OSM],
    )


def test_haversine_zero_distance_same_point():
    assert haversine_meters(12.9, 74.85, 12.9, 74.85) == 0.0


def test_haversine_known_distance_approx():
    # Roughly 1 degree of latitude ~= 111km
    d = haversine_meters(12.0, 75.0, 13.0, 75.0)
    assert 110_000 < d < 112_000


def test_normalize_name_strips_articles_and_punctuation():
    assert normalize_name("The Milagres Church!") == "milagres church"


def test_name_similarity_high_for_minor_spelling_variation():
    assert name_similarity("Milagres Church", "Milagres Chruch") > 0.85


def test_name_similarity_low_for_unrelated_names():
    assert name_similarity("Milagres Church", "Summer Sands Resort") < 0.4


def test_finds_match_within_threshold():
    service = DedupService(distance_threshold_meters=75.0, name_similarity_threshold=0.8)
    existing = _place("Mrs Lobo's Home Kitchen", 12.9141, 74.8560)
    candidate = _place("Mrs. Lobos Home Kitchen", 12.91415, 74.85605)  # ~7m away, near-identical name

    match = service.find_best_match(candidate, [existing])
    assert match is not None
    assert match.existing.name == "Mrs Lobo's Home Kitchen"


def test_no_match_when_too_far_even_if_name_matches():
    service = DedupService(distance_threshold_meters=75.0, name_similarity_threshold=0.8)
    existing = _place("City Centre Mall", 12.9141, 74.8560)
    candidate = _place("City Centre Mall", 13.0141, 74.9560)  # ~15km away

    match = service.find_best_match(candidate, [existing])
    assert match is None


def test_no_match_when_close_but_name_differs():
    service = DedupService(distance_threshold_meters=75.0, name_similarity_threshold=0.8)
    existing = _place("Milagres Church", 12.9141, 74.8560)
    candidate = _place("Summer Sands Resort", 12.91411, 74.85601)

    match = service.find_best_match(candidate, [existing])
    assert match is None


def test_merge_unions_tags_and_sources():
    service = DedupService()
    existing = _place("Milagres Church", 12.9141, 74.8560)
    existing.tags = ["heritage_site"]
    incoming = _place("Milagres Church", 12.9141, 74.8560)
    incoming.tags = ["heritage_site", "has-wiki-context"]
    incoming.source = [DataSource.WIKIDATA]
    incoming.description = "A colonial-era church."

    merged = service.merge(existing, incoming)
    assert set(merged.tags) == {"heritage_site", "has-wiki-context"}
    assert set(merged.source) == {DataSource.OSM, DataSource.WIKIDATA}
    assert merged.description == "A colonial-era church."
