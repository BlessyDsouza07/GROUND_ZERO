"""Regenerates sample_data/*.json (offline demo + tests). Run from the layer3 folder: python scripts/make_sample_data.py"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "sample_data"
ROOT.mkdir(exist_ok=True)


def P(pid, name, cat, sub, lat, lng, tags, bias, local, media, cost, free, acc, etq, unavail, grade, crowd, energy, dwell, extract, facts, food, hours, addr):
    return {"place_id": pid, "name": name, "category": cat, "subcategory": sub, "lat": lat, "lng": lng, "city": "Mangalore",
            "tags": tags, "trip_relevance_tags": tags, "bias_index": bias, "local_percentage": local, "media_mentions": media,
            "estimated_cost": cost, "is_free_entry": free, "accessibility_tags": acc, "etiquette_tag": etq,
            "temporarily_unavailable": unavail, "grade": grade, "crowd_level": crowd, "energy_requirement": energy,
            "dwell_time_typical": dwell, "wikipedia_extract": extract, "wikidata_facts": facts, "food_notes": food,
            "opening_hours": hours, "address": addr, "bias_recommendation": "keep", "source": "sample"}


places = [
    P("gz_milagres", "Milagres Church", "SPIRITUAL", "church", 12.8698, 74.8433, ["churches", "heritage", "history", "architecture", "authentic"], 0.25, 60, 40, 0, True, ["wheelchair-friendly"], "cover shoulders", False, "A", None, "low", 15,
      "Milagres Church is a Roman Catholic church in Hampankatta, Mangalore. It was built in 1680 by Bishop Thomas de Castro. The church is known for its Gothic-style architecture and carved wooden altar. It draws quiet visitors in the mornings.",
      {"inception": "1680", "architectural_style": "Gothic Revival"}, None, "Mo-Su 06:00-19:00", "Hampankatta, Mangaluru"),
    P("gz_stann", "St. Ann's Hilltop Chapel", "SPIRITUAL", "chapel", 12.8712, 74.8449, ["churches", "heritage", "authentic"], 0.1, 90, 2, 0, True, ["stairs-only"], "cover shoulders", True, "B", None, "medium", 20,
      "St. Ann's is a small hilltop chapel above the old town. It is currently under renovation.", {}, None, "Mo-Su 07:00-18:00", "Bendore, Mangaluru"),
    P("gz_rosario", "Rosario Cathedral", "SPIRITUAL", "cathedral", 12.8735, 74.8412, ["churches", "heritage", "architecture"], 0.2, 70, 25, 0, True, ["wheelchair-friendly"], "cover shoulders", False, "A", None, "low", 20,
      "Rosario Cathedral is a Catholic cathedral in Mangalore, consecrated in 1910 and inspired by St. Peter's Basilica in Rome. Its dome and frescoes are its main draw. Mass is held daily.",
      {"inception": "1910"}, None, "Mo-Su 06:00-19:00", "Car Street, Mangaluru"),
    P("gz_kadri", "Kadri Manjunath Temple", "SPIRITUAL", "temple", 12.8870, 74.8500, ["temples", "spiritual", "heritage", "history"], 0.2, 80, 30, 0, True, ["stairs"], "remove footwear, no leather items inside", False, "A", "medium", "medium", 25,
      "Kadri Manjunath Temple is a Hindu temple dedicated to Lord Manjunatha, built around the 10th century. It is known for its bronze statues. The temple complex has several sacred ponds.",
      {"inception": "1068"}, None, "Mo-Su 05:30-13:00,16:30-20:30", "Kadri, Mangaluru"),
    P("gz_mangaladevi", "Mangaladevi Temple", "SPIRITUAL", "temple", 12.8393, 74.8418, ["temples", "spiritual", "heritage", "authentic"], 0.15, 85, 15, 0, True, ["wheelchair-friendly"], "remove footwear", False, "A", None, "low", 20,
      "Mangaladevi Temple is an ancient temple that gave the city of Mangalore its name. It is dedicated to the goddess Mangaladevi.", {}, None, "Mo-Su 06:00-13:00,16:00-20:00", "Bolar, Mangaluru"),
    P("gz_lobo", "Mrs. Lobo's Home Kitchen", "FOOD", "home kitchen", 12.8721, 74.8402, ["local-food", "authentic", "seafood"], 0.05, 100, 2, 350, False, ["wheelchair-friendly"], None, False, "A", "low", "low", 50,
      "Mrs. Lobo's Home Kitchen serves Mangalorean Catholic home cooking from a family kitchen.", {},
      "Known for fish curry and pork sorpotel. The fish curry is medium spicy. A vegetarian thali can be arranged with notice.", "Mo-Sa 12:00-15:00,19:00-21:30; Su off", "Kodialbail, Mangaluru"),
    P("gz_janata", "Janata Idli Shop", "FOOD", "idli shop", 12.8690, 74.8420, ["local-food", "authentic", "vegetarian"], 0.08, 95, 1, 60, False, ["wheelchair-friendly"], None, False, "B", "medium", "low", 30,
      "A tiny neighbourhood breakfast counter serving steamed idli and sambar.", {}, "Vegetarian breakfast. Idli, vada and sambar; mild spice.", "Mo-Su 06:30-11:30", "Hampankatta, Mangaluru"),
    P("gz_summer", "Summer Sands Resort", "STAY", "resort", 12.8080, 74.8420, ["beach", "leisure"], 0.85, 10, 500, 4500, False, [], None, False, "C", "high", "low", 120,
      "A commercial beach resort.", {}, None, None, "Ullal, Mangaluru"),
    P("gz_panambur", "Panambur Beach", "NATURE", "beach", 12.9469, 74.8054, ["beach", "nature", "leisure", "sunset"], 0.45, 40, 120, 0, True, ["uneven-terrain"], None, False, "A", "high", "medium", 60,
      "Panambur Beach is a popular beach north of Mangalore near the New Mangalore Port. It is known for its sunsets and water sports.", {}, None, None, "Panambur, Mangaluru"),
    P("gz_tanni", "Tannirbhavi Beach", "NATURE", "beach", 12.9339, 74.8085, ["beach", "nature", "authentic", "sunset"], 0.2, 70, 12, 0, True, ["uneven-terrain"], None, False, "B", "low", "medium", 50,
      "Tannirbhavi Beach is a quieter beach on the Netravati river mouth, popular with locals in the evenings.", {}, None, None, "Tannirbhavi, Mangaluru"),
    P("gz_sultan", "Sultan Battery", "EXPLORE", "watchtower", 12.9083, 74.8098, ["history", "heritage", "architecture"], 0.3, 50, 35, 20, False, ["stairs"], None, False, "B", "low", "medium", 30,
      "Sultan Battery is a watchtower built by Tipu Sultan in 1784 to prevent warships from entering the Gurupura river. It is built of black stone.", {"inception": "1784"}, None, "Mo-Su 08:00-18:00", "Boloor, Mangaluru"),
    P("gz_pilikula", "Pilikula Nisargadhama", "NATURE", "park", 12.9247, 74.8905, ["nature", "park", "family"], 0.4, 45, 80, 120, False, ["wheelchair-friendly"], None, False, "A", "medium", "medium", 120,
      "Pilikula Nisargadhama is a biological park with a zoo, botanical garden and lake.", {}, None, "Tu-Su 09:30-17:30", "Vamanjoor, Mangaluru"),
    P("gz_falnir", "Falnir Bazaar", "SHOPPING", "market", 12.8686, 74.8493, ["shopping", "local-life", "authentic"], 0.1, 90, 3, 100, False, ["wheelchair-friendly"], None, False, "B", "medium", "medium", 40,
      "A busy neighbourhood bazaar with fruit sellers, tailors and spice shops.", {}, None, "Mo-Sa 09:00-20:00", "Falnir, Mangaluru"),
    P("gz_craft", "Clay Pot Painting Studio", "LOCAL_LIFE", "craft workshop", 12.8705, 74.8440, ["crafts", "artisan", "authentic", "local-life"], 0.05, 100, 0, 150, False, ["wheelchair-friendly"], None, False, "B", "low", "low", 40,
      "A small studio run by a veteran potter who teaches clay pot painting.", {}, None, "Mo-Sa 10:00-20:00", "Bendore, Mangaluru"),
    P("gz_hospital", "City Hospital (sample)", "EMERGENCY", "hospital", 12.8740, 74.8420, ["emergency"], 0.0, 100, 0, 0, True, [], None, False, "B", "low", "low", 5, "Multi-speciality hospital.", {}, None, "24/7", "Hampankatta, Mangaluru"),
    P("gz_police", "Police Station (sample)", "EMERGENCY", "police", 12.8700, 74.8460, ["emergency"], 0.0, 100, 0, 0, True, [], None, False, "B", "low", "low", 5, "City police station.", {}, None, "24/7", "Mangaluru"),
]
(ROOT / "master_data_core.sample.json").write_text(json.dumps({"_note": "SAMPLE DATA for offline demo/tests only. Coordinates approximate. Real data comes from Layer 0's master_data_core.json.", "places": places}, indent=2, ensure_ascii=False), encoding="utf-8")

profile = {"profile_id": "asha_demo", "device_id": "device-demo-1", "purpose": "cultural", "energy_band": "medium", "crowd_tolerance": "fine", "budget": 1500,
           "dietary_flags": ["veg"], "group_config": "couple", "group_session_id": None,
           "curiosity_text": "I want to see old churches and eat authentic Mangalorean food, not touristy restaurants.",
           "curiosity_vector": ["heritage", "churches", "local-food", "authentic"], "trip_duration_hours": 8, "start_time_preference": "mid_morning",
           "accessibility_flags": [], "companion_language": "en", "voice_personality": "warm", "return_visitor_exclusions": [], "created_at": "2026-09-22T03:30:00+00:00"}
(ROOT / "profile.sample.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")

itin = {"itinerary_id": "demo", "days": [{"day_number": 1, "slots": [
    {"slot_role": "GROUNDING", "recommendation": {"place_id": "gz_janata", "place_name": "Janata Idli Shop"}, "time_window": "09:00-09:40"},
    {"slot_role": "PERSONAL", "recommendation": {"place_id": "gz_milagres", "place_name": "Milagres Church"}, "time_window": "09:50-10:15"},
    {"slot_role": "PERSONAL", "recommendation": {"place_id": "gz_stann", "place_name": "St. Ann's Hilltop Chapel"}, "time_window": "10:30-11:00"},
    {"slot_role": "ANCHOR", "recommendation": None, "time_window": "12:30-13:15"},
    {"slot_role": "LOCAL_SECRET", "recommendation": {"place_id": "gz_lobo", "place_name": "Mrs. Lobo's Home Kitchen"}, "time_window": "13:15-14:00"},
    {"slot_role": "WILDCARD", "recommendation": {"place_id": "gz_craft", "place_name": "Clay Pot Painting Studio"}, "time_window": "15:00-15:40"},
    {"slot_role": "SIGNATURE", "recommendation": {"place_id": "gz_tanni", "place_name": "Tannirbhavi Beach"}, "time_window": "16:30-17:30"}],
    "alternatives": [{"slot_role": "PERSONAL", "recommendation": {"place_id": "gz_rosario"}}]}]}
(ROOT / "itinerary.sample.json").write_text(json.dumps(itin, indent=2, ensure_ascii=False), encoding="utf-8")
print("sample data written to", ROOT)
