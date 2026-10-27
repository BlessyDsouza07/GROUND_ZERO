"""
Pure logic behind `scripts/ingest_new_places.py` — no file or network I/O
here, so every rule is unit-testable (layer0/tests/test_place_ingest.py).

The one rule this whole module exists to protect: **a coordinate is only
ever written if it came from a real map feature that provably IS that
place.** The dataset has already been burned once by geocoders silently
falling back to a suburb or city centroid (several unrelated places pinned
to one point, later stripped out by scripts/audit_duplicate_coordinates.py).
So matching here is deliberately conservative — when unsure, a row stays
unresolved and is handed back for a hand-checked pin instead of guessed.

How a queue row is matched to an OpenStreetMap feature:

  1. Names are folded (accents, "Shri/Sri", "Jama/Juma/Jamia", "Mangalore/
     Mangaluru", apostrophes ...) and split into tokens.
  2. Generic words ("temple", "hotel", "masjid", "st", ...) and known
     locality names ("Kudroli", "Bejai", ...) are set aside. What remains
     are the *distinctive* tokens — "Sri Venkataramana Temple" -> {venkataramana}.
  3. A candidate matches only if its distinctive tokens equal the row's
     (typo-tolerant per token). A row with NO distinctive token ("Jamia
     Masjid") matches nothing: there are dozens of them.
  4. The candidate's own OSM tags must confirm the category (a place typed
     "beach" must be tagged natural=beach, not a restaurant named "Beach
     Cafe").
  5. If the row names a locality (in its name or address) the candidate
     must sit within LOCALITY_RADIUS_KM of it; if it names none, the
     candidate must at least be inside the city (CITY_RADIUS_KM).
  6. If several candidates survive and they are not all the same spot
     (within CLUSTER_METERS), the row is ambiguous and stays unresolved.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Optional

from shared.place_taxonomy import (
    RELIGIOUS_ETIQUETTE_NOTE,
    WORSHIP_TYPES,
    canonical_category,
)

BBOX = {"south": 12.75, "west": 74.78, "north": 13.05, "east": 75.05}  # same box as shared/config.py

LOCALITY_RADIUS_KM = 3.5
CITY_CENTER = (12.8698, 74.8433)     # Hampankatta — used only when a row names no locality at all
CITY_RADIUS_KM = 12.0
CLUSTER_METERS = 150.0
DEDUP_DISTANCE_METERS = 75.0        # same threshold as layer0/application/dedup.py
MIN_SEPARATION_METERS = 12.0        # two DIFFERENT places closer than this = suspicious collision

# --------------------------------------------------------------------------
# name folding
# --------------------------------------------------------------------------
_FOLDS: list[tuple[re.Pattern, str]] = [
    (re.compile(p), r) for p, r in [
        (r"\bsaint\b", "st"),
        (r"\b(shri|shree|sree|sri)\b", "sri"),
        (r"\b(masjid|masjeed|mosque|masjidh)\b", "masjid"),
        (r"\b(juma|jama|jumma|jamia|jame|jumah)\b", "jama"),
        (r"\b(mangalore|mangaluru|mangalur|kudla)\b", " "),
        (r"\b(kshetra|kshetram|devasthana|devasthanam|devalaya|mandir|mandira|gudi|temple)\b", "temple"),
        (r"\b(cafe|caffe|coffee house)\b", "cafe"),
        (r"\b(centre|center)\b", "center"),
        (r"\b(sultan|sulthan)\b", "sultan"),
    ]
]

GENERIC_TOKENS: frozenset[str] = frozenset({
    "the", "of", "and", "at", "in", "near", "opp", "opposite", "by", "for",
    "sri", "st", "temple", "church", "masjid", "jama", "shrine", "matha", "math", "basadi",
    "hotel", "restaurant", "cafe", "bar", "lodge", "residency", "inn", "hospital", "clinic",
    "market", "beach", "park", "garden", "road", "street", "cross", "bus", "stand", "stop",
    "station", "terminal", "junction", "center", "ltd", "pvt", "private", "limited", "shop",
    "store", "bakery", "sweets", "mall", "complex", "building", "food", "family",
})
# Words that are generic for *names* but which we do NOT want to strip when
# they are the only thing left — handled by the "empty core => ambiguous" rule.

_STOPWORDS: frozenset[str] = frozenset({"the", "of", "and", "at", "in", "near", "opp", "opposite", "by", "for"})

# When a name is only "<locality> <category word>", OSM often stores just the
# locality on a feature whose TAGS already say it is that category (Mukka ->
# natural=beach). The category word is then redundant, so it is ignored.
_CATEGORY_ECHO: dict[str, frozenset[str]] = {
    "beach": frozenset({"beach"}), "market": frozenset({"market"}), "park": frozenset({"park"}),
    "garden": frozenset({"garden"}), "lake": frozenset({"lake"}),
}
# Not echoed for places of worship on purpose: "<locality> Masjid" is not
# unique (Bolar alone has several), so those need the whole name to match.

# Type words: if the row and the OSM feature each name a type and the types
# differ ("Central Masjid" vs "Central Market"), they are different places.
_TYPE_WORDS: frozenset[str] = frozenset({
    "temple", "church", "masjid", "shrine", "market", "beach", "hotel", "restaurant", "cafe",
    "hospital", "clinic", "park", "garden", "lake", "mall", "bakery", "station", "school", "college",
    "bar", "lodge",
})


def _type_conflict(q_tokens: Iterable[str], f_tokens: Iterable[str]) -> bool:
    qt, ft = set(q_tokens) & _TYPE_WORDS, set(f_tokens) & _TYPE_WORDS
    return bool(qt and ft and not (qt & ft))

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def fold_name(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ").replace("\u2019", "'")
    s = re.sub(r"[.'`]", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    for pattern, repl in _FOLDS:
        s = pattern.sub(repl, s)
    return [t for t in _TOKEN_SPLIT.split(s) if t]


def norm_key(name: str) -> str:
    return " ".join(fold_name(name))


def _token_close(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or a[0] != b[0]:
        return False  # typos rarely change the first letter; Pavoor != Kavoor
    return SequenceMatcher(None, a, b).ratio() >= 0.82


def token_sets_equal(a: set[str], b: set[str]) -> bool:
    """Typo-tolerant set equality: every token of one side must pair with a
    distinct token of the other, and vice versa (so {'poonja','international'}
    never equals {'international'})."""
    if len(a) != len(b) or not a:
        return False
    remaining = list(b)
    for ta in a:
        hit = next((tb for tb in remaining if _token_close(ta, tb)), None)
        if hit is None:
            return False
        remaining.remove(hit)
    return True


def split_tokens(tokens: Iterable[str], locality_tokens: set[str]) -> tuple[set[str], set[str]]:
    """-> (distinctive core tokens, locality tokens found)."""
    core, locs = set(), set()
    for t in tokens:
        if t in GENERIC_TOKENS:
            continue
        if t in locality_tokens:
            locs.add(t)
        else:
            core.add(t)
    return core, locs


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


def in_bbox(lat: float, lon: float) -> bool:
    return BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lon <= BBOX["east"]


# --------------------------------------------------------------------------
# OSM candidates
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class OsmFeature:
    kind: str                     # "n" | "w"
    osm_id: int
    names: tuple[str, ...]
    lat: float
    lon: float
    tags: dict = field(default_factory=dict, hash=False, compare=False)
    # alt_name / old_name / loc_name: fine for matching a business, but NOT
    # trusted for neighbourhoods ("Pavoor" must not resolve to the node
    # called Kavoor just because one lists the other as an alias).
    primary_count: int = 0        # names[:primary_count] are name / name:en; 0 = unknown, treat all as primary

    @property
    def primary_names(self) -> tuple[str, ...]:
        return self.names[: self.primary_count] if self.primary_count else self.names

    @property
    def url(self) -> str:
        return f"https://www.openstreetmap.org/{'node' if self.kind == 'n' else 'way'}/{self.osm_id}"


_LOCALITY_PLACE_RANK = {"city": 5, "town": 5, "suburb": 4, "quarter": 4, "neighbourhood": 3,
                        "village": 3, "locality": 2, "hamlet": 2, "isolated_dwelling": 1}


def _eat(t: dict, *keys_values: tuple[str, set[str]]) -> bool:
    return any(t.get(k) in vals for k, vals in keys_values)


_FOOD = {"restaurant", "cafe", "fast_food", "food_court", "bar", "pub", "ice_cream", "biergarten"}


def osm_confirms_category(category: str, t: dict) -> bool:
    """True only if the feature's own tags positively support `category`."""
    c = canonical_category(category)
    if c == "heritage_site":
        return bool(t.get("historic") or t.get("religion") or t.get("amenity") == "place_of_worship"
                    or t.get("building") in {"temple", "church", "mosque", "chapel", "shrine", "cathedral"}
                    or t.get("tourism") in {"attraction", "museum"})
    if c in {"restaurant", "cafe", "street_food", "local_kitchen", "food_court"}:
        return t.get("amenity") in _FOOD
    if c in {"bakery", "dessert_shop"}:
        return t.get("shop") in {"bakery", "confectionery", "pastry"} or t.get("amenity") in {"ice_cream", "cafe"}
    if c == "market":
        return t.get("amenity") == "marketplace" or t.get("shop") in {"seafood", "greengrocer", "supermarket"}
    if c == "lodging":
        return t.get("tourism") in {"hotel", "guest_house", "hostel", "motel", "apartment", "resort", "chalet"}
    if c == "beach":
        return t.get("natural") in {"beach", "bay"} or t.get("leisure") == "beach_resort"
    if c in {"park", "garden"}:
        return t.get("leisure") in {"park", "garden", "nature_reserve"}
    if c in {"viewpoint", "nature_spot"}:
        return t.get("tourism") == "viewpoint" or t.get("natural") in {"peak", "cliff", "cave_entrance", "water", "wood"} \
            or t.get("leisure") == "nature_reserve" or t.get("waterway") is not None
    if c == "tourist_attraction":
        return t.get("tourism") in {"attraction", "zoo", "theme_park", "aquarium", "museum"} \
            or t.get("man_made") == "lighthouse" or bool(t.get("historic"))
    if c == "museum":
        return t.get("tourism") == "museum" or t.get("amenity") == "planetarium"
    if c == "hospital":
        return t.get("amenity") in {"hospital", "clinic", "doctors"} or bool(t.get("healthcare"))
    if c == "pharmacy":
        return t.get("amenity") == "pharmacy"
    if c == "fire_station":
        return t.get("amenity") == "fire_station"
    if c == "police_station":
        return t.get("amenity") == "police"
    if c == "bus_stand":
        return t.get("amenity") == "bus_station" or t.get("highway") == "bus_stop" or t.get("public_transport") is not None
    if c == "railway":
        return t.get("railway") in {"station", "halt"} or t.get("public_transport") == "station"
    if c == "airport":
        return t.get("aeroway") is not None
    if c == "transit_point":
        return t.get("amenity") == "ferry_terminal" or t.get("man_made") == "pier" or t.get("public_transport") is not None
    if c == "ev_charger":
        return t.get("amenity") == "charging_station"
    if c == "sports_venue":
        return t.get("leisure") in {"stadium", "sports_centre", "pitch", "fitness_centre"}
    if c == "institution":
        return t.get("amenity") in {"university", "college", "school"}
    if c == "shopping_mall":
        return t.get("shop") == "mall"
    if c == "local_shop":
        return t.get("shop") is not None
    if c == "locality":
        return t.get("place") in _LOCALITY_PLACE_RANK
    return False


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------
@dataclass
class Resolution:
    status: str                       # "resolved" | "unresolved"
    reason: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    feature: Optional[OsmFeature] = None
    method: str = ""


def _lookup_locality(tok: str, localities: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    """Exact hit, else a spelling variant (queue says Hampankatta, OSM says
    Hampankatte)."""
    if tok in localities:
        return localities[tok]
    if len(tok) < 5:
        return None
    for key, centroid in localities.items():
        if _token_close(tok, key):
            return centroid
    return None


def _locality_hits(name_tokens: list[str], address: str, localities: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """Locality tokens mentioned in the row's name or address -> centroid."""
    hits: dict[str, tuple[float, float]] = {}
    for t in name_tokens:
        if t not in GENERIC_TOKENS and (c := _lookup_locality(t, localities)):
            hits[t] = c
    for part in re.split(r"[,/]", address or ""):
        for t in fold_name(part):
            if t not in GENERIC_TOKENS and (c := _lookup_locality(t, localities)):
                hits[t] = c
    return hits


def resolve_from_osm(
    name: str,
    category: str,
    address: str,
    features: list[OsmFeature],
    localities: dict[str, tuple[float, float]],
) -> Resolution:
    cat = canonical_category(category)
    q_tokens = fold_name(name)
    locality_names = set(localities)
    q_core, q_locs = split_tokens(q_tokens, locality_names)

    if cat == "locality":
        return _resolve_locality(name, features)

    # A name made only of generic words + a locality ("Mukka Beach", "Kadri
    # Market") has no distinctive core; then the *whole* name must match, so
    # "Kadri Market" can never match "Kadri Park".
    q_full = {t for t in q_tokens if t not in _STOPWORDS}
    if not q_core and not q_full:
        return Resolution("unresolved", "name has no distinctive word (too generic to match safely)")

    hits = _locality_hits(q_tokens, address, localities)
    if not q_core and not hits:
        return Resolution("unresolved", "generic name and no locality to anchor it (e.g. 'Jamia Masjid')")

    survivors: list[OsmFeature] = []
    for f in features:
        if not in_bbox(f.lat, f.lon):
            continue
        if not osm_confirms_category(cat, f.tags):
            continue
        matched = False
        for fname in f.names:
            f_tokens = fold_name(fname)
            if _type_conflict(q_tokens, f_tokens):
                continue
            if q_core:
                f_core, _ = split_tokens(f_tokens, locality_names)
                ok = token_sets_equal(q_core, f_core)
            else:
                echo = _CATEGORY_ECHO.get(cat, frozenset())
                f_full = {t for t in f_tokens if t not in _STOPWORDS}
                ok = token_sets_equal(q_full - echo or q_full, f_full - echo or f_full)
            if ok:
                matched = True
                break
        if not matched:
            continue
        if hits:
            if not any(haversine_m(f.lat, f.lon, *c) / 1000 <= LOCALITY_RADIUS_KM for c in hits.values()):
                continue
        elif haversine_m(f.lat, f.lon, *CITY_CENTER) / 1000 > CITY_RADIUS_KM:
            continue  # nothing pins this row to a neighbourhood, so it must at least be in the city itself
        survivors.append(f)

    if not survivors:
        return Resolution("unresolved", "no confirmed match in the OSM extract (place is not mapped, or is named differently)")

    anchor = survivors[0]
    if any(haversine_m(anchor.lat, anchor.lon, s.lat, s.lon) > CLUSTER_METERS for s in survivors[1:]):
        return Resolution("unresolved", f"ambiguous: {len(survivors)} different OSM features match this name")

    # Same physical place mapped more than once nearby: prefer the
    # best-tagged feature, and a node over a way centroid.
    best = max(survivors, key=lambda s: (len(s.tags), s.kind == "n"))
    return Resolution("resolved", lat=round(best.lat, 7), lon=round(best.lon, 7), feature=best, method="osm_extract")


def _resolve_locality(name: str, features: list[OsmFeature]) -> Resolution:
    q = set(fold_name(name)) - GENERIC_TOKENS
    if not q:
        return Resolution("unresolved", "empty locality name")
    cands = []
    for f in features:
        place = f.tags.get("place")
        if place not in _LOCALITY_PLACE_RANK or not in_bbox(f.lat, f.lon):
            continue
        for fname in f.primary_names:
            if token_sets_equal(q, set(fold_name(fname)) - GENERIC_TOKENS):
                cands.append(f)
                break
    if not cands:
        return Resolution("unresolved", "locality not found in the OSM extract")
    top_rank = max(_LOCALITY_PLACE_RANK[c.tags["place"]] for c in cands)
    top = [c for c in cands if _LOCALITY_PLACE_RANK[c.tags["place"]] == top_rank]
    a = top[0]
    if any(haversine_m(a.lat, a.lon, c.lat, c.lon) > 1500 for c in top[1:]):
        return Resolution("unresolved", "ambiguous locality (several distant OSM matches)")

    # Corroboration: OSM has homonymous villages elsewhere in the box (a
    # "Balmatta" or "Kuloor" node many km from the real neighbourhood).
    # If plenty of other features carry this locality's name, the place node
    # must sit where they cluster.
    tok = next(iter(q)) if len(q) == 1 else None
    if tok and not _corroborated(a.lat, a.lon, tok, features):
        return Resolution("unresolved", "OSM place node disagrees with where features named after it cluster")
    return Resolution("resolved", lat=round(a.lat, 7), lon=round(a.lon, 7), feature=a, method="osm_locality")


def _corroborated(lat: float, lon: float, tok: str, features: list[OsmFeature]) -> bool:
    """True unless plenty (>=3) of other features carry this locality's name
    AND they cluster > 2.5 km from (lat, lon) — i.e. the place node is a
    homonymous village elsewhere in the box."""
    pts = [(f.lat, f.lon) for f in features
           if f.tags.get("place") is None and in_bbox(f.lat, f.lon)
           and any(tok in fold_name(n) for n in f.names)]
    if len(pts) < 3:
        return True
    lat_m = sorted(p[0] for p in pts)[len(pts) // 2]
    lon_m = sorted(p[1] for p in pts)[len(pts) // 2]
    return haversine_m(lat, lon, lat_m, lon_m) <= 2500


def build_locality_index(features: list[OsmFeature]) -> dict[str, tuple[float, float]]:
    """single-token locality name -> centroid, from OSM place=* features
    (primary names only). Ambiguous tokens keep the highest-ranked feature;
    a node that fails corroboration (see _corroborated) is left out rather
    than trusted."""
    best: dict[str, tuple[int, float, float]] = {}
    for f in features:
        place = f.tags.get("place")
        rank = _LOCALITY_PLACE_RANK.get(place or "")
        if not rank or not in_bbox(f.lat, f.lon):
            continue
        for fname in f.primary_names:
            toks = [t for t in fold_name(fname) if t not in GENERIC_TOKENS]
            if len(toks) != 1:
                continue
            t = toks[0]
            if len(t) < 4:
                continue
            if t not in best or rank > best[t][0]:
                best[t] = (rank, f.lat, f.lon)
    return {t: (v[1], v[2]) for t, v in best.items() if _corroborated(v[1], v[2], t, features)}


# --------------------------------------------------------------------------
# dedup against existing data
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class KnownPlace:
    name: str
    category: str
    lat: float
    lon: float


def find_existing(name: str, category: str, lat: float | None, lon: float | None,
                  known: list[KnownPlace], localities: set[str]) -> KnownPlace | None:
    """Same place already in the dataset? Same rule the ETL dedup applies
    (close in space AND similar name), plus exact-name equality."""
    nk = norm_key(name)
    q_core, _ = split_tokens(fold_name(name), localities)
    for k in known:
        if norm_key(k.name) == nk:
            return k
    if lat is None or lon is None:
        return None
    for k in known:
        d = haversine_m(lat, lon, k.lat, k.lon)
        if d > DEDUP_DISTANCE_METERS:
            continue
        k_core, _ = split_tokens(fold_name(k.name), localities)
        sim = SequenceMatcher(None, nk, norm_key(k.name)).ratio()
        if sim >= 0.82 or (q_core and token_sets_equal(q_core, k_core)):
            return k
    return None


def collides_with_other_place(lat: float, lon: float, name: str, known: list[KnownPlace]) -> KnownPlace | None:
    """A DIFFERENT place sitting within a few metres of this pin is the
    signature of a generic-centroid fallback."""
    nk = norm_key(name)
    for k in known:
        if norm_key(k.name) != nk and haversine_m(lat, lon, k.lat, k.lon) < MIN_SEPARATION_METERS:
            return k
    return None


# --------------------------------------------------------------------------
# row building
# --------------------------------------------------------------------------
_URL_RE = re.compile(r"https?://\S+")


def extract_source_url(source_note: str) -> str:
    m = _URL_RE.search(source_note or "")
    return m.group(0).rstrip(").,;'\"]") if m else ""


def google_maps_search_url(name: str, address: str) -> str:
    from urllib.parse import quote_plus
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name}, {address}".strip(", "))


def build_community_row(header: list[str], q: dict, res: Resolution, curator: str) -> list[str]:
    """One full-width community_places.csv row. Only fields we genuinely
    know are filled; everything else stays blank so the ETL falls back to
    the documented category-level prior (PlaceEnricher) instead of a guess."""
    raw_type = (q.get("category") or "").strip().lower().replace(" ", "_")
    cat = canonical_category(raw_type)
    tags: list[str] = []
    if raw_type and raw_type != cat:
        tags.append(raw_type)
    f = res.feature
    ft = f.tags if f else {}
    for key in ("religion", "denomination", "cuisine"):
        v = ft.get(key)
        if v:
            tags.extend(x.strip() for x in v.replace(",", ";").split(";") if x.strip())
    tags = list(dict.fromkeys(tags))

    source_url = (q.get("pin_source", "").strip() or extract_source_url(q.get("source_note", "")) or (f.url if f else ""))
    address = (q.get("address") or "").strip()
    if q.get("pin_note", "").strip():
        address = f"{address} ({q['pin_note'].strip()})" if address else f"({q['pin_note'].strip()})"
    values = {
        "name": q["name"].strip(),
        "category": cat,
        "lat": f"{res.lat}",
        "lon": f"{res.lon}",
        "address": address,
        "curator": curator,
        "source_url": source_url,
        "opening_hours": ft.get("opening_hours", ""),
        "tags": ";".join(tags),
        "contact_phone": ft.get("phone", ""),
    }
    if raw_type in WORSHIP_TYPES:
        values["etiquette_tag"] = RELIGIOUS_ETIQUETTE_NOTE
    return [values.get(col, "") for col in header]
