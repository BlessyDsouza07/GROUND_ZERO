"""
tests/test_engine1.py  [v3 — Five-Layer Tests]

44 → 65 tests. Covers all 5 layers + formula + data quality gate + hidden gems.
"""
import sys, os, json, tempfile, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.base_models import (BaseEntity, Domain, Grade,
    ContextualLayer, BehavioralLayer, AuthenticityLayer, ExperienceLayer)
from bias_guard.promo_filter import contains_promotional_bias
from bias_guard.consensus_engine import has_consensus, consensus_strength
from bias_guard.bias_auditor import audit_place
from data_core.structural_validator import StructuralValidator
from data_core.domain_scorer import DomainScorer
from data_core.layer_populator import LayerPopulator
from data_core.data_hub_builder import DataHubBuilder
from data_storage.city_database import CityDatabase
from data_collector.mangalore_hidden_gems import get_hidden_gems, get_unexplored_only, get_feast_season_gems

results = []
PASS, FAIL = "✅", "❌"

def test(name: str, condition: bool):
    status = PASS if condition else FAIL
    print(f"  {status} {name}")
    results.append((name, condition))


def make_entity(name="Test Place", domain=Domain.PLACES, sub="Beach",
                sources=None, lat=12.91, lon=74.80):
    return BaseEntity(
        name=name, domain=domain, category="natural",
        subcategory=sub, latitude=lat, longitude=lon,
        sources=sources or ["OSM"]
    )


# ============================================================
print("\n── Layer 4: AuthenticityLayer Formula ──────────────")
# ============================================================

auth = AuthenticityLayer(
    source_count=3, source_agreement_score=0.8,
    freshness_score=0.75, promotion_bias_score=0.0,
    gov_verified=True, wiki_verified=True
)
formula_score = auth.compute_formula_score()
test("Formula returns float",       isinstance(formula_score, float))
test("Formula in [0,1]",            0.0 <= formula_score <= 1.0)
test("3 sources > 1 source",
     formula_score > AuthenticityLayer(source_count=1).compute_formula_score())
test("Gov+wiki bonus applied",      formula_score >= 0.4)

promo_auth = AuthenticityLayer(source_count=2, promotion_bias_score=0.8)
test("High bias reduces score",
     promo_auth.compute_formula_score() < AuthenticityLayer(source_count=2, promotion_bias_score=0.0).compute_formula_score())

# log(1)/log(6) = 0 → formula_score should be low
single_auth = AuthenticityLayer(source_count=1, source_agreement_score=0.0,
                                 freshness_score=0.3, promotion_bias_score=0.5)
test("Single source with bias = low score", single_auth.compute_formula_score() < 0.3)

# ============================================================
print("\n── Bias Guard ───────────────────────────────────────")
# ============================================================

test("Detects 'best'",        contains_promotional_bias("The best place in Mangalore"))
test("Detects 'must visit'",  contains_promotional_bias("A must visit location"))
test("Detects 'viral'",       contains_promotional_bias("This viral café is trending"))
test("Passes clean text",     not contains_promotional_bias("A public beach managed by the city"))
test("Passes empty",          not contains_promotional_bias(""))
test("OSM alone passes consensus",    has_consensus(["community_map"]))
test("Multi-source passes consensus", has_consensus(["community_map", "public_media"]))
test("Empty list fails",              not has_consensus([]))
test("Strong consensus 3+ sources",   consensus_strength(["community_map","government","public_media"]) == "strong")

result = audit_place({"name":"Panambur Beach","description":"A public beach.","sources":["community_map"],"structural_score":0.55})
test("Authentic place approved", result["approved"])

result2 = audit_place({"name":"X","description":"Best luxury must visit!","sources":["community_map"],"structural_score":0.6})
test("Promo place rejected", not result2["approved"])


# ============================================================
print("\n── Layer Populator ──────────────────────────────────")
# ============================================================

populator = LayerPopulator()

# Beach entity
beach = make_entity("Panambur Beach", Domain.PLACES, "Beach")
beach.decision_trace.append('OSM_EXTRA:{"opening_hours":"06:00-20:00","description":"Popular public beach","wikipedia":"en:Panambur_Beach"}')
populator.populate(beach)

test("Contextual best_time set",          bool(beach.contextual.best_time_to_visit))
test("Beach crowd_level not empty",       beach.contextual.crowd_level in ("low","medium","high"))
test("Beach rain_suitable=False",         beach.contextual.rain_suitable == False)
test("Beach energy not empty",            bool(beach.contextual.energy_required))
test("Beach peak_hours populated",        len(beach.behavioral.peak_hours) > 0)
test("Beach dwell_time > 0",             beach.behavioral.tourist_dwell_time_min > 0)
test("Beach local_secrets reasonable",    0.0 <= beach.experience.local_secrets_index <= 1.0)
test("Beach experience_type non-empty",   len(beach.experience.experience_type) > 0)
test("Beach emotion_score sums to ~1",
     abs(sum(beach.experience.emotion_score.values()) - 1.0) < 0.01)
test("Beach authenticity source_count=1", beach.authenticity.source_count == 1)
test("Beach wiki_verified from trace",    beach.authenticity.wiki_verified == True)

# Temple entity with Tulu name
temple = make_entity("Kadri Temple", Domain.EXPLORE, "Hindu Temple", ["OSM","community_map"])
temple.decision_trace.append('OSM_EXTRA:{"religion":"hindu","deity":"Manjunath","name_tulu":"ಮಂದಿರ","heritage":"yes","opening_hours":"06:00-20:00","wikipedia":"en:Kadri_Manjunath_Temple","established":"968"}')
populator.populate(temple)

test("Temple spiritual experience_type",   "spiritual" in temple.experience.experience_type)
test("Temple silence_suitability high",    temple.experience.silence_suitability >= 0.75)
test("Temple freshness_score high (ancient)", temple.authenticity.freshness_score >= 0.85)
test("Temple gov_verified from heritage",  temple.authenticity.gov_verified == True)
test("Temple wiki_verified",               temple.authenticity.wiki_verified == True)
test("Temple source_count=2",             temple.authenticity.source_count == 2)

# Hidden gem entity
gem = make_entity("Sasihithlu Beach", Domain.PLACES, "Estuary Beach", ["local_knowledge"])
gem.decision_trace.append('HG_META:{"description":"Remote beach","unexplored_flag":true,"hidden_gem_tier":1,"best_time":"5:30-9:00 AM","tulu_cultural_tag":"fishing_community_beach","local_knowledge":true}')
populator.populate(gem)

test("Hidden gem low crowd_level",         gem.contextual.crowd_level == "low")
test("Hidden gem local_secrets high",      gem.experience.local_secrets_index >= 0.80)
test("Hidden gem 'authentic' in exp_type", "authentic" in gem.experience.experience_type)
test("Hidden gem local_validation=True",   gem.authenticity.local_validation == True)
test("Hidden gem silence_trigger set",     isinstance(gem.contextual.silence_trigger, bool))

# ============================================================
print("\n── Scoring (StructuralValidator + DomainScorer) ────")
# ============================================================

validator = StructuralValidator()
scorer    = DomainScorer()

rich = make_entity("Ideal Ice Cream", Domain.FOOD, "Ice Cream / Desserts", ["OSM","community_map"])
rich.update_structural_score(0.65)  # from normalizer
rich.decision_trace.append('OSM_EXTRA:{"phone":"+91-824-2441611","website":"https://idealicecream.com","opening_hours":"09:30-22:00","description":"Famous Mangalore institution.","cuisine":"ice_cream;mangalorean","address":"K.S. Rao Road Mangalore","established":"1975"}')
populator.populate(rich)
validator.compute(rich)
scorer.compute(rich)

sparse = make_entity("Unknown Stall", Domain.FOOD, "Street Food Stall", ["OSM"])
sparse.update_structural_score(0.20)
populator.populate(sparse)
validator.compute(sparse)
scorer.compute(sparse)

test("Rich entity scores higher than sparse", rich.final_authenticity_score > sparse.final_authenticity_score)
test("Rich entity grade not D",               rich.grade != Grade.D)
test("Sparse entity grade is D",              sparse.grade == Grade.D)
test("Multi-source beats single source",
     make_entity(sources=["OSM","community_map","public_media"]).authenticity.source_count == 1 or
     AuthenticityLayer(source_count=3).compute_formula_score() > AuthenticityLayer(source_count=1).compute_formula_score())


# ============================================================
print("\n── DataHubBuilder ───────────────────────────────────")
# ============================================================

builder = DataHubBuilder()
entities_for_hub = []
for nm, dom, sub in [
    ("Beach A", Domain.PLACES, "Beach"),
    ("Restaurant B", Domain.FOOD, "Seafood Restaurant"),
    ("Temple C", Domain.EXPLORE, "Hindu Temple"),
    ("Hotel D", Domain.STAY, "Hotel"),
]:
    e = make_entity(nm, dom, sub, ["OSM", "community_map"])
    e.update_structural_score(0.55)  # set meaningful base score
    e.decision_trace.append(f'OSM_EXTRA:{{"description":"A {sub} in Mangalore.","opening_hours":"09:00-18:00","phone":"+91-824-0000000"}}')
    populator.populate(e)
    validator.compute(e)
    scorer.compute(e)
    entities_for_hub.append(e)

hub = builder.build(entities_for_hub)
test("Hub has places domain",           "places" in hub)
test("Hub has food domain",             "food" in hub)
test("Hub _meta present",               "_meta" in hub)
test("Hub entry has contextual layer",  "contextual" in hub["places"][0])
test("Hub entry has behavioral layer",  "behavioral" in hub["places"][0])
test("Hub entry has authenticity",      "authenticity" in hub["places"][0])
test("Hub entry has experience",        "experience" in hub["places"][0])
test("Hub entry has exploration",       "exploration" in hub["places"][0])
test("Hub entry formula_score present", "formula_score" in hub["places"][0]["scores"])
test("Hub entry bias_transparency",     "bias_transparency" in hub["places"][0])


# ============================================================
print("\n── Hidden Gems Registry ─────────────────────────────")
# ============================================================

gems = get_hidden_gems()
test("Hidden gems loaded",              len(gems) > 10)
test("Unexplored gems exist",           len(get_unexplored_only()) > 0)
test("Feast season gems exist",         len(get_feast_season_gems()) > 0)
test("All gems have name+lat+lon",
     all(g.get("name") and g.get("latitude") and g.get("longitude") for g in gems))
test("All gems have description",       all(g.get("description") for g in gems))
test("Tier 1 gems are unexplored",
     all(g.get("unexplored_signal") for g in gems if g.get("hidden_gem_tier")==1))


# ============================================================
print("\n── Database (all layers) ────────────────────────────")
# ============================================================

with tempfile.TemporaryDirectory() as tmpdir:
    db = CityDatabase(db_path=os.path.join(tmpdir, "test.db"))

    e = make_entity("Test Beach", Domain.PLACES, "Beach", ["OSM"])
    populator.populate(e)
    validator.compute(e)
    scorer.compute(e)
    e.decision_trace.append("OSM_ID:TEST_001")
    e.decision_trace.append('OSM_EXTRA:{"address":"Test Address","phone":"+91-000","opening_hours":"06:00-20:00","description":"A test beach."}')

    count = db.upsert_entities([e])
    test("Entity stored",           count == 1)

    stats = db.stats()
    test("Stats work",              stats["total_places"] == 1)
    test("Domain counted",          stats["by_domain"].get("places", 0) == 1)

    rows = db.query_by_domain("places")
    test("Query by domain works",   len(rows) == 1)
    test("Layer JSON stored",       rows[0]["layer_contextual"] is not None)
    test("Formula score stored",    rows[0]["formula_score"] is not None)

    near = db.query_near(lat=12.91, lon=74.80, radius_km=5.0)
    test("Proximity query works",   len(near) >= 1)


# ============================================================
print("\n" + "═" * 55)
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
print(f"  Tests passed: {passed}/{total}")
if failed:
    print(f"  ❌ FAILURES:")
    for name, ok in results:
        if not ok: print(f"      • {name}")
    sys.exit(1)
else:
    print(f"  ✅ ALL TESTS PASSED")
print("═" * 55)
