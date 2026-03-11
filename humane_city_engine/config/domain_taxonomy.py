"""
config/domain_taxonomy.py

MASTER DOMAIN TAXONOMY — single source of truth for all 27 domains.

Every collector, normalizer, and store builder imports from here.
Adding a subcategory here automatically propagates everywhere.
"""

from typing import Dict, List


# ============================================================
# CANONICAL DOMAIN → SUBCATEGORY MAP
# 27 domains, 135 subcategories
# ============================================================

TAXONOMY: Dict[str, List[str]] = {

    "places_landmarks": [
        "Historical Monument",
        "Heritage Building",
        "City Landmark",
        "Fort / Watchtower",
        "Public Square",
        "Lighthouse",
        "Colonial Structure",
        "Gateway / Arch",
    ],

    "explore_sites": [
        "Scenic Viewpoint",
        "Coastal Viewpoint",
        "Walking Area",
        "Cultural Street",
        "Photography Location",
        "Hilltop",
        "Cliffside",
        "Riverside Walk",
    ],

    "activities": [
        "Boating",
        "Water Sports",
        "Heritage Walk",
        "Cultural Tour",
        "Nature Trail",
        "Cycling Route",
        "Boat Ride / Ferry",
        "Traditional Sport / Performance",
    ],

    "local_spots": [
        "Fishing Village",
        "Local Hangout Area",
        "Cultural Neighbourhood",
        "Traditional Gathering Spot",
        "Community Space",
        "Artisan Quarter",
        "Working Harbour",
        "Village Commons",
    ],

    "restaurants": [
        "Seafood Restaurant",
        "Traditional Mangalorean Cuisine",
        "Vegetarian Restaurant",
        "Café",
        "Street Food Hub",
        "Bakery",
        "Heritage Café",
        "Dhaba / Tiffin Room",
        "Udupi Restaurant",
        "Fine Dining",
        "Chinese / Continental",
    ],

    "food_dishes": [
        "Seafood Dish",
        "Tulu Cuisine",
        "Konkani Cuisine",
        "Dessert / Sweet",
        "Local Breakfast Item",
        "Coastal Curry",
        "Rice Preparation",
        "Snack / Deep-Fried",
        "Pickle / Chutney",
        "Beverage",
    ],

    "stay_options": [
        "Hotel",
        "Budget Lodge",
        "Resort",
        "Homestay",
        "Guest House",
        "Hostel",
        "Heritage Stay",
        "Beach Cottage",
        "Dharamshala",
        "Serviced Apartment",
    ],

    "beaches_coastal": [
        "Main Beach",
        "Quiet Beach",
        "Sunset Beach",
        "Surfing Beach",
        "Coastal Cliff",
        "Rocky Shore",
        "Backwater Meeting Point",
        "Tidal Flat",
    ],

    "nature_eco": [
        "Mangrove Forest",
        "Lake",
        "Park",
        "Botanical Garden",
        "Forest Reserve",
        "River Estuary",
        "Wetland",
        "Hilltop Nature Area",
        "Waterfall",
    ],

    "wildlife_species": [
        "Bird",
        "Mammal",
        "Reptile",
        "Amphibian",
        "Insect",
        "Butterfly",
        "Migratory Species",
    ],

    "marine_species": [
        "Fish Species",
        "Crustacean",
        "Coral Species",
        "Sea Turtle",
        "Marine Mammal",
        "Mollusc",
        "Seabird",
    ],

    "transport_nodes": [
        "Railway Station",
        "Bus Terminal",
        "Ferry Point",
        "Airport",
        "Seaport / Harbour",
        "Bus Stop",
        "Auto / Taxi Stand",
        "EV Charging Station",
    ],

    "emergency_services": [
        "Hospital",
        "Police Station",
        "Fire Station",
        "Coast Guard Station",
        "Disaster Shelter",
        "Pharmacy / Medical Store",
        "Blood Bank",
        "Ambulance Base",
    ],

    "religious_spiritual": [
        "Hindu Temple",
        "Church",
        "Mosque",
        "Dargah",
        "Ashram / Mutt",
        "Jain Temple",
        "Buddhist Monastery",
        "Wayside Shrine",
        "Pilgrimage Site",
        "Bathing Ghat",
    ],

    "markets_commerce": [
        "Fish Market",
        "Vegetable Market",
        "Street Market",
        "Night Market",
        "Local Bazaar",
        "Wholesale Market",
        "Flower Market",
        "Spice Market",
    ],

    "shopping_crafts": [
        "Handicraft Store",
        "Cashew Shop",
        "Spice Shop",
        "Textile / Saree Store",
        "Souvenir Store",
        "Jewellery Store",
        "Book Store",
        "Antique Shop",
        "Coir / Coconut Products",
        "Musical Instrument Shop",
    ],

    "museums_culture": [
        "Museum",
        "Heritage Village",
        "Art Gallery",
        "Cultural Centre",
        "Archaeological Site",
        "Open-Air Museum",
        "Tribal Heritage Display",
        "Maritime Museum",
    ],

    "education_institutions": [
        "University",
        "College",
        "Research Institute",
        "Library",
        "Educational Campus",
        "School (Notable)",
        "Training Centre",
        "Science Centre",
    ],

    "adventure_outdoor": [
        "Trekking Trail",
        "Kayaking Spot",
        "Cycling Route",
        "Camping Location",
        "Rock Climbing Area",
        "Rappelling Site",
        "Paragliding Launch",
        "Surfing Spot",
        "Waterfall Trek",
    ],

    "photography_spots": [
        "Sunrise Viewpoint",
        "Sunset Viewpoint",
        "Lighthouse View",
        "Coastal Cliff Photo Spot",
        "City Skyline Spot",
        "Wildlife Photography Hide",
        "River / Estuary View",
        "Heritage Architecture Shot",
    ],

    "nightlife_social": [
        "Pub",
        "Lounge",
        "Night Café",
        "Music Venue",
        "Late-Night Food Spot",
        "Rooftop Bar",
        "Cultural Show Venue",
        "Social Club",
    ],

    "day_trips": [
        "Hill Station",
        "Waterfall",
        "Temple Town",
        "Wildlife Reserve",
        "Scenic Drive",
        "Coastal Town",
        "Heritage Town",
        "Beach Town",
        "Trekking Base",
    ],

    "festivals_events": [
        "Temple Festival",
        "Church Feast",
        "Cultural Festival",
        "Food Festival",
        "Traditional Performance",
        "Boat Race",
        "Kambala / Folk Sport Event",
        "Music Festival",
        "Harvest Festival",
    ],

    "historical_events": [
        "Battle / Military Event",
        "City Milestone",
        "Colonial Event",
        "Cultural Movement",
        "Maritime History",
        "Religious Foundation Event",
        "Freedom Movement Event",
        "Trade / Port History",
    ],

    "notable_persons": [
        "Freedom Fighter",
        "Artist",
        "Writer / Poet",
        "Religious Leader",
        "Scientist / Scholar",
        "Musician",
        "Filmmaker / Actor",
        "Sportsperson",
        "Politician / Administrator",
    ],

    "media_photos": [
        "Landmark Photo",
        "Cultural Event Photo",
        "Wildlife Image",
        "Historical Photo",
        "City Landscape",
        "Food Photography",
        "Festival Photography",
        "Aerial / Drone View",
    ],

    "trending_articles": [
        "Travel Blog",
        "News Feature",
        "Cultural Story",
        "Tourism Trend",
        "Local Discovery",
        "Wikipedia Article",
        "RSS News",
        "Social Media Trending",
    ],
}


# ============================================================
# HELPERS
# ============================================================

ALL_DOMAINS: List[str] = list(TAXONOMY.keys())

def all_subcategories() -> List[str]:
    return [sc for scs in TAXONOMY.values() for sc in scs]

def domain_for_subcategory(subcategory: str) -> str:
    """Reverse lookup — find domain for a given subcategory."""
    sc_lower = subcategory.lower()
    for domain, subcats in TAXONOMY.items():
        if any(sc.lower() == sc_lower for sc in subcats):
            return domain
    return "places_landmarks"  # default


# ============================================================
# OSM TAG → DOMAIN/SUBCATEGORY MAPPING
# Used by the deep normalizer to classify OSM elements
# ============================================================

OSM_TAG_MAP: List[Dict] = [
    # beaches
    {"match": {"natural": "beach"},                    "domain": "beaches_coastal",   "subcategory": "Main Beach"},
    {"match": {"leisure": "beach"},                    "domain": "beaches_coastal",   "subcategory": "Main Beach"},
    {"match": {"tourism": "beach"},                    "domain": "beaches_coastal",   "subcategory": "Main Beach"},
    # viewpoints
    {"match": {"tourism": "viewpoint"},                "domain": "explore_sites",     "subcategory": "Scenic Viewpoint"},
    {"match": {"natural": "cliff"},                    "domain": "explore_sites",     "subcategory": "Coastal Cliff"},
    # places of worship
    {"match": {"amenity": "place_of_worship", "religion": "hindu"},   "domain": "religious_spiritual", "subcategory": "Hindu Temple"},
    {"match": {"amenity": "place_of_worship", "religion": "christian"},"domain": "religious_spiritual","subcategory": "Church"},
    {"match": {"amenity": "place_of_worship", "religion": "muslim"},  "domain": "religious_spiritual", "subcategory": "Mosque"},
    {"match": {"amenity": "place_of_worship", "religion": "jain"},    "domain": "religious_spiritual", "subcategory": "Jain Temple"},
    {"match": {"building": "temple"},                  "domain": "religious_spiritual","subcategory": "Hindu Temple"},
    {"match": {"building": "church"},                  "domain": "religious_spiritual","subcategory": "Church"},
    {"match": {"building": "mosque"},                  "domain": "religious_spiritual","subcategory": "Mosque"},
    # historic
    {"match": {"historic": "fort"},                    "domain": "places_landmarks",  "subcategory": "Fort / Watchtower"},
    {"match": {"historic": "monument"},                "domain": "places_landmarks",  "subcategory": "Historical Monument"},
    {"match": {"historic": "memorial"},                "domain": "places_landmarks",  "subcategory": "Historical Monument"},
    {"match": {"historic": "ruins"},                   "domain": "places_landmarks",  "subcategory": "Historical Monument"},
    {"match": {"historic": "archaeological_site"},     "domain": "museums_culture",   "subcategory": "Archaeological Site"},
    {"match": {"man_made": "lighthouse"},              "domain": "places_landmarks",  "subcategory": "Lighthouse"},
    # museums
    {"match": {"tourism": "museum"},                   "domain": "museums_culture",   "subcategory": "Museum"},
    {"match": {"tourism": "gallery"},                  "domain": "museums_culture",   "subcategory": "Art Gallery"},
    {"match": {"amenity": "arts_centre"},              "domain": "museums_culture",   "subcategory": "Cultural Centre"},
    # food
    {"match": {"amenity": "restaurant"},               "domain": "restaurants",       "subcategory": "Traditional Mangalorean Cuisine"},
    {"match": {"amenity": "cafe"},                     "domain": "restaurants",       "subcategory": "Café"},
    {"match": {"amenity": "fast_food"},                "domain": "restaurants",       "subcategory": "Street Food Hub"},
    {"match": {"amenity": "ice_cream"},                "domain": "restaurants",       "subcategory": "Dessert / Sweet"},
    {"match": {"amenity": "bakery"},                   "domain": "restaurants",       "subcategory": "Bakery"},
    {"match": {"shop": "bakery"},                      "domain": "restaurants",       "subcategory": "Bakery"},
    {"match": {"amenity": "dhaba"},                    "domain": "restaurants",       "subcategory": "Dhaba / Tiffin Room"},
    {"match": {"amenity": "bar"},                      "domain": "nightlife_social",  "subcategory": "Pub"},
    {"match": {"amenity": "pub"},                      "domain": "nightlife_social",  "subcategory": "Pub"},
    {"match": {"amenity": "nightclub"},                "domain": "nightlife_social",  "subcategory": "Music Venue"},
    # stay
    {"match": {"tourism": "hotel"},                    "domain": "stay_options",      "subcategory": "Hotel"},
    {"match": {"tourism": "hostel"},                   "domain": "stay_options",      "subcategory": "Hostel"},
    {"match": {"tourism": "guest_house"},              "domain": "stay_options",      "subcategory": "Guest House"},
    {"match": {"tourism": "motel"},                    "domain": "stay_options",      "subcategory": "Budget Lodge"},
    {"match": {"tourism": "resort"},                   "domain": "stay_options",      "subcategory": "Resort"},
    {"match": {"tourism": "homestay"},                 "domain": "stay_options",      "subcategory": "Homestay"},
    {"match": {"tourism": "camp_site"},                "domain": "stay_options",      "subcategory": "Beach Cottage"},
    # nature
    {"match": {"natural": "wetland"},                  "domain": "nature_eco",        "subcategory": "Wetland"},
    {"match": {"natural": "water"},                    "domain": "nature_eco",        "subcategory": "Lake"},
    {"match": {"waterway": "waterfall"},               "domain": "nature_eco",        "subcategory": "Waterfall"},
    {"match": {"natural": "bay"},                      "domain": "beaches_coastal",   "subcategory": "Rocky Shore"},
    {"match": {"leisure": "park"},                     "domain": "nature_eco",        "subcategory": "Park"},
    {"match": {"leisure": "garden"},                   "domain": "nature_eco",        "subcategory": "Botanical Garden"},
    {"match": {"leisure": "nature_reserve"},           "domain": "nature_eco",        "subcategory": "Forest Reserve"},
    {"match": {"landuse": "forest"},                   "domain": "nature_eco",        "subcategory": "Forest Reserve"},
    # transport
    {"match": {"amenity": "bus_station"},              "domain": "transport_nodes",   "subcategory": "Bus Terminal"},
    {"match": {"railway": "station"},                  "domain": "transport_nodes",   "subcategory": "Railway Station"},
    {"match": {"amenity": "ferry_terminal"},           "domain": "transport_nodes",   "subcategory": "Ferry Point"},
    {"match": {"aeroway": "aerodrome"},                "domain": "transport_nodes",   "subcategory": "Airport"},
    {"match": {"highway": "bus_stop"},                 "domain": "transport_nodes",   "subcategory": "Bus Stop"},
    {"match": {"man_made": "pier"},                    "domain": "transport_nodes",   "subcategory": "Ferry Point"},
    # emergency
    {"match": {"amenity": "hospital"},                 "domain": "emergency_services","subcategory": "Hospital"},
    {"match": {"amenity": "police"},                   "domain": "emergency_services","subcategory": "Police Station"},
    {"match": {"amenity": "fire_station"},             "domain": "emergency_services","subcategory": "Fire Station"},
    {"match": {"amenity": "pharmacy"},                 "domain": "emergency_services","subcategory": "Pharmacy / Medical Store"},
    # shopping
    {"match": {"shop": "craft"},                       "domain": "shopping_crafts",   "subcategory": "Handicraft Store"},
    {"match": {"shop": "spices"},                      "domain": "shopping_crafts",   "subcategory": "Spice Shop"},
    {"match": {"shop": "fabric"},                      "domain": "shopping_crafts",   "subcategory": "Textile / Saree Store"},
    {"match": {"shop": "clothes"},                     "domain": "shopping_crafts",   "subcategory": "Textile / Saree Store"},
    {"match": {"shop": "jewellery"},                   "domain": "shopping_crafts",   "subcategory": "Jewellery Store"},
    {"match": {"shop": "books"},                       "domain": "shopping_crafts",   "subcategory": "Book Store"},
    {"match": {"shop": "souvenir"},                    "domain": "shopping_crafts",   "subcategory": "Souvenir Store"},
    {"match": {"shop": "gift"},                        "domain": "shopping_crafts",   "subcategory": "Souvenir Store"},
    # markets
    {"match": {"amenity": "marketplace"},              "domain": "markets_commerce",  "subcategory": "Local Bazaar"},
    {"match": {"shop": "fish"},                        "domain": "markets_commerce",  "subcategory": "Fish Market"},
    {"match": {"shop": "seafood"},                     "domain": "markets_commerce",  "subcategory": "Fish Market"},
    {"match": {"shop": "greengrocer"},                 "domain": "markets_commerce",  "subcategory": "Vegetable Market"},
    # local spots
    {"match": {"amenity": "community_centre"},         "domain": "local_spots",       "subcategory": "Community Space"},
    {"match": {"amenity": "social_centre"},            "domain": "local_spots",       "subcategory": "Community Space"},
    {"match": {"amenity": "village_hall"},             "domain": "local_spots",       "subcategory": "Traditional Gathering Spot"},
    # education
    {"match": {"amenity": "university"},               "domain": "education_institutions","subcategory": "University"},
    {"match": {"amenity": "college"},                  "domain": "education_institutions","subcategory": "College"},
    {"match": {"amenity": "library"},                  "domain": "education_institutions","subcategory": "Library"},
    {"match": {"amenity": "research_institute"},       "domain": "education_institutions","subcategory": "Research Institute"},
    # adventure / outdoor
    {"match": {"route": "hiking"},                     "domain": "adventure_outdoor", "subcategory": "Trekking Trail"},
    {"match": {"route": "cycling"},                    "domain": "adventure_outdoor", "subcategory": "Cycling Route"},
    {"match": {"sport": "surfing"},                    "domain": "adventure_outdoor", "subcategory": "Surfing Spot"},
    {"match": {"sport": "kayaking"},                   "domain": "adventure_outdoor", "subcategory": "Kayaking Spot"},
    {"match": {"leisure": "fishing"},                  "domain": "local_spots",       "subcategory": "Working Harbour"},
    # activities
    {"match": {"amenity": "boat_rental"},              "domain": "activities",        "subcategory": "Boating"},
    {"match": {"amenity": "theatre"},                  "domain": "activities",        "subcategory": "Cultural Tour"},
    {"match": {"amenity": "cinema"},                   "domain": "nightlife_social",  "subcategory": "Cultural Show Venue"},
]


def classify_osm_element(tags: dict) -> tuple:
    """
    Given OSM tags dict, return (domain, subcategory).
    Tries each rule in OSM_TAG_MAP in order; returns best match.
    """
    for rule in OSM_TAG_MAP:
        match = rule["match"]
        if all(tags.get(k) == v or (v == "*" and k in tags)
               for k, v in match.items()):
            return rule["domain"], rule["subcategory"]

    # Fallback heuristics
    if tags.get("tourism"):
        return "explore_sites", "City Landmark"
    if tags.get("historic"):
        return "places_landmarks", "Historical Monument"
    if tags.get("natural"):
        return "nature_eco", "Park"
    if tags.get("leisure"):
        return "nature_eco", "Park"
    if tags.get("shop"):
        return "shopping_crafts", "Souvenir Store"
    if tags.get("amenity"):
        return "local_spots", "Community Space"

    return "places_landmarks", "City Landmark"