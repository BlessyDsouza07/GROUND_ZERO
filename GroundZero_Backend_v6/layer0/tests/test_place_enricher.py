from layer0.application.place_enricher import PlaceEnricher
from layer0.domain.entities import CrowdLevel, EnergyRequirement, PriceBand


def test_food_category_gets_food_available_true_definitionally():
    result = PlaceEnricher().enrich("restaurant", {})
    assert result.food_available is True


def test_non_food_category_without_tag_is_unknown_not_guessed():
    result = PlaceEnricher().enrich("heritage_site", {})
    assert result.food_available is None


def test_religious_site_gets_etiquette_only_from_real_osm_tag():
    with_religion = PlaceEnricher().enrich("heritage_site", {"religion": "christian"})
    without_religion = PlaceEnricher().enrich("heritage_site", {})
    assert with_religion.etiquette_tag is not None
    assert without_religion.etiquette_tag is None


def test_fee_no_tag_overrides_category_cost_prior():
    result = PlaceEnricher().enrich("cafe", {"fee": "no"})
    assert result.estimated_cost == 0.0
    assert result.price_band == PriceBand.FREE


def test_category_without_fee_tag_uses_prior():
    result = PlaceEnricher().enrich("cafe", {})
    assert result.estimated_cost == 200.0


def test_park_is_free_and_zero_energy_moderate():
    result = PlaceEnricher().enrich("park", {})
    assert result.estimated_cost == 0.0
    assert result.price_band == PriceBand.FREE


def test_beach_is_tide_dependent():
    result = PlaceEnricher().enrich("beach", {})
    assert result.tide_dependency is True


def test_museum_is_not_tide_dependent():
    result = PlaceEnricher().enrich("museum", {})
    assert result.tide_dependency is False


def test_waterfall_is_monsoon_only_season():
    result = PlaceEnricher().enrich("waterfall", {})
    assert result.season_suitability == ["monsoon"]


def test_beach_excludes_monsoon_season():
    result = PlaceEnricher().enrich("beach", {})
    assert "monsoon" not in result.season_suitability
    assert "winter" in result.season_suitability


def test_indoor_category_has_no_seasonal_restriction():
    result = PlaceEnricher().enrich("museum", {})
    assert set(result.season_suitability) == {"winter", "summer", "monsoon"}


def test_high_energy_categories():
    for cat in ["nature_spot", "trail", "waterfall", "adventure"]:
        result = PlaceEnricher().enrich(cat, {})
        assert result.energy_requirement == EnergyRequirement.HIGH, cat


def test_low_energy_categories():
    for cat in ["cafe", "restaurant", "museum", "library"]:
        result = PlaceEnricher().enrich(cat, {})
        assert result.energy_requirement == EnergyRequirement.LOW, cat


def test_unmapped_category_falls_back_to_moderate_defaults():
    result = PlaceEnricher().enrich("some_unknown_category", {})
    assert result.energy_requirement == EnergyRequirement.MODERATE
    assert result.crowd_level == CrowdLevel.MODERATE
    assert result.dwell_time_typical_minutes == 45


def test_dwell_time_reflects_category_nature():
    quick = PlaceEnricher().enrich("street_food", {})
    long_visit = PlaceEnricher().enrich("theatre", {})
    assert quick.dwell_time_typical_minutes < long_visit.dwell_time_typical_minutes


def test_best_time_only_set_for_categories_with_known_association():
    viewpoint = PlaceEnricher().enrich("viewpoint", {})
    generic = PlaceEnricher().enrich("craft_centre", {})
    assert viewpoint.best_time == "sunset"
    assert generic.best_time is None


def test_toilets_tag_directly_sets_washrooms():
    yes = PlaceEnricher().enrich("park", {"toilets": "yes"})
    no = PlaceEnricher().enrich("park", {"toilets": "no"})
    unknown = PlaceEnricher().enrich("park", {})
    assert yes.washrooms is True
    assert no.washrooms is False
    assert unknown.washrooms is None


def test_pet_friendly_only_set_for_conventional_outdoor_public_categories():
    park = PlaceEnricher().enrich("park", {})
    restaurant = PlaceEnricher().enrich("restaurant", {})
    assert park.pet_friendly is True
    assert restaurant.pet_friendly is None  # genuinely unknown, not guessed


def test_family_and_kid_friendly_consistent():
    result = PlaceEnricher().enrich("museum", {})
    assert result.family_friendly is True
    assert result.kid_friendly == result.family_friendly


def test_photography_allowed_only_for_conventional_categories():
    viewpoint = PlaceEnricher().enrich("viewpoint", {})
    restaurant = PlaceEnricher().enrich("restaurant", {})
    assert viewpoint.photography_allowed is True
    assert restaurant.photography_allowed is None
