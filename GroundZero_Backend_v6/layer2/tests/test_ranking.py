from datetime import datetime, timezone

from layer0.domain.entities import BiasSignals, Coordinates, OpeningHours, Place, PriceBand
from layer2.application.ranking import (
    RankingConfig, data_confidence, eligible, order_route, rank_score,
)
from layer2.application.slot_assembly import AssembledSlot
from layer2.domain.entities import ScoredPlace, SlotRole

CFG = RankingConfig()
NOW = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)


def _p(pid, cat="cafe", lat=12.87, lon=74.84, **kw):
    return Place(id=pid, name=pid, category=cat, coordinates=Coordinates(latitude=lat, longitude=lon),
                 opening_hours=OpeningHours(raw="", opens_at="08:00", closes_at="20:00"),
                 price_band=PriceBand.BUDGET, estimated_cost=100.0, bias_signals=BiasSignals(),
                 freshness_score=kw.pop("freshness_score", 0.0), dwell_time_typical_minutes=kw.pop("dwell", 45), **kw)


def _slot(place, role):
    sp = ScoredPlace(place_id=place.id, name=place.name, category=place.category, raw_score=0.5,
                     bias_index=0.2, personal_fit=0.5)
    return AssembledSlot(role=role, scored_place=sp)


def test_confidence_is_bounded_and_rewards_real_data():
    bare = _p("a")
    rich = _p("b", description="d", freshness_score=1.0, tags=["has-wiki-context"])
    assert 0.0 <= data_confidence(bare) < data_confidence(rich) <= 1.0


def test_rank_bonus_breaks_ties_but_cannot_overturn_a_clear_fit_gap():
    rich_near = _p("near", description="d", freshness_score=1.0)
    bare_far = _p("far", lat=12.99, lon=74.95)
    origin = (12.87, 74.84)
    tie_a = rank_score(0.60, rich_near, CFG, origin)
    tie_b = rank_score(0.60, bare_far, CFG, origin)
    assert tie_a > tie_b                                        # tie -> better-evidenced/nearer wins
    assert rank_score(0.75, bare_far, CFG, origin) > rank_score(0.60, rich_near, CFG, origin)  # clear gap stands


def test_eligibility_gate_drops_stays_and_canonicalises_worship_categories():
    pool = [_p(f"h{i}", "lodging") for i in range(3)] + [_p(f"t{i}", "temple") for i in range(9)]
    out = eligible(pool, CFG)
    assert {p.category for p in out} == {"heritage_site"} and len(out) == 9


def test_gate_falls_back_when_it_would_leave_too_few_places():
    pool = [_p("h", "lodging"), _p("c", "cafe")]
    assert len(eligible(pool, CFG)) == 2


def test_route_keeps_arc_shortens_path_and_puts_lunch_near_midday():
    # A zig-zag: alternating far west / far east stops in personal order.
    g = _p("g", "park", 12.870, 74.840)
    s = _p("s", "museum", 12.871, 74.841)
    a = _p("a", "restaurant", 12.900, 74.900)
    ls = _p("ls", "hidden_gem", 12.872, 74.842)
    mids = [_p(f"m{i}", "viewpoint", 12.87 + (0.05 if i % 2 else 0.0), 74.84 + (0.02 * i)) for i in range(6)]
    places = {p.id: p for p in [g, s, a, ls, *mids]}
    slots = [_slot(g, SlotRole.GROUNDING), _slot(s, SlotRole.SIGNATURE), _slot(a, SlotRole.ANCHOR),
             _slot(ls, SlotRole.LOCAL_SECRET)] + [_slot(m, SlotRole.PERSONAL) for m in mids]
    out = order_route(slots, places, NOW, CFG, origin=(12.87, 74.84))
    roles = [s.role for s in out]
    assert roles[0] == SlotRole.GROUNDING and roles[1] == SlotRole.SIGNATURE and roles[-1] == SlotRole.LOCAL_SECRET
    assert sorted(x.scored_place.place_id for x in out) == sorted(x.scored_place.place_id for x in slots)
    # anchor is neither first nor jammed at the start of the day
    assert SlotRole.ANCHOR in roles and 2 < roles.index(SlotRole.ANCHOR) < len(roles) - 1

    def length(seq):
        pts = [(places[x.scored_place.place_id].coordinates.latitude, places[x.scored_place.place_id].coordinates.longitude) for x in seq]
        return sum(((pts[i][0] - pts[i + 1][0]) ** 2 + (pts[i][1] - pts[i + 1][1]) ** 2) ** 0.5 for i in range(len(pts) - 1))
    assert length(out) < length(slots)


def test_route_is_returned_unchanged_when_a_slot_has_no_coordinates():
    a, b, c, d = (_p(x) for x in "abcd")
    slots = [_slot(a, SlotRole.GROUNDING), _slot(b, SlotRole.PERSONAL), _slot(c, SlotRole.PERSONAL), _slot(d, SlotRole.LOCAL_SECRET)]
    assert order_route(slots, {"a": a, "b": b, "c": c}, NOW, CFG) is slots
