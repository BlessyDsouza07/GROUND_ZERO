from layer0.domain.entities import BiasSignals, Coordinates, OpeningHours, Place, PriceBand
from layer1.domain.entities import TripDuration
from layer2.application.slot_assembly import LOCAL_SECRET_MIN_LOCAL_PERCENTAGE, SlotAssemblyService
from layer2.domain.entities import ScoredPlace, SlotRole


def _place(place_id: str, category: str) -> Place:
    return Place(
        id=place_id, name=place_id, category=category,
        coordinates=Coordinates(latitude=12.9, longitude=74.85),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.BUDGET, estimated_cost=100.0,
        bias_signals=BiasSignals(),
    )


def _scored(place_id: str, personal_fit: float, curiosity_score: float = 0.7, local_secret=False) -> ScoredPlace:
    return ScoredPlace(
        place_id=place_id, name=place_id, category="cafe", raw_score=personal_fit, bias_index=0.1,
        personal_fit=personal_fit, breakdown={"curiosity_score": curiosity_score},
        is_local_secret_eligible=local_secret,
    )


def _build_pool():
    """A rich enough candidate pool to fill every role for a full day."""
    places = {}
    scored = []

    # Grounding candidates (cafe/market/local_kitchen/bakery/park)
    for i, cat in enumerate(["cafe", "market", "local_kitchen"]):
        pid = f"grounding-{i}"
        places[pid] = _place(pid, cat)
        scored.append(_scored(pid, personal_fit=0.7 - i * 0.05))

    # Signature candidates (heritage_site/museum/tourist_attraction/beach/viewpoint)
    for i, cat in enumerate(["heritage_site", "museum", "beach"]):
        pid = f"signature-{i}"
        places[pid] = _place(pid, cat)
        scored.append(_scored(pid, personal_fit=0.9 - i * 0.05))

    # Anchor candidates (restaurant/food_court/cafe/local_kitchen)
    for i, cat in enumerate(["restaurant", "food_court"]):
        pid = f"anchor-{i}"
        places[pid] = _place(pid, cat)
        scored.append(_scored(pid, personal_fit=0.8 - i * 0.05))

    # Local secret candidates
    for i in range(2):
        pid = f"secret-{i}"
        places[pid] = _place(pid, "hidden_gem")
        scored.append(_scored(pid, personal_fit=0.75, local_secret=True))

    # Personal pool (plenty of generic high-curiosity places + some low-curiosity wildcards)
    for i in range(10):
        pid = f"personal-{i}"
        places[pid] = _place(pid, "viewpoint")
        scored.append(_scored(pid, personal_fit=0.6 - i * 0.01, curiosity_score=0.8))

    for i in range(3):
        pid = f"wildcard-{i}"
        places[pid] = _place(pid, "art_gallery")
        scored.append(_scored(pid, personal_fit=0.5, curiosity_score=0.1))  # low curiosity -> wildcard eligible

    return scored, places


def test_full_day_slot_counts_match_table_5():
    service = SlotAssemblyService(random_seed=42)
    scored, places = _build_pool()
    assembled = service.assemble(scored, places, TripDuration.FULL_DAY)

    role_counts = {}
    for slot in assembled:
        role_counts[slot.role] = role_counts.get(slot.role, 0) + 1

    assert role_counts.get(SlotRole.GROUNDING, 0) == 1
    assert role_counts.get(SlotRole.SIGNATURE, 0) == 1
    assert role_counts.get(SlotRole.ANCHOR, 0) == 1
    assert role_counts.get(SlotRole.LOCAL_SECRET, 0) == 1
    assert role_counts.get(SlotRole.PERSONAL, 0) == 9  # includes the 1 wildcard, per Table 5
    assert len(assembled) == 13


def test_half_day_slot_counts_match_table_5():
    service = SlotAssemblyService(random_seed=42)
    scored, places = _build_pool()
    assembled = service.assemble(scored, places, TripDuration.HALF_DAY)

    role_counts = {}
    for slot in assembled:
        role_counts[slot.role] = role_counts.get(slot.role, 0) + 1

    assert role_counts.get(SlotRole.GROUNDING, 0) == 1
    assert role_counts.get(SlotRole.SIGNATURE, 0) == 1
    assert role_counts.get(SlotRole.ANCHOR, 0) == 1
    assert role_counts.get(SlotRole.LOCAL_SECRET, 0) == 1
    assert role_counts.get(SlotRole.PERSONAL, 0) == 4
    assert len(assembled) == 8  # per Table 5; blueprint's own Table 11 says 7 (documented inconsistency)


def test_no_place_used_twice():
    service = SlotAssemblyService(random_seed=1)
    scored, places = _build_pool()
    assembled = service.assemble(scored, places, TripDuration.FULL_DAY)
    place_ids = [s.scored_place.place_id for s in assembled]
    assert len(place_ids) == len(set(place_ids))


def test_full_day_has_exactly_one_wildcard():
    service = SlotAssemblyService(random_seed=1)
    scored, places = _build_pool()
    assembled = service.assemble(scored, places, TripDuration.FULL_DAY)
    wildcards = [s for s in assembled if s.is_wildcard]
    assert len(wildcards) == 1


def test_half_day_has_zero_wildcards():
    service = SlotAssemblyService(random_seed=1)
    scored, places = _build_pool()
    assembled = service.assemble(scored, places, TripDuration.HALF_DAY)
    wildcards = [s for s in assembled if s.is_wildcard]
    assert len(wildcards) == 0


def test_signature_picks_highest_fit_among_eligible_categories():
    service = SlotAssemblyService(random_seed=1)
    scored, places = _build_pool()
    assembled = service.assemble(scored, places, TripDuration.FULL_DAY)
    signature_slot = next(s for s in assembled if s.role == SlotRole.SIGNATURE)
    assert signature_slot.scored_place.place_id == "signature-0"  # highest personal_fit=0.9 among signature candidates


def test_insufficient_candidates_returns_partial_assembly_without_crashing():
    service = SlotAssemblyService(random_seed=1)
    scored = [_scored("only-one", personal_fit=0.5)]
    places = {"only-one": _place("only-one", "cafe")}
    assembled = service.assemble(scored, places, TripDuration.FULL_DAY)
    # cafe matches Grounding category, so it should be placed there, and
    # nothing else should be fabricated to fill the remaining 12 slots.
    assert len(assembled) == 1
    assert assembled[0].role == SlotRole.GROUNDING


def test_community_submission_bias_default_clears_local_secret_threshold():
    """Cross-module consistency guard. An architectural audit found that
    the community-submission default local_percentage (previously 0.85,
    layer0/api/routes.py) sat BELOW LOCAL_SECRET_MIN_LOCAL_PERCENTAGE
    (0.9), meaning genuine community hidden-gem submissions — the exact
    pathway the Local Secret slot exists to feed — could never actually
    qualify for it. Imports both real constants directly so a future
    change to either one that reintroduces the mismatch fails loudly
    here, not silently in production."""
    from layer0.api.routes import COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE

    assert COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE >= LOCAL_SECRET_MIN_LOCAL_PERCENTAGE, (
        f"Community submission default local_percentage "
        f"({COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE}) is below "
        f"LOCAL_SECRET_MIN_LOCAL_PERCENTAGE ({LOCAL_SECRET_MIN_LOCAL_PERCENTAGE}) — "
        "genuine hidden-gem submissions could never qualify for the Local Secret slot."
    )
