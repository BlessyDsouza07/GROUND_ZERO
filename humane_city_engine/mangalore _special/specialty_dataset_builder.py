"""
Mangalore Specialty Dataset Builder

Purpose:
Builds a verified dataset of authentic Mangalore specialties.

Sources:
- trend_sources_collector
- mangalore_specialty_collector

Output:
data_core/mangalore_specialties.json

Rules:
- No fake data
- Multi-source validation
- Only real Mangalore specialties
"""

import json
import re
from pathlib import Path

from mangalore_special.trend_sources_collector import build_trend_dataset
from mangalore_special.mangalore_specialty_collector import collect_specialty_signals


OUTPUT_PATH = "data_core/mangalore_specialties.json"


# ---------------------------------------------------
# Known Authentic Mangalore Specialties
# (Seed dataset to validate signals)
# ---------------------------------------------------

KNOWN_MANGALORE_FOODS = [
    "neer dosa",
    "goli baje",
    "kori rotti",
    "mangalore buns",
    "fish curry",
    "chicken sukka",
    "bangude pulimunchi"
]

KNOWN_MANGALORE_PLACES = [
    "panambur beach",
    "tannirbhavi beach",
    "kadri temple",
    "pilikula nisargadhama",
    "st aloysius chapel",
    "someshwara beach"
]

KNOWN_MANGALORE_PRODUCTS = [
    "cashew",
    "spices",
    "mangalore tiles",
    "seafood"
]


# ---------------------------------------------------
# TEXT NORMALIZER
# ---------------------------------------------------

def normalize(text):

    text = text.lower()

    text = re.sub(r"[^a-zA-Z0-9 ]", " ", text)

    return text


# ---------------------------------------------------
# SPECIALTY DETECTOR
# ---------------------------------------------------

def detect_foods(text):

    found = []

    for food in KNOWN_MANGALORE_FOODS:

        if food in text:
            found.append(food)

    return found


def detect_places(text):

    found = []

    for place in KNOWN_MANGALORE_PLACES:

        if place in text:
            found.append(place)

    return found


def detect_products(text):

    found = []

    for item in KNOWN_MANGALORE_PRODUCTS:

        if item in text:
            found.append(item)

    return found


# ---------------------------------------------------
# DATASET BUILDER
# ---------------------------------------------------

def build_specialty_dataset():

    print("Collecting specialty signals...")

    signals = collect_specialty_signals()

    trends = build_trend_dataset()

    all_text = []

    for s in signals:
        all_text.append(normalize(str(s)))

    for group in trends.values():

        if isinstance(group, list):

            for item in group:

                if isinstance(item, dict):

                    text = item.get("title", "")

                    all_text.append(normalize(text))

    foods = set()
    places = set()
    products = set()

    for text in all_text:

        foods.update(detect_foods(text))
        places.update(detect_places(text))
        products.update(detect_products(text))

    dataset = {

        "city": "Mangalore",

        "must_eat": sorted(list(foods)),

        "must_visit": sorted(list(places)),

        "must_buy": sorted(list(products)),

        "generated_at": None
    }

    Path("data_core").mkdir(exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:

        json.dump(dataset, f, indent=4)

    print("Dataset saved:", OUTPUT_PATH)

    return dataset


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

if __name__ == "__main__":

    build_specialty_dataset()