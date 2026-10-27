from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from auth import routes as auth_routes
from auth.models import User
from hive2 import geofence, learning, models as m, routes as hroutes
from hive2.dataset import load_places
from hive2.experience import classify
from hive2.intent import parse_intent
from hive2.ranker import Context, Profile, rank
from explore.hours import open_info
from layer0.application.opening_hours_parser import OpeningHoursParser
from layer2.api.dependencies import get_place_repository
import privacy.routes as proutes

IST = ZoneInfo("Asia/Kolkata")
PLACES = load_places()
PAR = OpeningHoursParser()
CENTRE = (12.8698, 74.8420)


def of(p, now):
    i = open_info(p, PAR, now)
    return i.state, i.source, i.label


def run(text, profile=None, hour=11, **kw):
    now = datetime(2026, 10, 13, hour, 0, tzinfo=IST)
    it = parse_intent(text)
    ctx = Context(CENTRE[0], CENTRE[1], now, minutes=kw.get("minutes", it.minutes), intent=it, rain=kw.get("rain"), mode=kw.get("mode"))
    return rank(PLACES, ctx, profile or Profile(), of), now


# ---------- intent ----------
def test_intent_parsing():
    i = parse_intent("2 hours, with my kids, vegetarian, under 300, quiet please")
    assert i.minutes == 120 and i.with_kids and "veg" in i.diet and i.budget_per_place == 300 and i.avoid_crowds
    assert parse_intent("surprise me").mode == "surprise"
    assert parse_intent("nothing special").minutes is None
    assert parse_intent("non-veg please").diet == []


# ---------- knowledge: unknown != False ----------
def test_unknown_stays_none():
    p = next(p for p in PLACES if p.category == "heritage_site")
    ev = classify(p).evidence
    assert ev.wheelchair is None and ev.kid_friendly is None
    assert ev.crowd is None                       # master-data default "moderate" is treated as unknown
    assert ev.authenticity_basis in ("heuristic", "none", "local_listing", "community")
    assert 0 <= ev.verification <= 0.95


# ---------- hard constraints ----------
def test_closed_never_returned_and_hours_labelled():
    res, now = run("something to see")
    assert res.items
    for s in res.items:
        assert s.open_state != "closed"
        if s.open_source != "listed":
            assert any("not confirmed" in c for c in s.caveats)


def test_budget_is_never_violated():
    res, _ = run("under 100", minutes=240)
    for s in res.items:
        c = s.k.evidence.estimated_cost
        assert c is None or c <= 100


def test_visited_and_dismissed_excluded():
    base, _ = run("food", minutes=240)
    ids = {s.k.place_id for s in base.items}
    prof = Profile(visited={next(iter(ids))}, dismissed={sorted(ids)[-1]})
    res, _ = run("food", profile=prof, minutes=240)
    got = {s.k.place_id for s in res.items}
    assert not (got & prof.visited) and not (got & prof.dismissed)


def test_vegetarian_food_never_non_veg():
    res, _ = run("lunch, vegetarian", minutes=180)
    for s in res.items:
        if s.k.role == "food":
            blob = s.k.name.lower() + s.k.category
            assert not any(w in blob for w in ("seafood", "chicken", "mutton", "biryani"))


def test_wheelchair_not_false_when_required():
    prof = Profile(constraints={"accessibility": ["wheelchair"], "accessibility_strict": True})
    res, _ = run("easy sightseeing", profile=prof, minutes=240)
    for s in res.items:
        assert s.k.evidence.wheelchair is True


def test_nothing_fits_returns_message_not_relaxation():
    prof = Profile(constraints={"excluded_categories": sorted({p.category for p in PLACES})})
    res, _ = run("easy", profile=prof, minutes=240)
    assert res.items == [] and "haven't loosened" in res.message and res.relaxed == []


def test_late_night_unknown_hours_dropped():
    res, _ = run("anything", hour=23, minutes=120)
    for s in res.items:
        assert s.open_state != "unknown" or s.k.category == "lodging"


def test_time_budget_respected():
    res, _ = run("a quick break", minutes=30)
    for s in res.items:
        assert s.travel_min * 2 + min(s.k.evidence.dwell_minutes, 40) <= 30 + 15


# ---------- scoring/diversity/modes ----------
def test_personal_fit_changes_ranking():
    like = Profile(affinities={"exp:food": {"weight": 0.9, "confidence": 0.8, "source": "stated"}})
    a, _ = run("", profile=like, minutes=180)
    b, _ = run("", minutes=180)
    assert [s.k.place_id for s in a.items] != [s.k.place_id for s in b.items]
    foods = sum(1 for s in a.items if s.k.role == "food")
    assert foods >= sum(1 for s in b.items if s.k.role == "food")


def test_diversity_not_all_same_category():
    res, _ = run("", minutes=240)
    assert len({s.k.category for s in res.items}) >= 3


def test_slow_mode_fewer_stops():
    res, _ = run("", mode="slow", minutes=240)
    assert len(res.items) <= 3


def test_less_touristy_never_claims_without_evidence():
    res, _ = run("hidden local spots", minutes=240)
    for s in res.items:
        if s.hidden_gem:
            assert s.k.evidence.authenticity_basis in ("community", "local_listing")
        assert (s.k.evidence.commercialisation or 0) <= 0.35 or s.less_touristy_evidence


def test_explanations_grounded():
    res, _ = run("quiet green walk", minutes=180)
    for s in res.items:
        assert s.reasons
        if s.k.evidence.crowd is None:
            assert "Crowd level unknown" in s.caveats
        assert not any("hidden gem" in r.lower() for r in s.reasons) or s.hidden_gem


def test_monsoon_beach_caveat():
    now = datetime(2026, 7, 10, 10, 0, tzinfo=IST)
    it = parse_intent("beach")
    res = rank(PLACES, Context(*CENTRE, now, minutes=300, intent=it), Profile(), of)
    beaches = [s for s in res.items if s.k.category == "beach"]
    for s in beaches:
        assert any("Monsoon sea is dangerous" in c for c in s.caveats)


# ---------- learning ----------
def test_skip_without_dislike_does_not_penalise():
    p = next(p for p in PLACES if p.category == "restaurant")
    aff = learning.apply_event({}, p, "dismissed", reason="closed")
    assert aff == {}
    aff = learning.apply_event({}, p, "dismissed", reason="not_interested")
    assert aff["cat:restaurant"]["weight"] < 0


def test_impression_not_a_like():
    p = PLACES[0]
    assert learning.apply_event({}, p, "shown") == {}


def test_stated_preference_not_decayed_behaviour_is():
    old = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    aff = {"exp:food": {"weight": 0.8, "confidence": 0.9, "source": "stated", "updated": old},
           "exp:coastal": {"weight": 0.8, "confidence": 0.5, "source": "behaviour", "updated": old}}
    d = learning.decayed(aff)
    assert d["exp:food"]["weight"] == 0.8 and d["exp:coastal"]["weight"] < 0.3


# ---------- geofence ----------
def test_geofence_rules():
    t0 = datetime(2026, 10, 13, 11, 0, tzinfo=IST)
    cand = [("p1", "Place", 12.8700, 74.8420, "open", False)]
    st = {}
    assert geofence.evaluate(cand, 12.8700, 74.8420, 500, st, t0)["reason"] == "location_accuracy_too_low"
    assert geofence.evaluate(cand, 12.8700, 74.8420, 20, st, t0)["notify"] is None       # just entered: dwell
    r = geofence.evaluate(cand, 12.8700, 74.8420, 20, st, t0 + timedelta(seconds=45))
    assert r["notify"]["place_id"] == "p1"
    again = geofence.evaluate(cand, 12.8700, 74.8420, 20, st, t0 + timedelta(minutes=10))
    assert again["notify"] is None                                                         # cooldown
    assert geofence.evaluate(cand, 12.8700, 74.8420, 20, {}, t0, quiet=True)["notify"] is None


def test_geofence_hysteresis_and_closed():
    t0 = datetime(2026, 10, 13, 11, 0, tzinfo=IST)
    cand = [("p1", "Place", 12.8700, 74.8420, "open", False)]
    st = {}
    geofence.evaluate(cand, 12.8700, 74.8420, 20, st, t0)
    geofence.evaluate(cand, 12.87045, 74.8420, 20, st, t0 + timedelta(seconds=5))        # ~50 m: still inside
    assert st["p1"].inside
    geofence.evaluate(cand, 12.8720, 74.8420, 20, st, t0 + timedelta(seconds=10))         # ~220 m: left
    assert not st["p1"].inside
    closed = [("p2", "Shut", 12.87, 74.842, "closed", False)]
    s2 = {}
    geofence.evaluate(closed, 12.87, 74.842, 20, s2, t0)
    assert geofence.evaluate(closed, 12.87, 74.842, 20, s2, t0 + timedelta(seconds=60))["notify"] is None


# ---------- API with real SQLite DB ----------
class FakeRepo:
    async def list_all(self, category=None):
        return PLACES

    async def get_by_id(self, pid):
        return next((p for p in PLACES if str(p.id) == pid), None)


@pytest.fixture
async def api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.create_all, tables=[User.__table__, m.TravellerProfile.__table__, m.TravellerEvent.__table__,
                                                              m.GeofenceState.__table__, m.ConsentRecord.__table__, m.ContentReport.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _db():
        async with factory() as s:
            yield s

    app = FastAPI()
    for r in (auth_routes.router, hroutes.router, proutes.router):
        app.include_router(r)
    app.dependency_overrides[auth_routes.get_db] = _db
    app.dependency_overrides[get_place_repository] = lambda: FakeRepo()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def signup(c, email="a@x.com"):
    r = await c.post("/auth/register", json={"email": email, "password": "password1", "accepted_terms": True, "adult_confirmed": True})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.mark.asyncio
async def test_signup_requires_terms_and_adult(api):
    r = await api.post("/auth/register", json={"email": "b@x.com", "password": "password1"})
    assert r.status_code == 422
    r = await api.post("/auth/register", json={"email": "b@x.com", "password": "password1", "accepted_terms": True})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_plan_without_consent_stores_nothing(api):
    h = await signup(api)
    r = await api.post("/hive/plan", json={"text": "2 hours food", "lat": 12.87, "lng": 74.84}, headers=h)
    assert r.status_code == 200 and r.json()["cards"] and r.json()["personalised"] is False
    fb = await api.post("/hive/feedback", json={"place_id": r.json()["cards"][0]["place_id"], "kind": "saved"}, headers=h)
    assert fb.json()["stored"] is False
    assert (await api.get("/hive/profile", headers=h)).json()["affinities"] == {}
    assert (await api.post("/hive/location", json={"lat": 12.87, "lng": 74.84, "accuracy_m": 10}, headers=h)).status_code == 409


@pytest.mark.asyncio
async def test_consent_learning_edit_delete_flow(api):
    h = await signup(api)
    c = (await api.put("/privacy/consents", json={"kind": "personalization", "granted": True}, headers=h)).json()["consents"]
    assert c["personalization"]["granted"] and c["terms"]["granted"] and c["adult"]["granted"]
    cards = (await api.post("/hive/plan", json={"text": "food", "minutes": 240, "lat": 12.87, "lng": 74.84}, headers=h)).json()["cards"]
    pid = cards[0]["place_id"]
    assert (await api.post("/hive/feedback", json={"place_id": pid, "kind": "saved"}, headers=h)).json()["stored"]
    prof = (await api.get("/hive/profile", headers=h)).json()
    assert prof["affinities"] and all(a["source"] == "behaviour" for a in prof["affinities"].values())
    assert (await api.post("/hive/feedback", json={"place_id": pid, "kind": "dismissed", "reason": "not_interested"}, headers=h)).status_code == 200
    again = (await api.post("/hive/plan", json={"text": "food", "minutes": 240, "lat": 12.87, "lng": 74.84}, headers=h)).json()["cards"]
    assert pid not in {x["place_id"] for x in again}
    up = await api.put("/hive/profile", json={"constraints": {"dietary": ["veg"], "bogus": 1}, "stated": {"exp:heritage": 0.8}}, headers=h)
    assert up.json()["constraints"] == {"dietary": ["veg"]} and up.json()["affinities"]["exp:heritage"]["source"] == "stated"
    exp = (await api.get("/privacy/export", headers=h)).json()
    assert exp["account"]["email"] == "a@x.com" and exp["feedback_events"]
    assert (await api.delete("/hive/profile", headers=h)).json()["deleted"]
    assert (await api.get("/hive/profile", headers=h)).json()["affinities"] == {}


@pytest.mark.asyncio
async def test_withdraw_personalisation_deletes_memory_and_location_flow(api):
    h = await signup(api)
    await api.put("/privacy/consents", json={"kind": "personalization", "granted": True}, headers=h)
    cards = (await api.post("/hive/plan", json={"text": "", "minutes": 240}, headers=h)).json()["cards"]
    await api.post("/hive/feedback", json={"place_id": cards[0]["place_id"], "kind": "visited"}, headers=h)
    await api.put("/privacy/consents", json={"kind": "personalization", "granted": False}, headers=h)
    p = (await api.get("/hive/profile", headers=h)).json()
    assert p["affinities"] == {} and p["visited_count"] == 0
    await api.put("/privacy/consents", json={"kind": "location", "granted": True}, headers=h)
    r = await api.post("/hive/location", json={"lat": 12.87, "lng": 74.84, "accuracy_m": 10}, headers=h)
    assert r.status_code == 200 and "notify" in r.json()


@pytest.mark.asyncio
async def test_report_legal_and_safety(api):
    h = await signup(api)
    r = await api.post("/privacy/report", json={"target_kind": "photo", "target_ref": "x.jpg", "reason": "privacy"}, headers=h)
    assert r.status_code == 201
    assert (await api.get("/legal/privacy")).json()["draft"] is True
    assert (await api.get("/legal/nope")).status_code == 404
    nums = {e["number"] for e in (await api.get("/safety")).json()["emergency"]}
    assert {"112", "108", "100", "1363"} <= nums
    assert (await api.get("/hive/profile")).status_code == 401
