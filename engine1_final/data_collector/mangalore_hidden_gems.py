"""
data_collector/mangalore_hidden_gems.py

MANGALORE HIDDEN GEMS — Curated Local Intelligence Layer
=========================================================
Source type: "local_knowledge"

WHY THIS FILE EXISTS:
  OSM maps what contributors survey. Wikipedia covers what is famous.
  Neither captures what local people actually know — the pre-dawn fish
  market at Hoige Bazaar, the 100-year-old toddy shop near Ullal ferry,
  the Bhuta Kola shrine hidden in Kavoor forest, the one stall that
  makes authentic Kori Rotti with a 40-year-old recipe.

  Ground Zero's "must experience" city index (SRS §1.3, §1.4) requires
  a curated layer of culturally irreplaceable, low-footprint, locally
  significant places that no external API surfaces.

LEGAL / ETHICAL:
  - All entries are publicly accessible places
  - No proprietary data, no scraping, no review copying
  - Coordinates from public domain maps
  - Curated for uniqueness, not popularity — zero commercial inclusion
  - Bias check: unexplored_signal=True means <500 tourist visits/month est.

FIELDS USED BY PIPELINE:
  name, category, subcategory, domain, latitude, longitude
  description     — factual local significance statement
  opening_hours   — if known
  cuisine         — for food domain
  wikipedia       — if article exists
  tulu_cultural_tag — Tulu Nadu cultural classification
  feast_season    — if best during a specific feast/season
  best_time       — time of day / season recommendation
  hidden_gem_tier — 1=hyper-local only, 2=locally known, 3=regionally known
  unexplored_signal — True if tourist footfall is very low
"""

from typing import List, Dict
from utils.logger import get_logger

logger = get_logger("MangaloreHiddenGems")


HIDDEN_GEMS: List[Dict] = [

    # ════════════════════════════════════════════════════════
    # UNEXPLORED BEACHES
    # ════════════════════════════════════════════════════════
    {
        "name": "Sasihithlu Beach",
        "category": "beach", "subcategory": "Estuary Beach",
        "domain": "places",
        "latitude": 13.0120, "longitude": 74.8002,
        "description": "Estuary beach where the Shambhavi river meets the Arabian Sea. No tourist infrastructure. Fishermen dry their catch on the sand at dawn. The sandbar shifts seasonally — the geography changes every year. Reached by a 1km walk through a fishing village.",
        "opening_hours": "24/7 (open beach)",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "5:30–9:00 AM or sunset",
        "feast_season": None,
        "tulu_cultural_tag": "fishing_community_beach",
    },
    {
        "name": "Someshwara Beach",
        "category": "beach", "subcategory": "Temple Beach",
        "domain": "places",
        "latitude": 12.9741, "longitude": 74.7876,
        "description": "Rock-strewn beach with a working lighthouse and the ancient Someshwara Shiva temple directly on the waterfront. The only Mangalore beach where you can watch the lighthouse lantern rotate at night while hearing temple bells. Rocky tide pools accessible at low tide.",
        "opening_hours": "24/7",
        "unexplored_signal": True,
        "hidden_gem_tier": 2,
        "best_time": "Evening 17:00–19:00 (temple aarti + sunset)",
        "feast_season": "Maha Shivaratri (Feb/Mar) — midnight pilgrimage",
        "tulu_cultural_tag": "temple_beach",
    },
    {
        "name": "Batpady Beach",
        "category": "beach", "subcategory": "Undeveloped Coastal Strip",
        "domain": "places",
        "latitude": 12.8810, "longitude": 74.7790,
        "description": "Completely undeveloped beach south of Ullal, accessible only via a fishing village footpath. No vendors, no crowds. Fishermen launch outrigger canoes before 5 AM. Night sky untouched by city light — ideal for stargazing. Part of the Dakshina Kannada coastal ecosystem.",
        "opening_hours": "24/7",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Pre-dawn 4:30–6:00 AM (canoe launches); midnight (stars)",
        "feast_season": None,
        "tulu_cultural_tag": "fishing_village_coast",
    },
    {
        "name": "Chitrapur Coast (Shirva)",
        "category": "beach", "subcategory": "Pilgrimage Coastline",
        "domain": "places",
        "latitude": 13.0010, "longitude": 74.7950,
        "description": "Sacred GSB (Goud Saraswat Brahmin) coastline near Shirva village, 2km from Chitrapur Math. During Guru Purnima the monastic procession walks to this shore. Almost never visited by outsiders. A living pilgrimage ecosystem with no tourist signage.",
        "opening_hours": "24/7",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Guru Purnima full moon (July)",
        "feast_season": "Guru Purnima — July full moon",
        "tulu_cultural_tag": "gsb_pilgrimage_coast",
    },
    {
        "name": "Kulur Ferry Crossing",
        "category": "waterway", "subcategory": "River Ferry Crossing",
        "domain": "places",
        "latitude": 12.9100, "longitude": 74.8150,
        "description": "Small hand-operated ferry crossing the Gurupura river at Kulur. Used daily by fishermen, schoolchildren, and villagers on motorcycles. The 10-minute crossing gives views of Mangalore port, fishing boats, and the river mangroves. One of the last working traditional river ferries in coastal Karnataka.",
        "opening_hours": "06:00–22:00 daily",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Early morning (fishermen's boats returning 6–8 AM)",
        "feast_season": None,
        "tulu_cultural_tag": "river_ferry_culture",
    },

    # ════════════════════════════════════════════════════════
    # HIDDEN NATURE
    # ════════════════════════════════════════════════════════
    {
        "name": "Kavoor Wetlands (Mangrove Walk)",
        "category": "natural", "subcategory": "Mangrove Wetland",
        "domain": "places",
        "latitude": 12.9080, "longitude": 74.8540,
        "description": "40-hectare mangrove wetland on Mangalore's northeastern edge. Home to mud-skippers, fiddler crabs, and three mangrove species. A raised bund path cuts through the wetland. No entry fee, no signage. Used daily by local morning walkers who have no idea it is a functioning tidal wetland ecosystem.",
        "opening_hours": "Always open (public land)",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "6:00–8:00 AM birdwatching; 4:00–5:30 PM low-tide wildlife",
        "feast_season": None,
        "tulu_cultural_tag": "coastal_wetland_ecosystem",
    },
    {
        "name": "Gurupura River Estuary (Tannirbhavi side)",
        "category": "natural", "subcategory": "River Estuary / Backwater",
        "domain": "places",
        "latitude": 12.9240, "longitude": 74.7840,
        "description": "Where the Gurupura river meets the Arabian Sea. At low tide, sandbanks emerge and migratory birds — herons, egrets, kingfishers — crowd the shallows. The estuary ferry crossing is Mangalore's most atmospheric 10 minutes: fishing boats, the old port, open sea, and river dolphins occasionally visible.",
        "opening_hours": "Ferry: 6:00 AM–10:00 PM",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Low tide mornings 6:00–9:00 AM; monsoon for dramatic conditions",
        "feast_season": None,
        "tulu_cultural_tag": "fishing_estuary_ferry",
    },
    {
        "name": "Surathkal Lighthouse Rocky Shore",
        "category": "man_made", "subcategory": "Working Lighthouse",
        "domain": "explore",
        "latitude": 13.0155, "longitude": 74.7935,
        "description": "The 1904 Surathkal lighthouse is among the tallest on India's west coast and opens to the public on Fridays and Sundays. The rocky foreshore has natural tide pools with starfish, sea urchins, and anemones. NITK campus borders this shore. Almost no tourist infrastructure despite being visually dramatic.",
        "opening_hours": "Lighthouse: Fri + Sun 16:00–17:30; Shore: always",
        "unexplored_signal": True,
        "hidden_gem_tier": 2,
        "best_time": "Low tide Friday/Sunday afternoon",
        "feast_season": None,
        "tulu_cultural_tag": "colonial_lighthouse_coast",
        "wikipedia": "en:Surathkal Lighthouse",
    },
    {
        "name": "Pilikula Lake Rowing Point",
        "category": "leisure", "subcategory": "Freshwater Lake",
        "domain": "places",
        "latitude": 12.9214, "longitude": 74.8891,
        "description": "The Pilikula Nisarga Dhama lake is used for rowing and paddleboating. The surrounding forest is part of the Pilikula eco-cultural complex. Mornings are quiet — egrets fish along the banks and the Sahyadri foothills are visible. Most visitors stay at the zoo section and miss this lakeside.",
        "opening_hours": "09:00–17:30 (closed Mon)",
        "unexplored_signal": False,
        "hidden_gem_tier": 2,
        "best_time": "Weekday mornings (minimal crowd)",
        "feast_season": None,
        "tulu_cultural_tag": "pilikula_eco_complex",
        "wikipedia": "en:Pilikula Nisarga Dhama",
    },

    # ════════════════════════════════════════════════════════
    # HYPER-LOCAL FOOD
    # ════════════════════════════════════════════════════════
    {
        "name": "Hoige Bazaar Fish Market",
        "category": "marketplace", "subcategory": "Fish Market",
        "domain": "food",
        "latitude": 12.8679, "longitude": 74.8390,
        "description": "Mangalore's oldest fish market, operating since pre-independence. Beary Muslim women vendors (the traditional fish traders of coastal Karnataka) sell fresh catch from 5 AM. A mix of Beary, Tulu, and Konkani is spoken here. Invisible to tourists but fundamental to Mangalore's food identity.",
        "opening_hours": "05:00–10:00 daily",
        "cuisine": "fish; seafood; coastal",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "5:00–7:30 AM (peak fresh catch)",
        "feast_season": None,
        "tulu_cultural_tag": "beary_fish_trading_community",
    },
    {
        "name": "Ideal Ice Cream — Hampankatta Original",
        "category": "cafe", "subcategory": "Mangalore Ice Cream Institution",
        "domain": "food",
        "latitude": 12.8701, "longitude": 74.8450,
        "description": "Ideal Ice Cream was founded in Mangalore in 1975. The Hampankatta parlour is the original location. Flavours like Sitaphal (custard apple), Tender Coconut, and Jackfruit are regional originals found nowhere else in this form. An institution that defines Mangalorean dessert culture.",
        "opening_hours": "10:00–22:00",
        "cuisine": "ice_cream; sitaphal; tender_coconut; jackfruit",
        "unexplored_signal": False,
        "hidden_gem_tier": 3,
        "best_time": "Evenings (peak Mangalorean crowd experience)",
        "feast_season": None,
        "tulu_cultural_tag": "mangalore_food_icon",
        "wikipedia": "en:Ideal Ice Cream",
    },
    {
        "name": "Shetty Lunch Home (Balmatta)",
        "category": "restaurant", "subcategory": "Coastal Karnataka Restaurant",
        "domain": "food",
        "latitude": 12.8743, "longitude": 74.8472,
        "description": "A no-frills family restaurant serving traditional Mangalorean fish curry on banana leaf. Regulars order only by pointing — the menu is fixed and changes daily. Rice, fish curry, fried fish, and coconut chutney. No signboard visible from the road. Known exclusively by word of mouth among locals.",
        "opening_hours": "12:00–15:30 (lunch only, Mon–Sat)",
        "cuisine": "coastal; fish; kori_rotti; tulu",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "12:00–13:30 (arrive early — sells out)",
        "feast_season": None,
        "tulu_cultural_tag": "tulu_coastal_home_food",
    },
    {
        "name": "Goli Baje Corner (Old Bunder Road)",
        "category": "street_vendor", "subcategory": "Street Food Stall",
        "domain": "food",
        "latitude": 12.8690, "longitude": 74.8370,
        "description": "A 40-year-old family stall selling only Goli Baje — Mangalore's signature spongy rice-flour fritter — and coconut chutney. Open evenings only, closed Sundays. The recipe has been unchanged since 1984. Locals use it as the benchmark: if it doesn't taste like this, it is not authentic Goli Baje.",
        "opening_hours": "17:00–21:00 (Mon–Sat)",
        "cuisine": "goli_baje; tulu; street_food",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "17:00–19:00 (freshest batch)",
        "feast_season": None,
        "tulu_cultural_tag": "tulu_street_food_heritage",
    },
    {
        "name": "Machhi Restaurant (Ullal Road)",
        "category": "restaurant", "subcategory": "Seafood Restaurant",
        "domain": "food",
        "latitude": 12.8462, "longitude": 74.8231,
        "description": "Coastal seafood restaurant specialising in Mangalorean prawn curry, crab masala, and neer dosa. Sourced from Ullal harbour fishermen each morning. Outdoor seating on a covered terrace. No AC, no ambience — just fresh coastal food at local prices. Frequented by fishermen and port workers.",
        "opening_hours": "11:00–22:00 daily",
        "cuisine": "seafood; prawn; crab; neer_dosa; coastal",
        "unexplored_signal": True,
        "hidden_gem_tier": 2,
        "best_time": "Lunch 12:00–14:00 (freshest catch of the day)",
        "feast_season": None,
        "tulu_cultural_tag": "ullal_coastal_seafood",
    },

    # ════════════════════════════════════════════════════════
    # CULTURAL HERITAGE
    # ════════════════════════════════════════════════════════
    {
        "name": "Sultan Battery (Portuguese Fort Ruins)",
        "category": "historic", "subcategory": "Colonial Fort Ruins",
        "domain": "explore",
        "latitude": 12.8704, "longitude": 74.8226,
        "description": "16th-century Portuguese watchtower later fortified by Hyder Ali and Tipu Sultan to guard the Gurupura river mouth. Partially submerged at high tide. Surrounded by intact mangrove forest. One of the few standing pre-colonial military structures on the Karnataka coast. Almost no tourist signage.",
        "opening_hours": "Dawn to dusk (no entry fee)",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Low tide mornings Oct–Feb (structure most visible)",
        "feast_season": None,
        "tulu_cultural_tag": "colonial_military_heritage",
        "wikipedia": "en:Sultan Battery, Mangalore",
    },
    {
        "name": "Kadri Manjunatha Temple Cave Shrines",
        "category": "place_of_worship", "subcategory": "Ancient Cave Temple",
        "domain": "explore",
        "latitude": 12.8872, "longitude": 74.8553,
        "description": "10th–11th century Natha-sect temple complex with three natural rock cave shrines. Houses three Lokeshwara bronze statues dated to 968 CE — among the oldest surviving bronzes in coastal Karnataka. An underground spring inside the cave feeds the daily abhisheka ritual.",
        "opening_hours": "06:00–13:00, 16:00–20:30",
        "unexplored_signal": False,
        "hidden_gem_tier": 2,
        "best_time": "6:00–8:00 AM morning puja; avoid midday heat",
        "feast_season": "Kadri Manjunatha Rathotsava (Feb–Mar) — chariot festival",
        "tulu_cultural_tag": "natha_panth_cave_temple",
        "wikipedia": "en:Kadri Manjunatha Temple",
    },
    {
        "name": "St Aloysius Chapel Murals",
        "category": "tourism", "subcategory": "Heritage Church Frescoes",
        "domain": "explore",
        "latitude": 12.8716, "longitude": 74.8484,
        "description": "The interior walls and ceiling of this Jesuit chapel are entirely covered with over 100 fresco scenes painted by Italian Brother Antonio Moscheni between 1899–1900. The density and quality of the biblical narrative cycle is exceptional — deeply underrated at the national level.",
        "opening_hours": "09:00–17:00 Mon–Sat; limited Sunday",
        "unexplored_signal": False,
        "hidden_gem_tier": 2,
        "best_time": "Weekday mornings (lowest crowd)",
        "feast_season": "Christmas (elaborate nativity display)",
        "tulu_cultural_tag": "mangalorean_catholic_jesuit_art",
        "wikipedia": "en:St Aloysius Chapel, Mangalore",
    },
    {
        "name": "Old Bunder Quarter (Beary Heritage Walk)",
        "category": "historic", "subcategory": "Living Heritage Quarter",
        "domain": "explore",
        "latitude": 12.8667, "longitude": 74.8375,
        "description": "Mangalore's oldest continuously inhabited settlement, home to the Beary Muslim community whose trade roots predate the Portuguese by centuries. Early morning: incense merchants, gold traders, and a 300-year-old Friday mosque with distinctive Tulu Nadu timber architecture. No tourist infrastructure — a functioning living neighbourhood.",
        "opening_hours": "Always accessible (public street)",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "7:00–9:00 AM (morning market activity)",
        "feast_season": "Eid ul-Fitr; Milad-un-Nabi (street procession through Bunder)",
        "tulu_cultural_tag": "beary_heritage_quarter",
    },
    {
        "name": "Rosario Cathedral",
        "category": "place_of_worship", "subcategory": "Heritage Cathedral",
        "domain": "explore",
        "latitude": 12.8700, "longitude": 74.8455,
        "description": "One of the oldest Roman Catholic churches in India, established in the 16th century by the Portuguese. The current structure dates to 1910. Features a distinctive Indo-Portuguese Gothic facade and houses centuries-old liturgical artifacts. The feast of Our Lady of the Rosary (October) draws Mangalorean Catholics from across India.",
        "opening_hours": "06:00–19:00 daily",
        "unexplored_signal": False,
        "hidden_gem_tier": 3,
        "best_time": "Sunday 7 AM High Mass (most atmospheric)",
        "feast_season": "Our Lady of the Rosary feast (October)",
        "tulu_cultural_tag": "mangalorean_catholic_heritage",
        "wikipedia": "en:Rosario Cathedral, Mangalore",
    },
    {
        "name": "Mangaladevi Temple",
        "category": "place_of_worship", "subcategory": "Founding Temple",
        "domain": "explore",
        "latitude": 12.8607, "longitude": 74.8353,
        "description": "The Mangaladevi temple is the origin of the city's name — Mangalore derives from 'Mangaladevi'. Ancient goddess temple of probable pre-10th century origin. The 9-night Navarathri procession fills the old city. The 5 AM inaugural puja on day one of Navami is attended only by locals and rarely witnessed by outsiders.",
        "opening_hours": "06:00–13:00, 17:00–21:00",
        "unexplored_signal": False,
        "hidden_gem_tier": 2,
        "best_time": "Day 1 of Navarathri 5 AM (rare local puja); Day 9 Vijayadashami procession",
        "feast_season": "Navarathri (Sep/Oct — lunar calendar)",
        "tulu_cultural_tag": "mangaladevi_founding_temple",
    },

    # ════════════════════════════════════════════════════════
    # FESTIVALS / FEASTS / LIVE CULTURAL EVENTS
    # ════════════════════════════════════════════════════════
    {
        "name": "Karavali Utsav Festival Grounds",
        "category": "festival", "subcategory": "Regional Cultural Festival",
        "domain": "explore",
        "latitude": 12.9498, "longitude": 74.7977,
        "description": "Annual December coastal festival at Panambur Beach. Yakshagana, Kambala demonstration, Bhuta Kola, Pili Vesha (tiger dance), and boat race all converge in one place. The only occasion where all major Tulu cultural forms are staged simultaneously. Attended primarily by locals, minimal national promotion.",
        "opening_hours": "10:00–22:00 (December, exact dates vary annually)",
        "unexplored_signal": False,
        "hidden_gem_tier": 3,
        "best_time": "December; evening performances most intense",
        "feast_season": "December",
        "tulu_cultural_tag": "karavali_utsav_tulu_arts",
    },
    {
        "name": "Kambala Race Track (Bantwal region)",
        "category": "sport", "subcategory": "Kambala Traditional Buffalo Race",
        "domain": "activities",
        "latitude": 12.8950, "longitude": 74.9820,
        "description": "Kambala is the traditional buffalo race of Tulu Nadu — pairs of buffalos sprint through waterlogged paddy fields, the handler surfing on a plank behind them. Village Kambalas run Nov–March in private paddy fields. Attendance by respectful outsiders is welcome. The village atmosphere is incomparable to any televised version.",
        "opening_hours": "Village events — Sunday mornings, Nov–March (schedule varies)",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Nov–March Sunday mornings",
        "feast_season": "Kambala season: November–March",
        "tulu_cultural_tag": "kambala_tulu_buffalo_race",
        "wikipedia": "en:Kambala (sport)",
    },
    {
        "name": "Bhuta Kola Shrine (Kavoor Village)",
        "category": "historic", "subcategory": "Tulu Spirit Worship Ritual Site",
        "domain": "explore",
        "latitude": 12.9100, "longitude": 74.8650,
        "description": "Bhuta Kola is the animistic spirit-worship ritual of Tulu Nadu — a performer channels a village deity through costume, drumming, and trance in a ritual lasting sunset to dawn. Held at private family shrines (jumadis) in the post-harvest season. A living tradition completely invisible to tourism. Witnessing requires a local introduction.",
        "opening_hours": "Seasonal private events (Nov–Feb, post-harvest)",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Nov–Feb (post-harvest ritual season)",
        "feast_season": "Post-harvest Oct–Feb",
        "tulu_cultural_tag": "bhuta_kola_daiva_kola_animism",
        "wikipedia": "en:Bhuta Kola",
    },
    {
        "name": "Ullal Dargah Urs (Sayyid Muhammad Shareef)",
        "category": "festival", "subcategory": "Sufi Annual Urs",
        "domain": "explore",
        "latitude": 12.8155, "longitude": 74.8450,
        "description": "The 500-year-old dargah of Sayyid Muhammad Shareef-ul-Madani in Ullal draws devotees of all faiths during the annual Urs. Known locally as a unifying event where Hindu, Muslim, and Christian fishermen attend together. Qawwali performances continue through the night. A living example of coastal Karnataka's syncretic culture.",
        "opening_hours": "Urs week — lunar calendar (Rajab month, approx Jan–Mar)",
        "unexplored_signal": False,
        "hidden_gem_tier": 2,
        "best_time": "Urs night (qawwali from midnight)",
        "feast_season": "Rajab month Urs (Islamic lunar calendar)",
        "tulu_cultural_tag": "sufi_syncretic_coastal_culture",
        "wikipedia": "en:Syed Muhammad Shareef ul-Madani",
    },

    # ════════════════════════════════════════════════════════
    # UNEXPLORED LOCALITIES / AREAS
    # ════════════════════════════════════════════════════════
    {
        "name": "Ullal Village (Ferry Side)",
        "category": "place", "subcategory": "Coastal Fishing Village",
        "domain": "places",
        "latitude": 12.8120, "longitude": 74.8490,
        "description": "The village side of Ullal, across the river from the beach. A network of narrow lanes, fishing net repair yards, and centuries-old mosques and temples coexisting within metres. The Ullal beach is known; the village is not. Dargah of Syed Muhammad is here. Reached by the Ullal ferry.",
        "opening_hours": "Always open (public village)",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Morning 7:00–10:00 (market and mosque activity)",
        "feast_season": "Urs (Rajab); Eid; Navarathri (shared community celebrations)",
        "tulu_cultural_tag": "ullal_fishing_village_syncretic",
    },
    {
        "name": "Derebail Market Area",
        "category": "marketplace", "subcategory": "Local Neighbourhood Market",
        "domain": "local",
        "latitude": 12.9010, "longitude": 74.8650,
        "description": "A dense neighbourhood market in northern Mangalore serving the Derebail and Kankanady community. Fresh produce, spice merchants, flower sellers, and a weekly Sunday market that expands to three times its normal size. Almost exclusively local shoppers — no tourist presence. Authentic daily Mangalorean commerce.",
        "opening_hours": "07:00–20:00 daily; Sunday market 06:00–13:00",
        "unexplored_signal": True,
        "hidden_gem_tier": 1,
        "best_time": "Sunday 6:00–10:00 AM (extended market)",
        "feast_season": None,
        "tulu_cultural_tag": "local_neighbourhood_market",
    },
    {
        "name": "Kudroli Gokarnath Temple",
        "category": "place_of_worship", "subcategory": "Social Reform Temple",
        "domain": "explore",
        "latitude": 12.8780, "longitude": 74.8445,
        "description": "Founded in 1912 by social reformer Narayana Guru specifically to allow all castes equal entry at a time when caste exclusion was common in temples. The temple's social history is as significant as its architecture. The Navratri procession here is one of Mangalore's most colourful, with elaborate tableaux.",
        "opening_hours": "06:00–13:00, 17:00–21:00",
        "unexplored_signal": False,
        "hidden_gem_tier": 2,
        "best_time": "Navratri procession (Oct); morning puja 6–7 AM",
        "feast_season": "Navratri (Oct) — 9-night procession",
        "tulu_cultural_tag": "narayana_guru_social_reform_temple",
        "wikipedia": "en:Kudroli Gokarnath Temple",
    },
]


def get_hidden_gems() -> List[Dict]:
    logger.info(f"MangaloreHiddenGems — {len(HIDDEN_GEMS)} curated places")
    return HIDDEN_GEMS

def get_gems_by_domain(domain: str) -> List[Dict]:
    return [g for g in HIDDEN_GEMS if g.get("domain") == domain]

def get_gems_by_tier(tier: int) -> List[Dict]:
    return [g for g in HIDDEN_GEMS if g.get("hidden_gem_tier") == tier]

def get_unexplored_only() -> List[Dict]:
    return [g for g in HIDDEN_GEMS if g.get("unexplored_signal") is True]

def get_feast_season_gems() -> List[Dict]:
    return [g for g in HIDDEN_GEMS if g.get("feast_season")]


if __name__ == "__main__":
    gems = get_hidden_gems()
    print(f"\n  Total curated gems:   {len(gems)}")
    print(f"  Hyper-local (tier 1): {len(get_gems_by_tier(1))}")
    print(f"  Locally known (tier 2): {len(get_gems_by_tier(2))}")
    print(f"  With feast seasons:   {len(get_feast_season_gems())}")
    print(f"  Unexplored signal:    {len(get_unexplored_only())}")
    print()
    for g in get_gems_by_tier(1)[:4]:
        print(f"  • [{g['domain'].upper()}] {g['name']}")
        print(f"    {g['description'][:90]}...")
