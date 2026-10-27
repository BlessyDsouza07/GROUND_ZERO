"""
Legacy vs Ranking-v2 on the real Master Data Core, offline (no DB, no network).

    python scripts/benchmark_recommendations.py

Runs 24 traveller profiles (6 purposes x 2 energy bands x 2 trip lengths)
from a fixed start point through both engines and reports numbers that map
to real complaints, not vibes:

  non_attraction_stops   share of stops that are hotels / hospitals / shops /
                         uncategorized rows — should be 0
  route_km               total straight-line distance walking the stops in
                         the order they are scheduled — lower is better
  lunch_gap_h            |hour the meal Anchor is scheduled - 13:15| — lower
                         is better
  distinct_categories    variety per day — higher is better
  purpose_match          share of stops whose category matches the stated
                         purpose (SPIRITUAL -> heritage_site, FOODIE ->
                         food categories, ...) — higher is better
"""
from __future__ import annotations

import asyncio
import json
import statistics
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import import_master_data as im  # noqa: E402
from layer0.application.accessibility import AccessibilityDetector  # noqa: E402
from layer0.application.dedup import haversine_meters  # noqa: E402
from layer0.application.freshness import FreshnessService  # noqa: E402
from layer0.domain.repositories import PlaceRepository  # noqa: E402
from layer0.infrastructure.http_client import SourceUnavailable  # noqa: E402
from layer1.application.curiosity_extractor import CuriosityExtractor  # noqa: E402
from layer1.domain.entities import CrowdTolerance, EnergyBand, Purpose, TouristProfile, TripDuration  # noqa: E402
from layer2.application.hard_filters import HardFilterService  # noqa: E402
from layer2.application.hive_engine import HiveEngine  # noqa: E402
from layer2.application.personal_fit_score import PersonalFitScoreService  # noqa: E402
from layer2.application.ranking import RankingConfig  # noqa: E402
from layer2.application.slot_assembly import SlotAssemblyService  # noqa: E402
from layer2.application.transport_tagger import TransportTagger  # noqa: E402
from layer2.application.weather_scheduler import WeatherScheduler  # noqa: E402
from shared.place_taxonomy import canonical_category, is_itinerary_eligible  # noqa: E402

START = (12.8670, 74.8412)  # Hampankatta
NOW = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
PURPOSE_CATS = {
    Purpose.SPIRITUAL: {"heritage_site"},
    Purpose.FOODIE: {"restaurant", "cafe", "street_food", "local_kitchen", "food_court", "bakery", "dessert_shop", "market"},
    Purpose.ADVENTURE: {"beach", "viewpoint", "park", "nature_spot", "trail", "waterfall", "boat_ride", "adventure"},
    Purpose.CULTURAL: {"heritage_site", "museum", "art_gallery", "library", "theatre"},
    Purpose.LEISURE: {"beach", "park", "garden", "cafe", "viewpoint", "lake"},
    Purpose.UNDECIDED: set(),
}


class Repo(PlaceRepository):
    def __init__(self, places): self._p = places
    async def get_by_id(self, i): return next((p for p in self._p if p.id == i), None)
    async def find_duplicates(self, p, radius_meters=75.0): return []
    async def upsert(self, p): return p
    async def bulk_upsert(self, ps): return ps
    async def list_all(self, category=None): return [p for p in self._p if category is None or p.category == category]
    async def list_stale(self, d): return []
    async def delete(self, i): pass
    async def record_visit(self, i): pass


class NoWeather:
    async def hourly_forecast(self, lat, lon, hours=12):
        raise SourceUnavailable("weather_api", "offline benchmark")


def engine(places, ranking):
    return HiveEngine(
        place_repository=Repo(places),
        hard_filters=HardFilterService(AccessibilityDetector(), FreshnessService(3650), freshness_min_score=0.0),
        fit_score=PersonalFitScoreService(CuriosityExtractor()),
        slot_assembly=SlotAssemblyService(random_seed=7),
        weather_scheduler=WeatherScheduler(),
        transport_tagger=TransportTagger(),
        weather_collector=NoWeather(),
        ranking=ranking,
    )


async def run(places, ranking):
    eng = engine(places, ranking)
    by_id = {p.id: p for p in places}
    rows = []
    for purpose, energy, dur in product(
        [Purpose.SPIRITUAL, Purpose.FOODIE, Purpose.ADVENTURE, Purpose.CULTURAL, Purpose.LEISURE, Purpose.UNDECIDED],
        [EnergyBand.LOW, EnergyBand.HIGH], [TripDuration.HALF_DAY, TripDuration.FULL_DAY],
    ):
        prof = TouristProfile(id=None, purpose=purpose, energy_band=energy, crowd_tolerance=CrowdTolerance.FINE,
                              budget=3000, trip_duration_hours=dur)
        q = await eng.build_recommendation_queue(prof, NOW, start_latitude=START[0], start_longitude=START[1])
        stops = [by_id[i.place_id] for i in q.items if i.place_id in by_id]
        if not stops:
            continue
        cats = [canonical_category(p.category) for p in stops]
        km = sum(haversine_meters(a.coordinates.latitude, a.coordinates.longitude,
                                  b.coordinates.latitude, b.coordinates.longitude) for a, b in zip(stops, stops[1:])) / 1000
        meal = [i for i in q.items if getattr(i.role, "value", i.role) == "anchor"]
        lunch_gap = (abs((meal[0].scheduled_time.hour + meal[0].scheduled_time.minute / 60) - 13.25)
                     if meal and getattr(meal[0], "scheduled_time", None) else None)
        want = PURPOSE_CATS[purpose]
        rows.append(dict(
            non_attraction=sum(not is_itinerary_eligible(c) for c in cats) / len(cats),
            route_km=km, lunch_gap=lunch_gap, distinct=len(set(cats)),
            purpose=(sum(c in want for c in cats) / len(cats)) if want else None,
        ))
    return rows


def agg(rows, key):
    v = [r[key] for r in rows if r[key] is not None]
    return statistics.mean(v) if v else float("nan")


async def main():
    places = [im._dict_to_place(d) for d in json.loads((ROOT / "data" / "master_data_core.json").read_text(encoding="utf-8"))]
    for p in places:
        p.freshness_score = max(p.freshness_score or 0.0, 0.9)  # snapshot is fresh by construction
    legacy = await run(places, None)
    v2 = await run(places, RankingConfig())
    print(f"{'metric':<24}{'legacy':>10}{'ranking v2':>12}")
    for label, key, fmt in [("non_attraction_stops", "non_attraction", "{:.1%}"), ("route_km", "route_km", "{:.1f}"),
                            ("lunch_gap_h", "lunch_gap", "{:.2f}"), ("distinct_categories", "distinct", "{:.1f}"),
                            ("purpose_match", "purpose", "{:.1%}")]:
        print(f"{label:<24}{fmt.format(agg(legacy, key)):>10}{fmt.format(agg(v2, key)):>12}")
    print(f"profiles scored: legacy={len(legacy)} v2={len(v2)}")


if __name__ == "__main__":
    asyncio.run(main())
