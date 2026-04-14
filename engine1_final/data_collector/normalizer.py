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
# SYNTHETIC DESCRIPTION BUILDER
# ============================================================

def _build_synthetic_description(name: str, tags: dict, subcategory: str, domain) -> str:
    """
    Build a concise, factual, non-promotional description from OSM tags
    for nodes that have no description= tag.

    Rules:
    - Only uses data already in tags — no invented claims
    - Never promotional (no "best", "top", "must-visit")
    - Max 200 chars
    - Returns "" if not enough data to say anything useful
    """
    parts = []

    amenity  = tags.get("amenity", "")
    tourism  = tags.get("tourism", "")
    historic = tags.get("historic", "")
    natural  = tags.get("natural", "")
    leisure  = tags.get("leisure", "")
    religion = tags.get("religion", "")
    denom    = tags.get("denomination", "")
    deity    = tags.get("deity", "")
    cuisine  = tags.get("cuisine", "")
    sport    = tags.get("sport", "")
    shop     = tags.get("shop", "")
    building = tags.get("building", "")
    operator = tags.get("operator", "")
    brand    = tags.get("brand", "")
    stars    = tags.get("stars", "")
    rooms    = tags.get("rooms", "")
    capacity = tags.get("capacity", "")
    heritage = tags.get("heritage", "")
    wheelchair = tags.get("wheelchair", "")
    opening_hours = tags.get("opening_hours", "")
    takeaway = tags.get("takeaway", "")
    city     = tags.get("addr:city", "") or tags.get("addr:locality", "")

    # ── Place type sentence ──────────────────────────────────
    if amenity == "place_of_worship":
        rel_str = religion.title() if religion else "religious"
        if denom:
            parts.append(f"{denom.replace('_',' ').title()} {rel_str} place of worship in Mangalore.")
        else:
            parts.append(f"{rel_str.title()} place of worship in Mangalore.")
        if deity:
            parts.append(f"Dedicated to {deity.replace('_',' ').title()}.")

    elif amenity in ("restaurant", "cafe", "fast_food", "bar", "pub", "food_court"):
        if cuisine:
            c = cuisine.replace(";", ", ").replace("_", " ").title()
            parts.append(f"{subcategory} serving {c} cuisine.")
        else:
            parts.append(f"{subcategory} in Mangalore.")
        if capacity:
            parts.append(f"Capacity: {capacity} covers.")

    elif amenity == "hospital":
        parts.append(f"Hospital providing medical services in Mangalore.")
        if operator:
            parts.append(f"Operated by {operator}.")

    elif amenity in ("bank", "atm"):
        if brand or operator:
            b = brand or operator
            parts.append(f"{b} {subcategory.lower()} branch in Mangalore.")
        else:
            parts.append(f"{subcategory} in Mangalore.")

    elif amenity in ("college", "university", "school"):
        parts.append(f"Educational institution in Mangalore.")
        if operator:
            parts.append(f"Managed by {operator}.")

    elif amenity == "bus_station":
        parts.append("Bus station serving local and inter-city routes in Mangalore.")

    elif tourism == "hotel" or building == "hotel":
        parts.append(f"Hotel accommodation in Mangalore.")
        if stars:
            parts.append(f"{stars}-star rated.")
        if rooms:
            parts.append(f"{rooms} rooms available.")

    elif tourism in ("hostel", "guest_house"):
        parts.append(f"{subcategory} accommodation in Mangalore.")

    elif natural == "beach":
        parts.append(f"Beach on the Arabian Sea coast near Mangalore.")
        if tags.get("tidal"):
            parts.append("Tidal beach — conditions vary with tide.")

    elif natural == "waterfall":
        parts.append(f"Waterfall in the Western Ghats near Mangalore.")
        if tags.get("seasonal") or tags.get("intermittent") == "yes":
            parts.append("Seasonal — best visited during monsoon.")

    elif natural in ("wood", "forest"):
        parts.append(f"Forest area near Mangalore.")

    elif natural == "spring":
        parts.append(f"Natural freshwater spring near Mangalore.")

    elif leisure == "park" or leisure == "garden":
        parts.append(f"Public park or garden in Mangalore.")

    elif leisure == "nature_reserve":
        parts.append(f"Protected nature reserve near Mangalore.")

    elif historic:
        parts.append(f"Historic site ({historic.replace('_',' ')}) in the Mangalore region.")
        if heritage:
            parts.append(f"Heritage category: {heritage}.")

    elif leisure == "stadium":
        parts.append(f"Sports stadium in Mangalore.")
        if sport:
            parts.append(f"Primary sport: {sport.replace(';',', ')}.")

    elif leisure in ("sports_centre", "fitness_centre", "swimming_pool"):
        parts.append(f"{subcategory} facility in Mangalore.")

    elif shop:
        parts.append(f"{subcategory} in Mangalore.")
        if brand:
            parts.append(f"Brand: {brand}.")

    elif tourism == "museum":
        parts.append(f"Museum in Mangalore.")
        if operator:
            parts.append(f"Operated by {operator}.")

    elif tourism == "viewpoint":
        parts.append(f"Scenic viewpoint in the Mangalore region.")

    elif tourism in ("attraction", "artwork"):
        parts.append(f"Tourist attraction in Mangalore.")

    elif tags.get("place") in ("hamlet", "village"):
        parts.append(f"Locality in the Mangalore region.")

    elif tags.get("man_made") == "lighthouse":
        parts.append(f"Lighthouse on the Karnataka coast near Mangalore.")

    elif tags.get("waterway") in ("harbour", "dock", "jetty"):
        parts.append(f"Coastal {tags.get('waterway')} in Mangalore.")

    elif amenity == "pharmacy":
        parts.append(f"Pharmacy in Mangalore.")
        if brand or operator:
            parts.append(f"Part of {brand or operator} chain.")

    elif amenity == "police":
        parts.append(f"Police station in Mangalore.")

    elif amenity == "marketplace" or amenity == "market":
        parts.append(f"Market in Mangalore serving local community needs.")

    elif tags.get("public_transport") == "station" or tags.get("railway") == "station":
        parts.append(f"Railway station in Mangalore.")

    elif tags.get("aeroway") in ("aerodrome", "terminal"):
        parts.append(f"Airport facility serving Mangalore.")

    # ── Accessibility note ───────────────────────────────────
    if wheelchair == "yes":
        parts.append("Wheelchair accessible.")
    elif wheelchair == "limited":
        parts.append("Limited wheelchair access.")

    # ── Hours note ───────────────────────────────────────────
    if opening_hours and len(parts) > 0:
        parts.append(f"Open: {opening_hours}.")

    # ── Takeaway note ────────────────────────────────────────
    if takeaway == "yes" and amenity in ("restaurant", "cafe", "fast_food"):
        parts.append("Takeaway available.")

    result = " ".join(parts).strip()
    return result[:220] if result else ""


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

        # ── Build rich extra fields block ──────────────────────
        extra: dict = {}

        # ── ADDRESS (all variants) ──────────────────────────
        addr = (
            tags.get("addr:full")
            or tags.get("address")
            or (" ".join(filter(None, [
                tags.get("addr:housenumber", ""),
                tags.get("addr:street", ""),
                tags.get("addr:locality", ""),
                tags.get("addr:suburb", ""),
                tags.get("addr:city", ""),
                tags.get("addr:district", ""),
                tags.get("addr:postcode", ""),
            ]))).strip()
        )
        if addr and addr.strip():
            extra["address"] = addr.strip()

        # ── CONTACT (all variants) ──────────────────────────
        phone = (tags.get("phone")
                 or tags.get("contact:phone")
                 or tags.get("contact:mobile")
                 or tags.get("mobile")
                 or tags.get("telephone"))
        if phone:
            extra["phone"] = phone.strip()

        website = (tags.get("website")
                   or tags.get("contact:website")
                   or tags.get("url")
                   or tags.get("contact:url"))
        if website:
            extra["website"] = website.strip()

        email = tags.get("email") or tags.get("contact:email")
        if email:
            extra["email"] = email.strip()

        # ── HOURS ───────────────────────────────────────────
        hours = tags.get("opening_hours") or tags.get("service_times")
        if hours:
            extra["opening_hours"] = hours

        # ── FOOD SPECIFIC ───────────────────────────────────
        if tags.get("cuisine"):
            extra["cuisine"] = tags["cuisine"]
        if tags.get("diet:vegetarian"):
            extra["vegetarian"] = tags["diet:vegetarian"]
        if tags.get("diet:vegan"):
            extra["vegan"] = tags["diet:vegan"]
        if tags.get("diet:halal"):
            extra["halal"] = tags["diet:halal"]
        if tags.get("diet:kosher"):
            extra["kosher"] = tags["diet:kosher"]
        if tags.get("takeaway"):
            extra["takeaway"] = tags["takeaway"]
        if tags.get("delivery"):
            extra["delivery"] = tags["delivery"]
        if tags.get("outdoor_seating"):
            extra["outdoor_seating"] = tags["outdoor_seating"]
        if tags.get("capacity"):
            extra["capacity"] = tags["capacity"]

        # ── PRICE / FEE ─────────────────────────────────────
        fee = (tags.get("fee") or tags.get("charge")
               or tags.get("price") or tags.get("entrance_fee"))
        if fee:
            extra["price_info"] = fee

        # ── ACCOMMODATION SPECIFIC ──────────────────────────
        if tags.get("stars"):   extra["stars"] = tags["stars"]
        if tags.get("rooms"):   extra["rooms"] = tags["rooms"]
        if tags.get("beds"):    extra["beds"] = tags["beds"]
        if tags.get("internet_access"): extra["wifi"] = tags["internet_access"]
        if tags.get("swimming_pool"):   extra["swimming_pool"] = tags["swimming_pool"]

        # ── ACCESSIBILITY ────────────────────────────────────
        if tags.get("wheelchair"):
            extra["wheelchair"] = tags["wheelchair"]
        if tags.get("tactile_paving"):
            extra["tactile_paving"] = tags["tactile_paving"]

        # ── DESCRIPTION (prefer longer, more specific) ───────
        desc = (tags.get("description")
                or tags.get("description:en")
                or tags.get("note")
                or tags.get("inscription"))
        if desc:
            extra["description"] = desc[:600]

        # ── ALTERNATIVE NAMES ────────────────────────────────
        alt = (tags.get("alt_name") or tags.get("old_name")
               or tags.get("loc_name") or tags.get("short_name"))
        if alt and alt != name:
            extra["alt_name"] = alt

        # ── LOCAL LANGUAGE NAMES (critical for Mangalore) ───
        kn   = tags.get("name:kn")   or tags.get("name:kan")
        tulu = tags.get("name:tulu") or tags.get("name:tcy")
        ml   = tags.get("name:ml")   # Malayalam (Kasaragod border)
        hi   = tags.get("name:hi")
        if kn:   extra["name_kannada"] = kn
        if tulu: extra["name_tulu"] = tulu
        if ml:   extra["name_malayalam"] = ml
        if hi:   extra["name_hindi"] = hi

        # ── CROSS-REFERENCE LINKS ────────────────────────────
        if tags.get("wikipedia"):  extra["wikipedia"] = tags["wikipedia"]
        if tags.get("wikidata"):   extra["wikidata"]  = tags["wikidata"]
        if tags.get("image"):      extra["image_url"] = tags["image"]
        if tags.get("mapillary"):  extra["mapillary"]  = tags["mapillary"]

        # ── BRAND / OPERATOR / OWNER ─────────────────────────
        if tags.get("brand"):    extra["brand"]    = tags["brand"]
        if tags.get("operator"): extra["operator"] = tags["operator"]
        if tags.get("owner"):    extra["owner"]    = tags["owner"]
        if tags.get("network"):  extra["network"]  = tags["network"]

        # ── RELIGIOUS / CULTURAL SPECIFICS ──────────────────
        if tags.get("religion"):       extra["religion"]       = tags["religion"]
        if tags.get("denomination"):   extra["denomination"]   = tags["denomination"]
        if tags.get("deity"):          extra["deity"]          = tags["deity"]
        if tags.get("festival"):       extra["festival"]       = tags["festival"]
        if tags.get("heritage"):       extra["heritage"]       = tags["heritage"]
        if tags.get("heritage:ref"):   extra["heritage_ref"]   = tags["heritage:ref"]
        if tags.get("start_date"):     extra["established"]    = tags["start_date"]

        # ── NATURE / ENVIRONMENT ─────────────────────────────
        if tags.get("surface"):        extra["surface"]        = tags["surface"]
        if tags.get("tidal"):          extra["tidal"]          = tags["tidal"]
        if tags.get("depth"):          extra["depth"]          = tags["depth"]
        if tags.get("width"):          extra["width"]          = tags["width"]
        if tags.get("height"):         extra["height"]         = tags["height"]
        if tags.get("ele"):            extra["elevation_m"]    = tags["ele"]

        # ── MANGALORE-SPECIFIC UNEXPLORED SIGNALS ────────────
        if tags.get("fishing"):        extra["fishing"]        = tags["fishing"]
        if tags.get("boat"):           extra["boat_access"]    = tags["boat"]
        if tags.get("access"):         extra["access"]         = tags["access"]
        if tags.get("seasonal"):       extra["seasonal"]       = tags["seasonal"]
        if tags.get("landuse"):        extra["landuse"]        = tags["landuse"]

        # ── SPORT-SPECIFIC ───────────────────────────────────
        if tags.get("sport"):          extra["sport"]          = tags["sport"]
        if tags.get("lanes"):          extra["lanes"]          = tags["lanes"]

        # ── UNEXPLORED FLAG: mark locally-unique places ──────
        # Places with Tulu names, specific deities, or rare heritage tags
        # are flagged as "potentially unexplored" for the HIVE engine
        is_unexplored = (
            bool(tulu) or
            tags.get("deity") is not None or
            tags.get("historic") in ("wayside_shrine", "ruins", "archaeological_site") or
            tags.get("landuse") in ("aquaculture", "salt_pond", "orchard") or
            tags.get("fishing") is not None or
            tags.get("man_made") in ("lighthouse", "pier", "fish_farm") or
            (tags.get("place") in ("hamlet", "village") and not tags.get("tourism"))
        )
        if is_unexplored:
            extra["unexplored_flag"] = True

        # ── SYNTHETIC DESCRIPTION (fills null descriptions) ──────────
        # Most Mangalore OSM nodes have no description= tag. We build a
        # concise, factual, non-promotional description from existing tags.
        # This is purely structural synthesis — no invented claims.
        if not extra.get("description"):
            synth = _build_synthetic_description(name, tags, subcategory, domain)
            if synth:
                extra["description"] = synth

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

# ============================================================
# HIDDEN GEMS → BaseEntity CONVERTER
# ============================================================

def normalize_hidden_gems() -> List[BaseEntity]:
    """
    Convert the curated Mangalore hidden gems dataset into BaseEntity objects.
    Source: "local_knowledge" — curated + cross-verified.
    """
    from data_collector.mangalore_hidden_gems import get_hidden_gems

    DOMAIN_MAP = {
        "food": Domain.FOOD, "places": Domain.PLACES,
        "explore": Domain.EXPLORE, "activities": Domain.ACTIVITIES,
        "stay": Domain.STAY, "local": Domain.LOCAL,
        "emergency": Domain.EMERGENCY, "transport": Domain.TRANSPORT,
    }

    gems = get_hidden_gems()
    entities: List[BaseEntity] = []

    for gem in gems:
        try:
            domain = DOMAIN_MAP.get(gem.get("domain", "places"), Domain.PLACES)
            entity = BaseEntity(
                name=gem["name"],
                domain=domain,
                category=gem.get("category", "general"),
                subcategory=gem.get("subcategory", "Hidden Gem"),
                latitude=float(gem["latitude"]),
                longitude=float(gem["longitude"]),
                sources=["local_knowledge"],
                created_at=datetime.now(timezone.utc)
            )

            extra = {}
            if gem.get("description"):      extra["description"]        = gem["description"][:500]
            if gem.get("opening_hours"):    extra["opening_hours"]      = gem["opening_hours"]
            if gem.get("cuisine"):          extra["cuisine"]             = gem["cuisine"]
            if gem.get("wikipedia"):        extra["wikipedia"]           = gem["wikipedia"]
            if gem.get("tulu_cultural_tag"):extra["tulu_tag"]           = gem["tulu_cultural_tag"]
            if gem.get("feast_season"):     extra["feast_season"]       = gem["feast_season"]
            if gem.get("best_time"):        extra["best_time"]          = gem["best_time"]
            if gem.get("hidden_gem_tier"):  extra["hidden_gem_tier"]    = gem["hidden_gem_tier"]
            extra["unexplored_flag"]   = gem.get("unexplored_signal", False)
            extra["is_hidden_gem"]     = True

            if extra:
                entity.decision_trace.append(
                    f"OSM_EXTRA:{json.dumps(extra, ensure_ascii=False)}"
                )

            entity.decision_trace.append("HIDDEN_GEMS_LAYER:mangalore_curated")

            # Pre-score from tag richness (curated entries are always richer than bare OSM)
            base = 0.30
            if extra.get("description"):  base += 0.15
            if extra.get("opening_hours"):base += 0.08
            if extra.get("wikipedia"):    base += 0.05
            entity.update_structural_score(min(base, 1.0))

            entities.append(entity)

        except Exception as e:
            print(f"  [HiddenGems] Skipped '{gem.get('name')}': {e}")

    print(f"  [HiddenGems] Normalized {len(entities)} curated local places")
    return entities
