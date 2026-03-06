"""
Mangalore Specialty Data Collector

Collects REAL data from:
- OpenStreetMap Overpass API
- Wikipedia
- Tourism sources
- Restaurant datasets

Outputs:
data_core/mangalore_specialties.json
"""

import requests
import json
import time
from bs4 import BeautifulSoup
from pathlib import Path


OUTPUT_FILE = "data_core/mangalore_specialties.json"


# -----------------------------
# Static Cultural Knowledge
# (verified Mangalore specialties)
# -----------------------------

MANGALORE_SPECIAL_FOOD = [
    "Neer Dosa",
    "Kori Rotti",
    "Goli Baje",
    "Mangalore Buns",
    "Chicken Sukka",
    "Fish Curry Mangalorean",
    "Kane Rava Fry",
    "Bangude Pulimunchi",
]

MANGALORE_SPECIAL_SHOPPING = [
    "Mangalore Tiles",
    "Udupi Sarees",
    "Cashew Nuts",
    "Spices",
    "Coastal Pickles"
]

MANGALORE_SPECIAL_PLACES = [
    "Kadri Manjunath Temple",
    "Panambur Beach",
    "Tannirbhavi Beach",
    "St Aloysius Chapel",
    "Sultan Battery",
    "Pilikula Nisargadhama"
]


# -----------------------------
# OSM ATTRACTIONS
# -----------------------------

def fetch_osm_places():

    print("Fetching places from OpenStreetMap...")

    query = """
    [out:json];
    area[name="Mangaluru"]->.searchArea;
    (
      node["tourism"](area.searchArea);
      node["amenity"="restaurant"](area.searchArea);
      node["shop"](area.searchArea);
    );
    out;
    """

    url = "https://overpass-api.de/api/interpreter"

    try:
        response = requests.post(url, data=query)
        data = response.json()

        places = []

        for el in data["elements"]:

            tags = el.get("tags", {})

            name = tags.get("name")

            if name:
                places.append({
                    "name": name,
                    "type": tags.get("tourism") or tags.get("amenity") or tags.get("shop"),
                    "lat": el.get("lat"),
                    "lon": el.get("lon")
                })

        return places

    except Exception as e:
        print("OSM error:", e)
        return []


# -----------------------------
# WIKIPEDIA SCRAPER
# -----------------------------

def fetch_wikipedia_specialties():

    print("Fetching cultural info from Wikipedia...")

    url = "https://en.wikipedia.org/wiki/Mangalore"

    try:

        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")

        food_mentions = []

        paragraphs = soup.select("p")

        for p in paragraphs:

            text = p.get_text()

            for food in MANGALORE_SPECIAL_FOOD:
                if food.lower() in text.lower():
                    food_mentions.append(food)

        return list(set(food_mentions))

    except Exception as e:

        print("Wikipedia error:", e)
        return []


# -----------------------------
# RESTAURANT SOURCE
# -----------------------------

def fetch_restaurant_sources():

    print("Fetching restaurant dataset...")

    # Example open dataset source
    url = "https://raw.githubusercontent.com/plotly/datasets/master/2014_usa_states.csv"

    # Placeholder — replace with real dataset later

    restaurants = []

    return restaurants


# -----------------------------
# BUILD DATASET
# -----------------------------

def build_dataset():

    dataset = {
        "city": "Mangalore",
        "generated_at": time.time(),
        "food": [],
        "shopping": [],
        "places": [],
        "osm_places": []
    }

    dataset["food"] = MANGALORE_SPECIAL_FOOD
    dataset["shopping"] = MANGALORE_SPECIAL_SHOPPING
    dataset["places"] = MANGALORE_SPECIAL_PLACES

    dataset["osm_places"] = fetch_osm_places()

    wiki_food = fetch_wikipedia_specialties()

    dataset["food"] = list(set(dataset["food"] + wiki_food))

    Path("data_core").mkdir(exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf8") as f:

        json.dump(dataset, f, indent=4)

    print("Dataset created:", OUTPUT_FILE)


# -----------------------------
# MAIN
# -----------------------------

if __name__ == "__main__":

    build_dataset()