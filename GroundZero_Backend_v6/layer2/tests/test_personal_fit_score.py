"""
Table 10 (blueprint) gives raw_score and bias_index as already-computed
inputs and shows the resulting personal_fit — it does NOT show which
sub-component scores (companion/energy/curiosity/crowd/time) produced
those specific raw_score values. So we verify the formula itself
(raw_score × (1 − bias_index)) exactly against all three worked examples,
and verify the sub-component scoring behavior separately via property
tests against realistic Place/TouristProfile combinations.
"""
from datetime import datetime, timezone

from layer0.domain.entities import (
    BiasSignals,
    Coordinates,
    CrowdLevel,
    EnergyRequirement,
    OpeningHours,
    Place,
    PriceBand,
)
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.domain.entities import (
    CrowdTolerance,
    EnergyBand,
    Purpose,
    StartTimePreference,
    TouristProfile,
    TripDuration,
)
from layer2.application.personal_fit_score import PersonalFitScoreService


def _place(category="heritage_site", bias_index=0.25, energy=EnergyRequirement.LOW, crowd=CrowdLevel.LOW, best_time=None) -> Place:
    return Place(
        id="p1", name="Test Place", category=category,
        coordinates=Coordinates(latitude=12.9, longitude=74.85),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.FREE, estimated_cost=0.0,
        bias_signals=BiasSignals(), bias_index=bias_index,
        energy_requirement=energy, crowd_level=crowd, best_time=best_time,
    )


def _profile(purpose=Purpose.CULTURAL, energy=EnergyBand.LOW, crowd_tolerance=CrowdTolerance.PREFER_QUIET) -> TouristProfile:
    return TouristProfile(
        id="prof1", purpose=purpose, energy_band=energy, crowd_tolerance=crowd_tolerance,
        budget=2000.0, trip_duration_hours=TripDuration.FULL_DAY,
        start_time_preference=StartTimePreference.MORNING,
    )


def test_formula_matches_table_10_milagres_church():
    raw_score, bias_index = 0.84, 0.25
    expected_personal_fit = round(raw_score * (1 - bias_index), 2)
    assert expected_personal_fit == 0.63


def test_formula_matches_table_10_summer_sands_resort():
    raw_score, bias_index = 0.47, 0.85
    expected_personal_fit = round(raw_score * (1 - bias_index), 2)
    assert expected_personal_fit == 0.07


def test_formula_matches_table_10_mrs_lobos_home_kitchen():
    raw_score, bias_index = 0.88, 0.05
    expected_personal_fit = round(raw_score * (1 - bias_index), 2)
    assert expected_personal_fit == 0.84


def test_service_applies_exact_same_formula():
    """Confirms PersonalFitScoreService.score() computes personal_fit as
    raw_score * (1 - bias_index) with no deviation, using its own
    internally-derived raw_score (not the Table 10 example numbers)."""
    service = PersonalFitScoreService(CuriosityExtractor())
    place = _place(bias_index=0.25)
    profile = _profile()
    breakdown = service.score(place, profile, scheduled_hour=9)
    assert abs(breakdown.personal_fit - round(breakdown.raw_score * (1 - breakdown.bias_index), 4)) < 1e-9


def test_high_bias_index_crushes_personal_fit_even_with_good_raw_score():
    service = PersonalFitScoreService(CuriosityExtractor())
    good_authentic = _place(category="heritage_site", bias_index=0.05)
    good_hyped = _place(category="heritage_site", bias_index=0.90)
    profile = _profile()

    authentic_fit = service.score(good_authentic, profile, scheduled_hour=9)
    hyped_fit = service.score(good_hyped, profile, scheduled_hour=9)

    # Same raw_score inputs (same category/energy/crowd/etc), but bias
    # index should be the dominant differentiator per the blueprint's
    # design intent ("no blacklist, the math does the curation").
    assert authentic_fit.raw_score == hyped_fit.raw_score
    assert authentic_fit.personal_fit > hyped_fit.personal_fit


def test_purpose_matching_category_scores_higher_companion():
    service = PersonalFitScoreService(CuriosityExtractor())
    matching_place = _place(category="heritage_site")
    non_matching_place = _place(category="shopping_mall")
    profile = _profile(purpose=Purpose.CULTURAL)

    matching = service.score(matching_place, profile, scheduled_hour=9)
    non_matching = service.score(non_matching_place, profile, scheduled_hour=9)
    assert matching.companion_score > non_matching.companion_score


def test_energy_mismatch_reduces_energy_score():
    service = PersonalFitScoreService(CuriosityExtractor())
    profile = _profile(energy=EnergyBand.LOW)
    low_energy_place = _place(energy=EnergyRequirement.LOW)
    high_energy_place = _place(energy=EnergyRequirement.HIGH)

    matched = service.score(low_energy_place, profile, scheduled_hour=9)
    mismatched = service.score(high_energy_place, profile, scheduled_hour=9)
    assert matched.energy_score > mismatched.energy_score


def test_avoid_crowds_tourist_zero_score_for_high_crowd_place():
    service = PersonalFitScoreService(CuriosityExtractor())
    profile = _profile(crowd_tolerance=CrowdTolerance.AVOID_ENTIRELY)
    crowded_place = _place(crowd=CrowdLevel.HIGH)

    breakdown = service.score(crowded_place, profile, scheduled_hour=9)
    assert breakdown.crowd_score == 0.0
