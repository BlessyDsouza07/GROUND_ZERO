"""
city_profiles/mangalore_profile.py

Complete city profile for Mangalore (Mangaluru), Karnataka, India.

This is the reference implementation — use this as a template
when creating profiles for other cities.
"""

from city_profiles.city_profile import CityProfile, LandmarkSeed, RSSFeedConfig


MANGALORE = CityProfile(

    # ── IDENTITY ──────────────────────────────────────────────
    city_id        = "mangalore",
    display_name   = "Mangalore",
    full_name      = "Mangalore, Karnataka, India",
    state          = "Karnataka",
    country        = "India",
    country_code   = "IN",
    timezone       = "Asia/Kolkata",

    # ── GEOGRAPHY ─────────────────────────────────────────────
    bbox           = (12.78, 74.75, 13.05, 75.05),  # south, west, north, east
    center_lat     = 12.8714,
    center_lon     = 74.8431,
    osm_relation_id= 1952828,          # openstreetmap.org/relation/1952828
    wikidata_qid   = "Q42941",         # wikidata.org/wiki/Q42941
    osm_admin_levels = ["6", "7", "8"],

    # ── NAME VARIANTS ─────────────────────────────────────────
    name_variants        = ["Mangaluru", "Mangalore", "ಮಂಗಳೂರು"],
    local_language_name  = "ಮಂಗಳೂರು",
    local_language_code  = "kn",

    # ── CUISINE & FOOD ────────────────────────────────────────
    signature_foods = [
        "Neer Dosa",
        "Kori Rotti (Chicken on Rice Wafers)",
        "Goli Baje (Mangalore Bajji)",
        "Kane Fish Fry (Ladyfish)",
        "Chicken Ghee Roast",
        "Prawn Gassi (Coconut Curry)",
        "Kotte Kadubu (Jackfruit Leaf Dumplings)",
        "Mangalore Buns (Sweet Banana Puri)",
        "Patrade (Colocasia Leaf Rolls)",
        "Dali Thoy (Lentil Curry, Coastal Style)",
        "Bangude Pulusu (Mackerel Curry)",
        "Crab Masala (Tulu Nadu Style)",
        "Halasina Hannina Gojju (Jackfruit Curry)",
        "Moode (Rice Dumplings in Leaf)",
        "Padengi Gassi (Sprouted Chickpea Curry)",
        "Sannas (Fermented Rice Cakes)",
        "Undi (Steamed Rice Balls)",
        "Surmayi Fry (Kingfish Fry)",
        "Ideal Ice Cream (Cashew & Coconut flavours)",
    ],

    food_culture_notes = (
        "Mangalore cuisine is dominated by coconut, fish, and the Tulu Nadu tradition. "
        "The city sits at the confluence of the Gurupur and Netravathi rivers with the Arabian Sea, "
        "making fresh seafood — kane, bangude, prawn, crab — the backbone of every meal. "
        "Vegetarian Tulu Nadu cooking uses jackfruit, colocasia, raw banana and is equally rich. "
        "The Catholic community (descendants of Portuguese-era converts) adds its own layer: "
        "sorpotel, vindaloo, and the iconic Mangalore bread bun. Udupi-style pure vegetarian "
        "restaurants coexist with Muslim-run biryani houses and Jain eateries. "
        "Breakfast is the sacred meal: neer dosa (water rice crepe), idli, and goli baje with coconut chutney. "
        "Ideal Ice Cream (est. 1975) is a Mangalore institution — try cashew, tender coconut, sitaphal."
    ),

    local_ingredients = [
        "Coconut (used in almost every dish)",
        "Byadagi Red Chilli (mild, fragrant — core of ghee roast)",
        "Kodampuli (Gamboge / Goraka — souring agent for fish curries)",
        "Fresh Seafood (kane, bangude, prawn, crab, surmayi)",
        "Jackfruit (raw and ripe, used in curries and sweets)",
        "Colocasia / Taro (patrade, patrode)",
        "Neer (water rice) — for neer dosa",
        "Coconut Vinegar (Catholic cuisine)",
        "Kori (local free-range chicken)",
        "Cashew Nuts (coastal Karnataka grown)",
    ],

    # ── CURATED LANDMARKS ─────────────────────────────────────
    landmarks = [
        # BEACHES
        LandmarkSeed("Panambur Beach",     12.9540, 74.8020, "Beach",          "places",  "Main beach, water sports, Dasara fair grounds", "Panambur_Beach", "sunrise or late afternoon"),
        LandmarkSeed("Tannirbhavi Beach",  12.9400, 74.7840, "Beach",          "places",  "Accessible by ferry, less crowded, peaceful", "", "morning or sunset"),
        LandmarkSeed("Ullal Beach",        12.8000, 74.8380, "Beach",          "places",  "Hazara mosque nearby, serene, good sunset", "Ullal", "sunset"),
        LandmarkSeed("Someshwara Beach",   12.8680, 74.8350, "Beach",          "places",  "Rocky, temple, good sunset point", "", "sunset"),
        LandmarkSeed("Surathkal Beach",    13.0130, 74.7890, "Beach",          "places",  "Near NIT campus, old lighthouse, fewer crowds", "", "morning"),
        LandmarkSeed("Kaup Beach",         13.1700, 74.7400, "Beach",          "places",  "1901 lighthouse you can climb, bay views, 30km north", "Kaup", "afternoon"),
        LandmarkSeed("Sasihithlu Beach",   13.0700, 74.7650, "Beach",          "places",  "Backwater meets sea, very peaceful, mangroves", "", "morning"),

        # TEMPLES
        LandmarkSeed("Kadri Manjunath Temple",       12.8979, 74.8505, "Hindu Temple",   "explore", "1000+ year old, bronze Lokeshwara statue, must visit", "Kadri_Manjunath_Temple", "early morning"),
        LandmarkSeed("Mangaladevi Temple",           12.8570, 74.8470, "Hindu Temple",   "explore", "City's namesake, ancient Shakti temple, Navaratri festivities", "Mangaladevi_Temple,_Mangalore", "morning"),
        LandmarkSeed("Kudroli Gokarnath Temple",     12.8800, 74.8400, "Hindu Temple",   "explore", "Grand architecture, Dasara celebrations, Vivekananda connection", "", "morning"),
        LandmarkSeed("Kateel Durgaparameshwari",     13.0240, 75.0310, "Hindu Temple",   "explore", "Island temple, 30km east, extremely popular, river setting", "Kateel", "morning"),
        LandmarkSeed("Dharmasthala Temple",          12.9560, 75.3850, "Hindu Temple",   "explore", "75km east, famous Shiva temple, free meals for all, pilgrimage", "Dharmasthala", "morning — full day trip"),
        LandmarkSeed("Polali Rajarajeshwari Temple", 12.7590, 75.0350, "Hindu Temple",   "explore", "30km east, powerful Shakti temple, forested setting", "", "morning"),

        # CHURCHES
        LandmarkSeed("St Aloysius Chapel",     12.8714, 74.8381, "Church",         "explore", "1880 Italian-style frescoes covering every inch — stunning", "St._Aloysius_Chapel,_Mangalore", "morning"),
        LandmarkSeed("Milagres Church",        12.8680, 74.8370, "Church",         "explore", "1680, oldest church in Mangalore, Our Lady of Miracles", "", "morning"),
        LandmarkSeed("Rosario Cathedral",      12.8650, 74.8430, "Church",         "explore", "Diocese headquarters, Gothic architecture, active parish", "", "any time"),
        LandmarkSeed("Bejai Church",           12.8920, 74.8440, "Healing Shrine", "explore", "Our Lady of Health — healing shrine, many devotees, peaceful", "", "morning"),

        # MOSQUES / DARGAHS
        LandmarkSeed("Hazrat Shah Bundar Dargah", 12.8000, 74.8380, "Dargah / Shrine", "explore", "Ullal, coastal shrine, annual urs festival, important to local Muslims", "", "any time"),
        LandmarkSeed("Idgah Maidan Mosque",       12.8800, 74.8430, "Mosque",          "explore", "Hilltop mosque, panoramic city views, Eid prayers large gathering", "", "any time"),

        # HISTORIC
        LandmarkSeed("Sultan Battery",       12.8700, 74.8260, "Historic Fort",  "explore", "Tipu Sultan's 1784 riverside watchtower, small but atmospheric", "Sultan_Battery", "morning"),
        LandmarkSeed("Kaup Lighthouse",      13.1700, 74.7430, "Lighthouse",     "explore", "1901, still functional, open to climb, wide sea views", "", "afternoon"),

        # NATURE
        LandmarkSeed("Pilikula Nisargadhama",  12.9380, 74.9960, "Nature Park",    "places",  "Zoo, boating, nature trails, heritage village — family spot", "Pilikula_Nisargadhama", "morning"),
        LandmarkSeed("Tannirbhavi Mangroves",  12.9300, 74.7800, "Mangroves",      "places",  "Mangrove forest, birdwatching, very peaceful, boat access", "", "early morning"),
        LandmarkSeed("Gurupur River Estuary",  12.9350, 74.7900, "River Estuary",  "places",  "Boat rides, sunset views, fishing boat activity, serene", "", "sunset"),
        LandmarkSeed("Lighthouse Hill Garden", 12.8760, 74.8440, "Viewpoint",      "places",  "360° city view, evening garden, couples and families", "", "sunset"),

        # EXPERIENCES
        LandmarkSeed("Yakshagana Performance",    12.8709, 74.8428, "Cultural Performance", "activities", "Traditional Tulu dance-drama — check Ravindra Kala Bhavana schedule", "Yakshagana", "evening"),
        LandmarkSeed("Kambala Buffalo Race",      12.8000, 74.8000, "Traditional Sport",    "activities", "Nov-Mar season, paddy field buffalo races, electrifying", "Kambala_(Karnataka)", "early morning Nov-Mar"),
        LandmarkSeed("Hoige Bazaar Fish Market",  12.8710, 74.8340, "Market Experience",    "food",       "5am-8am, largest fish market, full sensory Mangalore — essential visit", "", "5am-8am"),
        LandmarkSeed("Gurupur River Ferry",       12.9350, 74.7850, "Boat Ride",            "activities", "10-min ferry to Tannirbhavi beach — local experience, not tourist", "", "morning"),
        LandmarkSeed("Car Street Heritage Walk",  12.8670, 74.8370, "Heritage Walk",        "explore",    "Old Brahmin agrahara quarter, 19th century houses, quiet lanes", "", "early morning"),

        # FOOD SPOTS
        LandmarkSeed("Ideal Ice Cream",    12.8720, 74.8410, "Ice Cream Parlour",       "food", "Mangalore institution since 1975 — cashew, coconut, sitaphal", "Ideal_Ice_Cream", "any time"),
        LandmarkSeed("Janatha Hotel",      12.8700, 74.8420, "Traditional Breakfast",   "food", "Iconic neer dosa, idli, Mangalorean breakfast — often crowded", "", "7am-10am"),
        LandmarkSeed("Hotel Surya",        12.8690, 74.8390, "Coastal Restaurant",      "food", "Famous chicken ghee roast and fish curries — must try", "", "lunch or dinner"),
        LandmarkSeed("Taj Mahal Cafe",     12.8720, 74.8400, "Heritage Cafe",           "food", "100+ year old cafe, colonial feel, Mangalorean breakfast", "", "morning"),
        LandmarkSeed("Hao Ming",           12.8750, 74.8440, "Chinese Restaurant",      "food", "Oldest Chinese restaurant in Mangalore, decades of history", "", "lunch or dinner"),

        # SHOPPING
        LandmarkSeed("Hampankatta Market",    12.8709, 74.8428, "Bazaar / Market",   "local", "City centre market — sarees, cloth, utensils, street food, everything", "", "morning or evening"),
        LandmarkSeed("Balmatta Bakeries",     12.8730, 74.8420, "Bakery Street",     "local", "Traditional Mangalorean bread, bun, khaari — buy fresh in morning", "", "early morning"),
        LandmarkSeed("Deralakatte Spice Market", 12.8450, 74.9300, "Spice Market",   "local", "Wholesale cardamom, pepper, coastal spices — aromatic, authentic", "", "morning"),

        # VIEWPOINTS
        LandmarkSeed("Idgah Hills",        12.8800, 74.8430, "Scenic Viewpoint", "places", "Hilltop, panoramic city + sea view, peaceful at sunrise", "", "sunrise or sunset"),
    ],

    # ── WIKIPEDIA TRACKING ────────────────────────────────────
    wikipedia_articles = [
        "Mangalore",
        "Panambur_Beach",
        "Kadri_Manjunath_Temple",
        "Pilikula_Nisargadhama",
        "Neer_dosa",
        "Kori_rotti",
        "Yakshagana",
        "Kambala",
        "Tulu_language",
        "Dakshina_Kannada",
        "Mangaladevi_Temple",
        "Tulu_Nadu",
        "Goli_baje",
        "Kaup",
        "Dharmasthala",
        "St._Aloysius_Chapel,_Mangalore",
    ],

    # ── RSS FEEDS ─────────────────────────────────────────────
    rss_feeds = [
        RSSFeedConfig(
            name     = "The Hindu Karnataka",
            url      = "https://www.thehindu.com/news/national/karnataka/feeder/default.rss",
            language = "en",
            relevance_keywords = ["mangalore", "mangaluru", "dakshina kannada", "tulu", "coastal karnataka"],
        ),
        RSSFeedConfig(
            name     = "Times of India Mangalore",
            url      = "https://timesofindia.indiatimes.com/city/mangalore/rssfeeds/1948093.cms",
            language = "en",
            relevance_keywords = ["mangalore", "mangaluru"],
        ),
        RSSFeedConfig(
            name     = "Udayavani",
            url      = "https://www.udayavani.com/feed",
            language = "kn",
            relevance_keywords = ["ಮಂಗಳೂರು", "ದಕ್ಷಿಣ ಕನ್ನಡ"],
        ),
        RSSFeedConfig(
            name     = "Karnataka Tourism",
            url      = "https://karnatakatourism.org/feed/",
            language = "en",
            relevance_keywords = ["mangalore", "mangaluru", "karnataka coast", "tulu"],
        ),
    ],

    # ── SEASONS ───────────────────────────────────────────────
    peak_season_months    = [10, 11, 12, 1, 2, 3],  # Oct-Mar
    monsoon_months        = [6, 7, 8, 9],            # Jun-Sep (heavy Southwest monsoon)
    best_visit_months     = [11, 12, 1, 2],          # Nov-Feb ideal

    # ── LOCAL CONTEXT ─────────────────────────────────────────
    local_festivals = [
        {"name": "Mangalore Dasara",        "month": 10, "notes": "City-wide celebration, Kudroli temple centrepiece"},
        {"name": "Kambala Season",          "month": 11, "notes": "Buffalo races Nov-Mar across coastal Karnataka"},
        {"name": "Yaksha Utsava",           "month": 11, "notes": "Yakshagana festival, check Ravindra Kala Bhavana"},
        {"name": "Christmas & New Year",    "month": 12, "notes": "Large Catholic community, Balmatta area festivities"},
        {"name": "Tulu New Year (Bisu)",    "month": 4,  "notes": "Tulu Nadu new year, family gathering festival"},
        {"name": "Brahmotsava",             "month": 3,  "notes": "Annual temple chariot festival at major temples"},
        {"name": "Navaratri",               "month": 10, "notes": "Mangaladevi temple celebrations, 9 nights"},
    ],

    day_trip_cities = [
        {"name": "Udupi",        "distance_km": 60,  "notes": "Krishna temple, Manipal university, coastal town"},
        {"name": "Dharmasthala", "distance_km": 75,  "notes": "Major pilgrimage, free meals, Shiva temple"},
        {"name": "Kateel",       "distance_km": 30,  "notes": "Island temple, riverside setting"},
        {"name": "Moodabidri",   "distance_km": 35,  "notes": "1000-pillar Jain temple, Jain capital of Karnataka"},
        {"name": "Coorg",        "distance_km": 130, "notes": "Coffee estates, misty hills, Kodava culture"},
        {"name": "Malpe Beach",  "distance_km": 90,  "notes": "Ferry to St. Mary's Island basalt formations"},
        {"name": "Marawanthe",   "distance_km": 140, "notes": "NH17 road between sea and river — most scenic coastal drive"},
        {"name": "Murudeshwar",  "distance_km": 160, "notes": "160m Shiva statue, beach, temple on cliff"},
        {"name": "Kukke Subramanya","distance_km": 105,"notes": "Snake temple, dense forest, major pilgrimage"},
    ],

    special_experiences = [
        "Watch a Yakshagana performance (traditional Tulu dance-drama)",
        "Witness Kambala buffalo races (November to March)",
        "5am fish market walk at Hoige Bazaar",
        "Ferry from Panambur to Tannirbhavi beach",
        "Sunset at Gurupur river estuary, watching fishing boats return",
        "Car Street heritage walk through old Brahmin agrahara",
        "Full coastal Karnataka meal — neer dosa, fish curry, sol kadhi",
        "Cashew feni tasting (Goan-influenced local spirit)",
        "Watch the Portuguese-era mass at Milagres Church on Sunday",
        "Early morning puja at Kadri Manjunath temple",
    ],

    # ── SEARCH KEYWORDS ───────────────────────────────────────
    search_keywords = [
        "mangalore", "mangaluru", "tulu", "dakshina kannada",
        "coastal karnataka", "tulu nadu", "konkani mangalore",
        "bunt mangalore", "beary mangalore",
    ],
)