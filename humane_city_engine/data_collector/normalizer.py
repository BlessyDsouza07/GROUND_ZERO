"""
normalizer.py

Converts raw OSM JSON data into structured BaseEntity objects
compatible with the Data Core pipeline.

This module:
- Cleans raw OSM data
- Deduplicates entries
- Maps OSM tags → Domain enum
- Outputs BaseEntity objects
- Does NOT store raw reviews
"""

import json
from datetime import datetime
from typing import List

from core.base_models import BaseEntity, Domain


# ============================================================
# DOMAIN MAPPING LOGIC
# ============================================================

def map_to_domain(tags: dict) -> Domain:
    """
    Maps OSM tags to core Domain enum.
    """

    amenity = tags.get("amenity")
    tourism = tags.get("tourism")
    historic = tags.get("historic")
    natural = tags.get("natural")
    leisure = tags.get("leisure")
    shop = tags.get("shop")

    # Emergency & Safety
    if amenity in ["hospital", "police", "fire_station"]:
        return Domain.EMERGENCY

    # Stay
    if tourism in ["hotel", "hostel", "guest_house"]:
        return Domain.STAY

    # Food
    if amenity in [
        "restaurant",
        "cafe",
        "fast_food",
        "bar",
        "pub"
    ]:
        return Domain.FOOD

    # Transport
    if amenity in [
        "bus_station",
        "ferry_terminal",
        "taxi",
        "parking"
    ]:
        return Domain.TRANSPORT

    # Explore & Culture
    if tourism in ["museum", "attraction"] or historic:
        return Domain.EXPLORE

    # Nature
    if natural or leisure in ["park", "beach"]:
        return Domain.PLACES

    # Shopping & Local Life
    if shop:
        return Domain.LOCAL

    # Default fallback
    return Domain.PLACES


# ============================================================
# NORMALIZATION ENGINE
# ============================================================

def normalize_to_entities(raw_file_path: str) -> List[BaseEntity]:
    """
    Convert raw OSM JSON into BaseEntity list.

    Args:
        raw_file_path (str): Path to raw OSM JSON

    Returns:
        List[BaseEntity]
    """

    with open(raw_file_path, encoding="utf-8") as f:
        raw_data = json.load(f)

    entities: List[BaseEntity] = []
    seen_ids = set()

    for element in raw_data.get("elements", []):

        element_id = element.get("id")

        # Deduplicate
        if element_id in seen_ids:
            continue
        seen_ids.add(element_id)

        tags = element.get("tags", {})
        name = tags.get("name")

        # Skip unnamed
        if not name:
            continue

        # Extract coordinates safely
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")

        if lat is None or lon is None:
            continue

        domain = map_to_domain(tags)

        entity = BaseEntity(
            name=name.strip(),
            domain=domain,
            category=tags.get("amenity")
                     or tags.get("tourism")
                     or tags.get("historic")
                     or tags.get("natural")
                     or tags.get("leisure")
                     or tags.get("shop")
                     or "general",
            subcategory=tags.get("tourism") or tags.get("amenity") or "general",
            latitude=float(lat),
            longitude=float(lon),
            sources=["OSM"],
            created_at=datetime.utcnow()
        )

        entities.append(entity)

    print(f"✅ Normalized {len(entities)} clean entities.")

    return entities
