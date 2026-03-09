"""
data_collector/normalizer.py  [DIVERSITY UPGRADE — v3]

WHAT THIS VERSION ADDS:
- Rich subcategory system: 80+ specific subcategories (not just "restaurant")
  e.g. "Coastal Seafood", "Udupi Vegetarian", "Street Food", "Rooftop Bar"
- price_hint extracted from OSM fee/charge tags
- cuisine extracted and stored cleanly
- Rating extracted if present (some OSM nodes have stars tag)
- wheelchair accessibility stored
- description stored (up to 500 chars)
- alt_name (trade name vs official name)
- All extra fields stored in a clean JSON block in decision_trace
- Tourist relevance score: places with website/phone/hours score higher
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict

from core.base_models import BaseEntity, Domain


# ============================================================
# DOMAIN MAPPING — COMPREHENSIVE
# ============================================================

def map_to_domain(tags: dict) -> Domain:
    amenity         = tags.get("amenity", "")
    tourism         = tags.get("tourism", "")
    historic        = tags.get("historic", "")
    natural         = tags.get("natural", "")
    leisure         = tags.get("leisure", "")
    shop            = tags.get("shop", "")
    sport           = tags.get("sport", "")
    healthcare      = tags.get("healthcare", "")
    waterway        = tags.get("waterway", "")
    public_transport= tags.get("public_transport", "")
    emergency       = tags.get("emergency", "")
    building        = tags.get("building", "")
    place           = tags.get("place", "")

    # EMERGENCY & HEALTH SERVICES
    if amenity in ("hospital", "police", "fire_station", "pharmacy") \
       or emergency \
       or healthcare in ("hospital", "clinic", "doctor"):
        return Domain.EMERGENCY

    # STAY / ACCOMMODATION
    if tourism in ("hotel", "hostel", "guest_house", "motel", "resort",
                   "camp_site", "apartment", "homestay") \
       or building in ("hotel",):
        return Domain.STAY

    # FOOD & DRINK — every type
    if amenity in ("restaurant", "cafe", "fast_food", "bar", "pub",
                   "food_court", "ice_cream", "juice_bar", "biryani_house",
                   "sweet_shop", "bakery", "snack_bar", "seafood", "dhaba",
                   "canteen", "street_vendor", "nightclub") \
       or shop in ("bakery", "confectionery", "chocolate", "seafood",
                   "fish", "deli", "beverages", "alcohol"):
        return Domain.FOOD

    # TRANSPORT
    if amenity in ("bus_station", "ferry_terminal", "taxi", "parking",
                   "fuel", "car_rental", "bicycle_rental") \
       or public_transport in ("station", "stop_position", "platform") \
       or tags.get("railway") in ("station", "halt") \
       or tags.get("aeroway") in ("aerodrome", "terminal"):
        return Domain.TRANSPORT

    # CULTURE & EXPLORE
    if tourism in ("museum", "attraction", "artwork", "gallery",
                   "viewpoint", "information", "theme_park", "zoo") \
       or historic \
       or amenity in ("place_of_worship", "theatre", "cinema", "arts_centre",
                      "community_centre", "library", "exhibition_centre") \
       or building in ("temple", "church", "mosque", "chapel", "heritage") \
       or tags.get("heritage"):
        return Domain.EXPLORE

    # ACTIVITIES & SPORTS
    if sport \
       or leisure in ("stadium", "sports_centre", "swimming_pool",
                      "fitness_centre", "golf_course", "pitch", "track",
                      "water_park", "amusement_arcade"):
        return Domain.ACTIVITIES

    # WELLNESS
    if amenity in ("spa",) \
       or shop in ("massage", "beauty", "hairdresser") \
       or healthcare in ("ayurveda",) \
       or amenity in ("yoga",):
        return Domain.ACTIVITIES

    # EDUCATION
    if amenity in ("university", "college", "school"):
        return Domain.EXPLORE

    # NATURE / PLACES
    if natural or waterway \
       or leisure in ("park", "beach_resort", "garden", "nature_reserve",
                      "marina", "playground") \
       or tourism in ("picnic_site",):
        return Domain.PLACES

    # SHOPPING & LOCAL LIFE
    if shop or amenity in ("marketplace", "market", "shopping_centre") \
       or tags.get("landuse") in ("retail",):
        return Domain.LOCAL

    # NEIGHBOURHOOD / AREA
    if place in ("neighbourhood", "suburb", "quarter"):
        return Domain.PLACES

    return Domain.PLACES


# ============================================================
# SUBCATEGORY — RICH SPECIFIC LABELS
# ============================================================

def get_subcategory(tags: dict) -> str:
    """
    Returns a specific, human-readable subcategory.
    This is what a tour guide would say: "Coastal Seafood Restaurant",
    not just "restaurant".
    """
    amenity  = tags.get("amenity", "")
    tourism  = tags.get("tourism", "")
    historic = tags.get("historic", "")
    natural  = tags.get("natural", "")
    leisure  = tags.get("leisure", "")
    shop     = tags.get("shop", "")
    sport    = tags.get("sport", "")
    cuisine  = tags.get("cuisine", "")
    religion = tags.get("religion", "")
    building = tags.get("building", "")
    waterway = tags.get("waterway", "")

    # ── FOOD ──────────────────────────────────────────────────
    if amenity == "restaurant":
        if cuisine:
            c = cuisine.lower()
            if any(x in c for x in ("seafood", "fish", "prawn", "crab")):
                return "Seafood Restaurant"
            if any(x in c for x in ("tulu", "mangalore", "coastal", "konkani")):
                return "Coastal Karnataka Restaurant"
            if any(x in c for x in ("udupi", "vegetarian", "veg")):
                return "Udupi Vegetarian Restaurant"
            if any(x in c for x in ("biryani",)):
                return "Biryani Restaurant"
            if any(x in c for x in ("chinese",)):
                return "Chinese Restaurant"
            if any(x in c for x in ("mughlai", "north_indian", "punjabi")):
                return "North Indian Restaurant"
            if any(x in c for x in ("south_indian",)):
                return "South Indian Restaurant"
            if any(x in c for x in ("pizza", "italian")):
                return "Pizza / Italian"
            if any(x in c for x in ("burger", "fast_food", "american")):
                return "Fast Food / Burger"
            return f"{cuisine.title()} Restaurant"
        return "Restaurant"
    if amenity == "fast_food":
        return "Fast Food / Street Eats"
    if amenity == "cafe":
        return "Café / Coffee Shop"
    if amenity == "bar":
        return "Bar / Drinks"
    if amenity == "pub":
        return "Pub"
    if amenity == "nightclub":
        return "Nightclub / Live Music"
    if amenity in ("juice_bar",):
        return "Juice Bar / Fresh Drinks"
    if amenity == "ice_cream":
        return "Ice Cream / Desserts"
    if amenity in ("sweet_shop", "confectionery"):
        return "Sweets & Mithai Shop"
    if amenity == "bakery" or shop == "bakery":
        return "Bakery / Breads & Cakes"
    if amenity in ("dhaba",):
        return "Dhaba / Roadside Eatery"
    if amenity == "street_vendor":
        return "Street Food Stall"
    if amenity == "canteen":
        return "Canteen / Mess"
    if amenity == "food_court":
        return "Food Court"
    if amenity == "snack_bar":
        return "Snack Bar"
    if shop in ("seafood", "fish"):
        return "Fish Market / Seafood Shop"
    if shop in ("butcher",):
        return "Meat Shop"
    if shop in ("greengrocer",):
        return "Fresh Produce / Vegetable Market"
    if amenity in ("seafood",):
        return "Seafood Spot"

    # ── ACCOMMODATION ─────────────────────────────────────────
    if tourism == "hotel" or building == "hotel":
        stars = tags.get("stars", "")
        if stars in ("5",): return "5-Star Hotel"
        if stars in ("4",): return "4-Star Hotel"
        if stars in ("3",): return "3-Star Hotel"
        return "Hotel"
    if tourism == "hostel": return "Hostel / Backpacker Stay"
    if tourism == "guest_house": return "Guest House / Lodge"
    if tourism == "motel": return "Motel"
    if tourism == "resort": return "Resort"
    if tourism == "homestay": return "Homestay"
    if tourism == "apartment": return "Service Apartment"
    if tourism == "camp_site": return "Campsite"

    # ── BEACHES ───────────────────────────────────────────────
    if natural == "beach": return "Beach"
    if leisure == "beach_resort": return "Beach Resort"
    if waterway == "dock": return "Boat Dock / Jetty"
    if waterway == "jetty": return "Jetty / Ferry Point"
    if leisure == "marina": return "Marina"
    if natural == "coastline": return "Coastal Area"

    # ── NATURE ────────────────────────────────────────────────
    if natural == "waterfall": return "Waterfall"
    if natural == "water": return "Lake / Pond"
    if natural in ("wood", "forest"): return "Forest / Green Area"
    if natural == "hill": return "Hill / Hillock"
    if natural == "peak": return "Hilltop / Peak"
    if natural == "wetland": return "Wetland / Backwater"
    if natural == "spring": return "Natural Spring"
    if natural == "cliff": return "Cliff / Viewpoint"
    if leisure == "park": return "Park / Garden"
    if leisure == "garden": return "Garden"
    if leisure == "nature_reserve": return "Nature Reserve / Wildlife Spot"
    if tourism == "picnic_site": return "Picnic Spot"

    # ── RELIGIOUS SITES ───────────────────────────────────────
    if amenity == "place_of_worship" or building in ("temple", "church", "mosque", "chapel"):
        if religion == "hindu" or building == "temple":
            return "Hindu Temple"
        if religion == "christian" or building in ("church", "chapel"):
            return "Church / Chapel"
        if religion == "muslim" or building == "mosque":
            return "Mosque / Dargah"
        if religion == "jain":
            return "Jain Temple"
        if religion == "sikh":
            return "Gurudwara"
        if religion == "buddhist":
            return "Buddhist Temple"
        return "Place of Worship"

    # ── HISTORIC ──────────────────────────────────────────────
    if historic == "castle": return "Fort / Castle"
    if historic == "ruins": return "Ancient Ruins"
    if historic == "monument": return "Monument / Memorial"
    if historic == "archaeological_site": return "Archaeological Site"
    if historic == "building": return "Heritage Building"
    if historic == "lighthouse": return "Lighthouse"
    if historic == "battlefield": return "Historical Site"
    if historic: return f"Historic Site ({historic})"

    # ── CULTURE ───────────────────────────────────────────────
    if tourism == "museum": return "Museum"
    if tourism == "gallery": return "Art Gallery"
    if tourism == "artwork": return "Public Art / Mural"
    if tourism == "viewpoint": return "Scenic Viewpoint"
    if amenity == "theatre": return "Theatre / Performing Arts"
    if amenity == "cinema": return "Cinema / Movie Hall"
    if amenity == "arts_centre": return "Arts & Culture Centre"
    if amenity == "library": return "Library"
    if amenity == "community_centre": return "Community Hall"

    # ── ATTRACTIONS ───────────────────────────────────────────
    if tourism == "attraction": return "Tourist Attraction"
    if tourism == "theme_park": return "Amusement / Theme Park"
    if tourism == "zoo": return "Zoo / Animal Park"
    if tourism == "information": return "Tourist Info Centre"

    # ── SHOPPING ──────────────────────────────────────────────
    if shop == "spices": return "Spice Shop"
    if shop in ("supermarket", "grocery"): return "Supermarket / Grocery"
    if shop == "clothes": return "Clothing Store"
    if shop == "saree": return "Saree / Silk Shop"
    if shop == "jewellery": return "Jewellery Store"
    if shop == "electronics": return "Electronics Store"
    if shop == "hardware": return "Hardware Store"
    if shop == "gift": return "Gift / Souvenir Shop"
    if shop == "books": return "Bookstore"
    if shop == "pharmacy": return "Medical / Pharmacy"
    if shop == "optician": return "Optician"
    if shop == "mobile_phone": return "Mobile Phones"
    if amenity == "marketplace": return "Bazaar / Marketplace"
    if amenity == "market": return "Local Market"
    if amenity == "shopping_centre": return "Shopping Mall"
    if shop: return f"Shop ({shop.replace('_', ' ').title()})"

    # ── SPORTS & ACTIVITIES ───────────────────────────────────
    if leisure == "swimming_pool": return "Swimming Pool"
    if leisure == "sports_centre": return "Sports Centre"
    if leisure == "stadium": return "Stadium"
    if leisure == "fitness_centre": return "Gym / Fitness Centre"
    if leisure == "golf_course": return "Golf Course"
    if leisure == "water_park": return "Water Park"
    if sport: return f"{sport.replace('_', ' ').title()} Facility"

    # ── WELLNESS ──────────────────────────────────────────────
    if amenity == "spa": return "Spa & Wellness"
    if shop == "massage": return "Massage / Therapy Centre"
    if shop == "beauty": return "Beauty Parlour / Salon"

    # ── TRANSPORT ─────────────────────────────────────────────
    if amenity == "bus_station": return "Bus Station / KSRTC"
    if amenity == "ferry_terminal": return "Ferry Terminal"
    if tags.get("railway") == "station": return "Railway Station"
    if tags.get("aeroway"): return "Airport"
    if amenity == "fuel": return "Petrol Station"
    if amenity == "parking": return "Parking Area"

    # ── EDUCATION ─────────────────────────────────────────────
    if amenity == "university": return "University"
    if amenity == "college": return "College"
    if amenity == "school": return "School"

    # ── SERVICES ──────────────────────────────────────────────
    if amenity == "hospital": return "Hospital"
    if amenity == "police": return "Police Station"
    if amenity == "pharmacy": return "Pharmacy / Medical Store"
    if amenity == "bank": return "Bank"
    if amenity == "atm": return "ATM"
    if amenity == "post_office": return "Post Office"

    # ── NEIGHBOURHOOD ─────────────────────────────────────────
    if tags.get("place") in ("neighbourhood", "suburb", "quarter"):
        return "Neighbourhood / Area"

    return "Point of Interest"


# ============================================================
# STRUCTURAL SCORE — BASED ON DATA COMPLETENESS
# ============================================================

def compute_structural_score(tags: dict) -> float:
    """
    Score 0.0–1.0 based on how much useful data the OSM entry has.
    More complete entries = more trustworthy = higher score.
    """
    score = 0.20  # base for existing at all

    if tags.get("name"):             score += 0.10
    if tags.get("opening_hours"):    score += 0.15
    if tags.get("phone") or tags.get("contact:phone"): score += 0.10
    if tags.get("website") or tags.get("contact:website"): score += 0.10
    if tags.get("cuisine"):          score += 0.05
    if tags.get("addr:street") or tags.get("addr:full"): score += 0.10
    if tags.get("description"):      score += 0.05
    if tags.get("wheelchair"):       score += 0.03
    if tags.get("stars"):            score += 0.05
    if tags.get("wikidata"):         score += 0.05
    if tags.get("wikipedia"):        score += 0.05
    if tags.get("brand") or tags.get("operator"): score += 0.02

    return round(min(score, 1.0), 3)


# ============================================================
# MAIN NORMALIZER
# ============================================================

def normalize_to_entities(raw_file_path: str) -> List[BaseEntity]:
    """
    Convert raw OSM JSON → rich BaseEntity list.

    Every entity gets:
    - Correct domain (FOOD, STAY, EXPLORE, PLACES, etc.)
    - Specific subcategory (e.g. "Coastal Seafood Restaurant")
    - Structural score based on data completeness
    - All available contact/practical info stored in decision_trace
    - Cuisine, opening hours, accessibility, description

    Args:
        raw_file_path: path to raw OSM JSON from fetch_osm_places()

    Returns:
        List[BaseEntity] ready for DataCorePipeline
    """

    with open(raw_file_path, encoding="utf-8") as f:
        raw_data = json.load(f)

    entities: List[BaseEntity] = []
    seen_ids: set = set()

    total = len(raw_data.get("elements", []))
    skipped_unnamed = 0
    skipped_no_coords = 0

    domain_counts: Dict[str, int] = {}
    subcategory_counts: Dict[str, int] = {}

    for element in raw_data.get("elements", []):

        el_id = element.get("id")
        if el_id in seen_ids:
            continue
        seen_ids.add(el_id)

        tags = element.get("tags", {})

        # Name — try all variants
        name = (
            tags.get("name")
            or tags.get("name:en")
            or tags.get("alt_name")
            or tags.get("name:kn")
            or tags.get("name:tulu")
        )

        if not name:
            skipped_unnamed += 1
            continue

        # Coordinates
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")

        if lat is None or lon is None:
            skipped_no_coords += 1
            continue

        # Core classification
        domain = map_to_domain(tags)
        primary_type = next(
            (tags.get(k) for k in ("amenity", "tourism", "historic", "natural",
                                    "leisure", "shop", "sport", "healthcare",
                                    "waterway", "building") if tags.get(k)),
            "general"
        )
        subcategory = get_subcategory(tags)

        # Build entity
        entity = BaseEntity(
            name=name.strip(),
            domain=domain,
            category=primary_type,
            subcategory=subcategory,
            latitude=float(lat),
            longitude=float(lon),
            sources=["OSM"],
            created_at=datetime.now(timezone.utc)
        )

        # Structural score from data completeness
        struct_score = compute_structural_score(tags)
        entity.update_structural_score(struct_score)

        # Build rich extra fields block
        extra: dict = {}

        # Address
        addr = tags.get("addr:full") or (
            " ".join(filter(None, [
                tags.get("addr:housenumber", ""),
                tags.get("addr:street", ""),
                tags.get("addr:locality", ""),
                tags.get("addr:city", ""),
                tags.get("addr:postcode", ""),
            ]))
        ).strip()
        if addr:
            extra["address"] = addr

        # Contact
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile")
        if phone:
            extra["phone"] = phone

        website = tags.get("website") or tags.get("contact:website") or tags.get("url")
        if website:
            extra["website"] = website

        # Hours
        if tags.get("opening_hours"):
            extra["opening_hours"] = tags["opening_hours"]

        # Food specific
        if tags.get("cuisine"):
            extra["cuisine"] = tags["cuisine"]

        if tags.get("diet:vegetarian"):
            extra["vegetarian"] = tags["diet:vegetarian"]

        if tags.get("diet:vegan"):
            extra["vegan"] = tags["diet:vegan"]

        # Price / fee
        fee = tags.get("fee") or tags.get("charge") or tags.get("price")
        if fee:
            extra["price_info"] = fee

        # Accommodation specific
        if tags.get("stars"):
            extra["stars"] = tags["stars"]

        if tags.get("rooms"):
            extra["rooms"] = tags["rooms"]

        # Accessibility
        if tags.get("wheelchair"):
            extra["wheelchair"] = tags["wheelchair"]

        # Description
        desc = tags.get("description") or tags.get("note")
        if desc:
            extra["description"] = desc[:500]

        # Alternative names
        alt = tags.get("alt_name") or tags.get("old_name") or tags.get("loc_name")
        if alt and alt != name:
            extra["alt_name"] = alt

        # Kannada / Tulu name
        kn = tags.get("name:kn")
        tulu = tags.get("name:tulu")
        if kn:   extra["name_kannada"] = kn
        if tulu: extra["name_tulu"] = tulu

        # Wikipedia / Wikidata links
        if tags.get("wikipedia"):
            extra["wikipedia"] = tags["wikipedia"]
        if tags.get("wikidata"):
            extra["wikidata"] = tags["wikidata"]

        # Brand / operator
        if tags.get("brand"):    extra["brand"] = tags["brand"]
        if tags.get("operator"): extra["operator"] = tags["operator"]

        # Encode all extras into decision_trace
        if extra:
            entity.decision_trace.append(
                f"OSM_EXTRA:{json.dumps(extra, ensure_ascii=False)}"
            )

        entity.decision_trace.append(f"OSM_ID:{el_id}")
        entity.decision_trace.append(f"OSM_TYPE:{element.get('type','node')}")

        entities.append(entity)

        # Track stats
        d = domain.value
        domain_counts[d] = domain_counts.get(d, 0) + 1
        subcategory_counts[subcategory] = subcategory_counts.get(subcategory, 0) + 1

    # Summary
    print(f"\n  ✓ Normalized {len(entities)} entities from {total} raw elements")
    print(f"    Skipped: {skipped_unnamed} unnamed, {skipped_no_coords} no-coords\n")

    print("  Domain breakdown:")
    for dom, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"    {dom:<20} {count}")

    print("\n  Top subcategories:")
    for sub, count in sorted(subcategory_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"    {sub:<40} {count}")

    return entities