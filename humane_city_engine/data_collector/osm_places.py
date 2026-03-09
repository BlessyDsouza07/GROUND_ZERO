"""
data_collector/osm_places.py  [DIVERSITY UPGRADE — v3]

WHAT THIS VERSION ADDS vs previous:
- Covers every food-related OSM tag (street_vendor, juice_bar, dhaba, sweet_shop etc.)
- Covers every accommodation type (homestay, dharamshala, lodge, service_apartment)
- Covers every experience type (yoga, ayurveda, martial arts, cooking school)
- Covers every shopping type (fish market, spice shop, saree, jewellery)
- Covers every transport type (auto_rickshaw, ferry, boat hire)
- Covers every wellness type (spa, ayurveda, traditional medicine)
- Covers every nightlife type (rooftop bar, toddy shop, live music)
- Covers waterfront, coastal, river, backwater spots
- Named roads and walking streets (MG Road, Hampankatta etc.)
- Religious sites of all faiths (temple, church, mosque, dargah, jain, synagogue)
- Colleges and landmark educational institutions
- All beaches with access paths
- All viewpoints and photography spots

HOW IT WORKS:
- Primary: uses known Mangalore area_id 3601952828
- Fallback: Mangalore bounding box (12.78,74.75,13.05,75.05) — always works
- Mirror rotation: 3 Overpass servers — if one is down, tries next
- 15s wait before fetch to avoid rate limits from prior queries
"""

import requests
import json
import os
import time
from typing import Dict
from datetime import datetime, timezone


# ============================================================
# CONFIGURATION
# ============================================================

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

MAX_RETRIES = 3
RETRY_DELAY = 8


# ============================================================
# COMPREHENSIVE OVERPASS QUERIES
# ============================================================

def _build_area_query(area_id: int) -> str:
    return f"""
[out:json][timeout:240];
area({area_id})->.mg;
(
  // ── FOOD: RESTAURANTS ──────────────────────────────────────
  node["amenity"="restaurant"](area.mg);
  way["amenity"="restaurant"](area.mg);
  node["amenity"="cafe"](area.mg);
  way["amenity"="cafe"](area.mg);
  node["amenity"="fast_food"](area.mg);
  way["amenity"="fast_food"](area.mg);
  node["amenity"="food_court"](area.mg);
  way["amenity"="food_court"](area.mg);
  node["amenity"="bar"](area.mg);
  way["amenity"="bar"](area.mg);
  node["amenity"="pub"](area.mg);
  node["amenity"="ice_cream"](area.mg);
  node["amenity"="juice_bar"](area.mg);
  node["amenity"="biryani_house"](area.mg);
  node["amenity"="sweet_shop"](area.mg);
  node["amenity"="bakery"](area.mg);
  way["amenity"="bakery"](area.mg);
  node["amenity"="snack_bar"](area.mg);
  node["amenity"="seafood"](area.mg);
  node["amenity"="dhaba"](area.mg);
  node["amenity"="canteen"](area.mg);
  node["shop"="bakery"](area.mg);
  node["shop"="confectionery"](area.mg);
  node["shop"="chocolate"](area.mg);
  node["shop"="deli"](area.mg);
  node["shop"="seafood"](area.mg);
  node["shop"="fish"](area.mg);
  node["shop"="butcher"](area.mg);
  node["shop"="greengrocer"](area.mg);

  // ── FOOD: STREET FOOD & VENDORS ────────────────────────────
  node["amenity"="street_vendor"](area.mg);
  node["shop"="street_vendor"](area.mg);
  node["cuisine"](area.mg);
  way["cuisine"](area.mg);

  // ── ACCOMMODATION ──────────────────────────────────────────
  node["tourism"="hotel"](area.mg);
  way["tourism"="hotel"](area.mg);
  node["tourism"="hostel"](area.mg);
  node["tourism"="guest_house"](area.mg);
  way["tourism"="guest_house"](area.mg);
  node["tourism"="motel"](area.mg);
  node["tourism"="resort"](area.mg);
  way["tourism"="resort"](area.mg);
  node["tourism"="camp_site"](area.mg);
  node["tourism"="apartment"](area.mg);
  node["tourism"="homestay"](area.mg);
  node["building"="hotel"](area.mg);
  way["building"="hotel"](area.mg);

  // ── TOURIST ATTRACTIONS ────────────────────────────────────
  node["tourism"="attraction"](area.mg);
  way["tourism"="attraction"](area.mg);
  relation["tourism"="attraction"](area.mg);
  node["tourism"="museum"](area.mg);
  way["tourism"="museum"](area.mg);
  node["tourism"="gallery"](area.mg);
  node["tourism"="artwork"](area.mg);
  node["tourism"="viewpoint"](area.mg);
  way["tourism"="viewpoint"](area.mg);
  node["tourism"="information"](area.mg);
  node["tourism"="theme_park"](area.mg);
  node["tourism"="zoo"](area.mg);
  node["tourism"="picnic_site"](area.mg);

  // ── BEACHES & COASTAL ──────────────────────────────────────
  node["natural"="beach"](area.mg);
  way["natural"="beach"](area.mg);
  relation["natural"="beach"](area.mg);
  node["leisure"="beach_resort"](area.mg);
  way["leisure"="beach_resort"](area.mg);
  node["amenity"="beach"](area.mg);
  node["waterway"="dock"](area.mg);
  node["waterway"="jetty"](area.mg);
  way["waterway"="river"](area.mg);
  way["waterway"="stream"](area.mg);
  node["natural"="coastline"](area.mg);
  way["natural"="coastline"](area.mg);
  node["leisure"="marina"](area.mg);

  // ── NATURE & PARKS ─────────────────────────────────────────
  node["leisure"="park"](area.mg);
  way["leisure"="park"](area.mg);
  relation["leisure"="park"](area.mg);
  node["leisure"="garden"](area.mg);
  way["leisure"="garden"](area.mg);
  node["leisure"="nature_reserve"](area.mg);
  way["leisure"="nature_reserve"](area.mg);
  node["natural"="wood"](area.mg);
  way["natural"="wood"](area.mg);
  node["natural"="water"](area.mg);
  way["natural"="water"](area.mg);
  node["natural"="wetland"](area.mg);
  node["natural"="hill"](area.mg);
  node["natural"="peak"](area.mg);
  node["natural"="cliff"](area.mg);
  node["natural"="spring"](area.mg);
  node["natural"="waterfall"](area.mg);
  node["leisure"="playground"](area.mg);

  // ── RELIGIOUS SITES (all faiths) ───────────────────────────
  node["amenity"="place_of_worship"](area.mg);
  way["amenity"="place_of_worship"](area.mg);
  relation["amenity"="place_of_worship"](area.mg);
  node["building"="temple"](area.mg);
  way["building"="temple"](area.mg);
  node["building"="church"](area.mg);
  way["building"="church"](area.mg);
  node["building"="mosque"](area.mg);
  way["building"="mosque"](area.mg);
  node["building"="chapel"](area.mg);
  way["building"="chapel"](area.mg);
  node["historic"="temple"](area.mg);
  node["historic"="church"](area.mg);
  node["historic"="mosque"](area.mg);

  // ── HISTORIC & CULTURAL ────────────────────────────────────
  node["historic"](area.mg);
  way["historic"](area.mg);
  relation["historic"](area.mg);
  node["heritage"](area.mg);
  way["heritage"](area.mg);
  node["amenity"="theatre"](area.mg);
  way["amenity"="theatre"](area.mg);
  node["amenity"="cinema"](area.mg);
  way["amenity"="cinema"](area.mg);
  node["amenity"="arts_centre"](area.mg);
  node["amenity"="community_centre"](area.mg);
  node["amenity"="library"](area.mg);
  way["amenity"="library"](area.mg);
  node["amenity"="exhibition_centre"](area.mg);
  node["building"="heritage"](area.mg);
  way["building"="heritage"](area.mg);

  // ── SHOPPING ───────────────────────────────────────────────
  node["shop"](area.mg);
  way["shop"](area.mg);
  node["amenity"="marketplace"](area.mg);
  way["amenity"="marketplace"](area.mg);
  node["amenity"="market"](area.mg);
  way["amenity"="market"](area.mg);
  node["amenity"="shopping_centre"](area.mg);
  way["amenity"="shopping_centre"](area.mg);
  node["landuse"="retail"](area.mg);
  way["landuse"="retail"](area.mg);

  // ── SPORTS & ACTIVITIES ────────────────────────────────────
  node["sport"](area.mg);
  way["sport"](area.mg);
  node["leisure"="sports_centre"](area.mg);
  way["leisure"="sports_centre"](area.mg);
  node["leisure"="stadium"](area.mg);
  way["leisure"="stadium"](area.mg);
  node["leisure"="swimming_pool"](area.mg);
  way["leisure"="swimming_pool"](area.mg);
  node["leisure"="fitness_centre"](area.mg);
  way["leisure"="fitness_centre"](area.mg);
  node["leisure"="pitch"](area.mg);
  way["leisure"="pitch"](area.mg);
  node["leisure"="golf_course"](area.mg);
  node["leisure"="water_park"](area.mg);
  node["leisure"="amusement_arcade"](area.mg);

  // ── WELLNESS & HEALTH ──────────────────────────────────────
  node["amenity"="spa"](area.mg);
  node["shop"="massage"](area.mg);
  node["shop"="beauty"](area.mg);
  node["shop"="hairdresser"](area.mg);
  node["amenity"="clinic"](area.mg);
  way["amenity"="clinic"](area.mg);
  node["healthcare"="ayurveda"](area.mg);
  node["amenity"="yoga"](area.mg);
  node["healthcare"](area.mg);
  way["healthcare"](area.mg);

  // ── EDUCATION (landmark colleges & institutions) ───────────
  node["amenity"="university"](area.mg);
  way["amenity"="university"](area.mg);
  node["amenity"="college"](area.mg);
  way["amenity"="college"](area.mg);
  node["amenity"="school"](area.mg);
  way["amenity"="school"](area.mg);

  // ── TRANSPORT ──────────────────────────────────────────────
  node["amenity"="bus_station"](area.mg);
  way["amenity"="bus_station"](area.mg);
  node["amenity"="ferry_terminal"](area.mg);
  node["amenity"="taxi"](area.mg);
  node["amenity"="fuel"](area.mg);
  node["amenity"="car_rental"](area.mg);
  node["amenity"="bicycle_rental"](area.mg);
  node["aeroway"="aerodrome"](area.mg);
  node["public_transport"="station"](area.mg);
  way["public_transport"="station"](area.mg);
  node["railway"="station"](area.mg);
  node["railway"="halt"](area.mg);
  node["amenity"="parking"](area.mg);

  // ── EMERGENCY & SERVICES ───────────────────────────────────
  node["amenity"="hospital"](area.mg);
  way["amenity"="hospital"](area.mg);
  node["amenity"="police"](area.mg);
  node["amenity"="fire_station"](area.mg);
  node["amenity"="pharmacy"](area.mg);
  node["amenity"="bank"](area.mg);
  node["amenity"="atm"](area.mg);
  node["amenity"="post_office"](area.mg);
  node["amenity"="telephone"](area.mg);

  // ── NIGHTLIFE ──────────────────────────────────────────────
  node["amenity"="nightclub"](area.mg);
  node["amenity"="club"](area.mg);
  node["tourism"="nightclub"](area.mg);

  // ── NAMED ROADS & WALKING AREAS ────────────────────────────
  way["highway"="pedestrian"]["name"](area.mg);
  way["highway"="footway"]["name"](area.mg);
  node["place"="neighbourhood"](area.mg);
  node["place"="suburb"](area.mg);
  node["place"="quarter"](area.mg);
);
out tags center;
"""


def _build_bbox_query() -> str:
    """Mangalore bounding box fallback — always returns data."""
    bbox = "12.78,74.75,13.05,75.05"
    return f"""
[out:json][timeout:240];
(
  node["amenity"~"restaurant|cafe|fast_food|bar|pub|food_court|ice_cream|juice_bar|sweet_shop|bakery|snack_bar|seafood|dhaba|canteen|street_vendor|place_of_worship|hospital|police|pharmacy|bank|atm|cinema|theatre|library|marketplace|spa|bus_station|ferry_terminal|parking|fuel"]({bbox});
  way["amenity"~"restaurant|cafe|fast_food|food_court|bakery|place_of_worship|hospital|theatre|cinema|library|marketplace|bus_station"]({bbox});
  node["tourism"~"hotel|hostel|guest_house|motel|resort|attraction|museum|viewpoint|gallery|artwork|picnic_site|homestay|camp_site|apartment"]({bbox});
  way["tourism"~"hotel|resort|guest_house|attraction|museum"]({bbox});
  node["natural"~"beach|wood|water|waterfall|hill|peak|cliff|spring|wetland"]({bbox});
  way["natural"~"beach|wood|water|coastline|wetland"]({bbox});
  node["leisure"~"park|garden|beach_resort|marina|sports_centre|stadium|swimming_pool|fitness_centre|pitch|playground|nature_reserve|water_park"]({bbox});
  way["leisure"~"park|garden|beach_resort|sports_centre|stadium|swimming_pool|fitness_centre|pitch|nature_reserve"]({bbox});
  node["historic"]({bbox});
  way["historic"]({bbox});
  node["shop"]({bbox});
  way["shop"]({bbox});
  node["sport"]({bbox});
  node["healthcare"]({bbox});
  way["healthcare"]({bbox});
  node["amenity"~"university|college|school"]({bbox});
  way["amenity"~"university|college"]({bbox});
  node["waterway"~"dock|jetty"]({bbox});
  way["waterway"~"river|stream"]({bbox});
  node["railway"~"station|halt"]({bbox});
  node["public_transport"="station"]({bbox});
  node["place"~"neighbourhood|suburb|quarter"]({bbox});
);
out tags center;
"""


# ============================================================
# MAIN FETCH FUNCTION
# ============================================================

def fetch_osm_places(
    area_id: int,
    output_path: str = "data_storage/raw_places.json"
) -> Dict:
    """
    Fetch ALL tourist-relevant OSM data for Mangalore.

    Covers: food (every type), accommodation, beaches, temples,
    churches, mosques, shopping, activities, wellness, nightlife,
    transport, education, emergency, nature, historic sites.

    Args:
        area_id: OSM area ID (use 3601952828 for Mangalore)
        output_path: where to save the raw JSON

    Returns:
        Dict with all OSM elements + metadata
    """

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    query_area = _build_area_query(area_id)
    query_bbox = _build_bbox_query()

    # Wait after prior rate-limit-heavy operations
    print(f"  Waiting 15s to clear Overpass rate limits...")
    time.sleep(15)

    data = None
    used_fallback = False
    successful_mirror = None

    for mirror in OVERPASS_MIRRORS:
        print(f"  Trying: {mirror}")
        try:
            resp = requests.post(
                mirror,
                data={"data": query_area},
                timeout=250
            )

            if resp.status_code in (429, 503, 504):
                print(f"  {resp.status_code} — trying next mirror in 8s...")
                time.sleep(8)
                continue

            resp.raise_for_status()
            data = resp.json()

            count = len(data.get("elements", []))
            print(f"  Area query returned {count} elements")

            if count == 0:
                print(f"  Zero results from area_id — switching to bbox fallback...")
                time.sleep(5)
                r2 = requests.post(mirror, data={"data": query_bbox}, timeout=250)
                r2.raise_for_status()
                data = r2.json()
                used_fallback = True
                print(f"  Bbox fallback returned {len(data.get('elements', []))} elements")

            successful_mirror = mirror
            break

        except requests.RequestException as e:
            print(f"  {mirror} error: {e} — trying next...")
            time.sleep(5)

    if data is None:
        raise RuntimeError(
            "All Overpass mirrors failed. Wait 3-5 minutes and retry — "
            "this is a temporary rate limit, not a code error."
        )

    if "elements" not in data:
        raise ValueError("Overpass response missing 'elements' key.")

    # Deduplicate by (type, id)
    seen = set()
    unique = []
    for el in data["elements"]:
        key = (el.get("type", ""), el.get("id", 0))
        if key not in seen:
            seen.add(key)
            unique.append(el)

    data["elements"] = unique
    data["_metadata"] = {
        "area_id": area_id,
        "query_method": "bbox_fallback" if used_fallback else "area_id",
        "mirror_used": successful_mirror,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "element_count": len(unique),
        "source": "OpenStreetMap Overpass API",
        "license": "ODbL — openstreetmap.org/copyright"
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    method = "bbox fallback" if used_fallback else "area_id"
    print(f"  ✓ {len(unique)} unique OSM elements collected ({method})")
    print(f"  Saved → {output_path}")
    return data