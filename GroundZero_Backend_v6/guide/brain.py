"""The guide's own knowledge, used whenever the language model is not
available (or fails). It understands what the person is asking, answers
from Mangaluru knowledge, and recommends only places that are open now,
nearest first. It never lists unrelated places and never pretends to know
something it doesn't.
"""
from __future__ import annotations

import re
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from explore.hours import EAT, STAY, TRANSIT, open_info

CENTRE = (12.9141, 74.8560)


def _km(a, b, c, d) -> float:
    p1, p2 = radians(a), radians(c)
    h = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(d - b) / 2) ** 2
    return 12742 * asin(sqrt(h))


# intent -> (trigger regex, categories, name/tag keywords, intro line)
_FOOD_KW = {
    "seafood": ("fish|seafood|sea food|prawn|crab|lobster|squid|pomfret|bangude|anjal|mackerel|surmai",
                {"restaurant", "local_kitchen", "street_food"}, ["sea", "fish", "prawn", "crab", "coastal", "malpe", "gassi", "mangalorean", "kerala", "bunder", "marine", "ocean"],
                "Fresh seafood is what Mangaluru does best. Ask for the day's catch: bangude (mackerel) fry, pomfret, anjal (kingfish) and prawn gassi with neer dosa are the local favourites."),
    "veg": ("veg|vegetarian|tiffin|idli|dosa|vada|breakfast|udupi|thali|meals",
            {"restaurant", "local_kitchen", "cafe"}, ["udupi", "veg", "woodlands", "mess", "bhavan", "tiffin", "shetty", "pai", "kamath", "adyar", "naivedyam", "dosa"],
            "For vegetarian food Mangaluru is excellent: Udupi-style tiffin rooms for neer dosa, idli, buns and a proper vegetarian thali."),
    "coffee": ("coffee|tea|chai|cafe|café|filter",
               {"cafe", "coffee_shop", "bakery", "restaurant"}, ["cafe", "coffee", "chai", "tea", "brew", "bake"],
               "For a good coffee, a cafe or an old-school filter coffee stall both do the job."),
    "sweet": ("ice cream|icecream|dessert|sweet|gadbad|kulfi|cake|bakery|pastry|bun",
              {"dessert_shop", "bakery", "cafe", "street_food"}, ["ice", "cream", "pabba", "ideal", "sweet", "bake", "dessert", "gadbad", "cake", "bun"],
              "Mangaluru loves its desserts: gadbad ice cream is the one to try, and the soft sweet banana buns are a local breakfast classic."),
    "street": ("street food|snack|chaat|golgappa|pani puri|evening snack|bajji|samosa",
               {"street_food", "food_court", "local_kitchen"}, ["chaat", "puri", "bajji", "snack", "chat", "stall", "kabab", "kebab"],
               "Street food comes alive in the evening, usually from around 4 pm."),
    "nonveg": ("chicken|mutton|biryani|non veg|non-veg|kebab|kabab|ghee roast|kori|egg|beef|pork",
               {"restaurant", "local_kitchen"}, ["biryani", "chicken", "kebab", "kabab", "mughlai", "ghee", "kori", "non", "bhojan"],
               "For non-veg, chicken ghee roast with kori rotti is the Mangalorean signature. Biryani and kebabs are strong around Bunder and Kankanady."),
    "world": ("sushi|japanese|thai|korean|italian|pasta|pizza|burger|chinese|continental|mexican|momos|ramen",
              {"restaurant", "cafe"}, [], ""),
}

_KB = {
    "about": "Mangaluru (Mangalore) is a port city on the Arabian Sea in coastal Karnataka, about 350 km west of Bengaluru. It sits where the Netravati and Gurpura rivers meet the sea, and is known for its beaches, temples and churches, and a food culture of seafood, neer dosa and ghee roast.",
    "airport": "Mangaluru International Airport (IXE) is at Bajpe, about 20 km north of the city. Taxis and app cabs take around 35 to 45 minutes to the centre, and there are KSRTC and airport buses as well.",
    "train": "Mangaluru Central is the main railway station, near Hampankatta. Mangaluru Junction at Kankanady is the second one, used by many trains towards Kerala, Konkan and Bengaluru.",
    "bus": "City buses run through Hampankatta and State Bank, which is also where the private bus stand is. KSRTC long-distance buses leave from the Bejai area KSRTC stand. Autos are cheap for short hops; agree the fare or use the meter first.",
    "transport": "In Mangaluru you can use city buses, auto-rickshaws and app cabs. Autos are best for short hops, and it's wise to agree the fare or use the meter first. For beaches and day trips, a cab or a rented two-wheeler is easiest.",
    "weather": "Mangaluru is hot and humid. June to September is heavy monsoon, October to February is the pleasant season, and March to May is hot. Sunset is around 6 pm in winter and about 6:45 pm in summer.",
    "season": "The best time is October to February, when it's dry and breezy. Avoid peak monsoon (June to August) for beaches, since swimming is risky then.",
    "safety": "Mangaluru is generally safe for travellers. Avoid swimming at unguarded beaches, especially in monsoon and after dark, keep valuables close in crowded bus stands, and agree auto fares before you ride.",
    "festival": "Mangaluru Dasara with its tiger dance (pili vesha), Kambala buffalo races in winter, Yakshagana performances, Christmas and Monti Fest, and Ganesh Chaturthi are the big ones. Bhuta Kola, the spirit worship, is a deeply local tradition.",
    "language": "Tulu, Kannada, Konkani and Beary are spoken, and almost everyone in the city understands some Hindi and English. A friendly 'Yenchina?' (Tulu for 'how are you?') goes down well.",
    "daytrip": "Good day trips from Mangaluru: Udupi and Malpe (about 60 km), Dharmasthala and Kukke Subramanya, Moodabidri's Thousand Pillar Basadi, Karkala, Manipal, and Gokarna a few hours north.",
    "etiquette": "At temples cover your shoulders and knees and remove your footwear. Some temples ask men to remove shirts, so check at the door. Ask before photographing people, and be quiet around prayer.",
    "famous": "Mangaluru is famous for Kadri Manjunath and Mangaladevi temples, St. Aloysius Chapel's paintings, Panambur and Tannirbhavi beaches, Pilikula, the old port at Bunder, and above all its food.",
    "rain": "On a rainy day go indoors: St. Aloysius Chapel, Pilikula's planetarium, a museum, and a long meal of hot neer dosa and ghee roast. Skip the beaches until it clears.",
    "kids": "With kids, Pilikula Nisargadhama (zoo, planetarium, boating), Panambur Beach and the parks work well. Ice cream stops help.",
    "shopping": "Hampankatta, State Bank and Bunder are the old shopping centres. City Centre Mall and Forum Fiza are the big malls. For local things look for Mangalorean banana chips, jackfruit chips, cashews and filter coffee.",
    "hello": "Hi there. I'm your Mangaluru guide. Ask me where to eat, what to see, how to get around, or what is open right now.",
    "thanks": "You're welcome. Enjoy Mangaluru, and ask me anytime.",
}

_RULES = [
    ("hello", r"^\s*(hi|hello|hey|namaste|namaskara|good (morning|evening|afternoon))\b"),
    ("thanks", r"\b(thanks|thank you|thx)\b"),
    ("airport", r"\b(airport|flight|bajpe)\b"),
    ("train", r"\b(railway|train|station|junction)\b"),
    ("bus", r"\b(bus|ksrtc)\b"),
    ("transport", r"\b(auto|cab|taxi|uber|ola|ferry|get around|reach|commute|transport|travel from|how (do|can) i get)\b"),
    ("weather", r"\b(weather|temperature|hot|humid|monsoon)\b"),
    ("season", r"\b(best time|when to visit|season|which month)\b"),
    ("safety", r"\b(safe|safety|dangerous|scam|security)\b"),
    ("festival", r"\b(festival|dasara|kambala|yakshagana|bhuta|pili vesha|celebrat)"),
    ("language", r"\b(language|tulu|kannada|konkani|beary|speak)\b"),
    ("daytrip", r"\b(day trip|nearby town|udupi|gokarna|dharmasthala|manipal|malpe|kukke|karkala|moodabidri|excursion)\b"),
    ("etiquette", r"\b(etiquette|dress code|what to wear|customs|manners)\b"),
    ("rain", r"\b(rain|rainy|wet day)\b"),
    ("kids", r"\b(kid|kids|child|children|family|toddler)\b"),
    ("shopping", r"\b(shop|shopping|souvenir|buy|mall|market)\b"),
    ("about", r"\b(where is|what is|tell me about|about) (mangalore|mangaluru)\b|\bwhere is mangal|\bwhat('s| is) mangal|\bhistory of mangal"),
    ("famous", r"\b(famous for|known for|must see|must visit|top (things|sights)|highlights)\b"),
]

_PLACE_RULES = [
    ("beach", r"\b(beach|sea|sunset|waves|coast)\b", {"beach"}, ["beach"], "Sunset at a Mangaluru beach is a classic. Go about 45 minutes before sunset."),
    ("temple", r"\b(temple|pray|prayer|church|mosque|worship|spiritual|god)\b", {"temple", "church", "mosque"}, ["temple", "church", "mosque", "kshetra", "basilica"], "Mangaluru's temples, churches and mosques are worth seeing, and several are very old."),
    ("heritage", r"\b(heritage|history|historic|fort|museum|old|culture|tourist|sightsee|sights|attraction)\b", {"heritage_site", "museum", "tourist_attraction", "attraction", "art_gallery"}, [], "For history and culture, these are the places worth your time."),
    ("nature", r"\b(park|lake|garden|nature|walk|peaceful|quiet|relax|green)\b", {"park", "lake", "garden", "nature_spot", "viewpoint"}, [], "For a calm green break, these are good."),
    ("shopping_places", r"\b(mall|market|shopping)\b", {"shopping_mall", "market"}, [], "Here is where to shop."),
]


def _open_places(places, now, cats=None, kws=None, lat=None, lng=None, limit=4):
    from layer0.application.opening_hours_parser import OpeningHoursParser

    parser = OpeningHoursParser()
    clat, clng = (lat, lng) if lat is not None and lng is not None else CENTRE
    pool = []
    for p in places:
        if p.category == "uncategorized":
            continue
        if cats is not None and p.category not in cats and not (set(p.tags or []) & cats):
            continue
        name = (p.name or "").lower()
        tags = " ".join(p.tags or []).lower()
        hit = bool(kws) and any(k in name or k in tags for k in kws)
        if kws and not hit:
            continue
        info = open_info(p, parser, now)
        if info.state == "closed":
            continue
        d = _km(clat, clng, p.coordinates.latitude, p.coordinates.longitude)
        pool.append((d, p, info))
    pool.sort(key=lambda x: x[0])
    seen, out = set(), []
    for d, p, info in pool:
        key = re.sub(r"[^a-z0-9]", "", (p.name or "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((p, d, info))
        if len(out) >= limit:
            break
    return out


def _list(found, with_dist: bool) -> str:
    return "\n".join(
        f"- {p.name}" + (f", {d:.1f} km away" if with_dist else "") + (f" ({info.label.lower()})" if info.label else "")
        for p, d, info in found
    )


def answer(question: str, places, now: datetime, lat=None, lng=None):
    q = question.lower().strip()
    located = lat is not None and lng is not None
    used = []

    for key, rx in _RULES:
        if re.search(rx, q):
            return _KB[key], used

    # food
    food_trigger = re.search(r"\b(eat|food|hungry|lunch|dinner|breakfast|snack|restaurant|meal|dish|cuisine|taste|try)\b", q)
    for key, (rx, cats, kws, intro) in _FOOD_KW.items():
        if re.search(rf"\b({rx})", q):
            if key == "world":
                hit = re.search(rx, q).group(0)
                found = _open_places(places, now, cats, [hit, hit[:4]], lat, lng)
                if found:
                    return f"A few places that may serve {hit}:\n{_list(found, located)}\nCheck the menu before you go.", [p for p, _, _ in found]
                alt = _open_places(places, now, _FOOD_KW["seafood"][1], _FOOD_KW["seafood"][2], lat, lng, 3)
                tail = f"\nOpen now and worth trying instead:\n{_list(alt, located)}" if alt else ""
                return (f"{hit.capitalize()} isn't a Mangaluru speciality, and I don't know a place here that's known for it. "
                        f"A multi-cuisine restaurant may have it, so check the menu.{tail}"), [p for p, _, _ in alt]
            found = _open_places(places, now, cats, kws, lat, lng)
            if not found:
                found = _open_places(places, now, cats, None, lat, lng)
            late = now.hour >= 21
            note = " It's late, so many kitchens will be closing soon." if late else ""
            if found:
                return f"{intro}{note}\nOpen now:\n{_list(found, located)}", [p for p, _, _ in found]
            return f"{intro} Nothing I know is open right now, so try again in the morning or evening.", []
    if food_trigger:
        found = _open_places(places, now, EAT, None, lat, lng)
        if found:
            return "Here is food that's open right now:\n" + _list(found, located), [p for p, _, _ in found]
        return "Most kitchens are closed at this hour. Hotel restaurants and a few late-night places may still be open. Try again after 7 am.", []

    # stay
    if re.search(r"\b(stay|hotel|room|sleep|lodge|lodging|homestay|accommodation|night)\b", q):
        found = _open_places(places, now, STAY, None, lat, lng)
        if found:
            return "Places to stay, closest first:\n" + _list(found, located) + "\nCall ahead to confirm availability and price.", [p for p, _, _ in found]

    for key, rx, cats, kws, intro in _PLACE_RULES:
        if re.search(rx, q):
            found = _open_places(places, now, cats, kws or None, lat, lng)
            if found:
                return f"{intro}\nOpen now:\n{_list(found, located)}", [p for p, _, _ in found]
            return f"{intro} Nothing I know of is open for that right now.", []

    # plan a day
    if re.search(r"\b(plan|itinerary|schedule|day plan|what to do|to do|things to do|suggest|recommend|bored|explore)\b", q):
        h = now.hour
        steps = []
        for label, cats in (("Start with", {"temple", "church", "heritage_site"}), ("Then eat at", EAT), ("Later, go to", {"park", "lake", "beach", "viewpoint", "museum"})):
            f = _open_places(places, now, cats, None, lat, lng, 1)
            if f:
                steps.append(f"{label} {f[0][0].name}")
        if steps:
            return "A simple plan from what's open now:\n- " + "\n- ".join(steps) + "\nFor a full timed itinerary, use Plan a Trip.", []

    return ("I'm not sure I understood that. I can help with food, places to stay, beaches, temples, getting around, "
            "weather and day trips. Try asking something like 'where can I eat fresh seafood' or 'how do I get from the airport to the city'."), []
