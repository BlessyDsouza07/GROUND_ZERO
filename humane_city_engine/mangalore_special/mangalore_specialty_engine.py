"""
Mangalore Specialty Intelligence Engine

Purpose
-------
Generate authentic Mangalore specialty recommendations.

Input Sources
-------------
- mangalore_specialties.json
- trend signals

Output
------
Structured tourism recommendation dataset

Rules
-----
No ratings.
No influencer bias.
Deterministic ranking.
Multi-source confirmation.
"""

import json
from pathlib import Path
from datetime import datetime

from mangalore_special.trend_sources_collector import build_trend_dataset

DATASET_PATH = "data_core/mangalore_specialties.json"


# ----------------------------------------------------
# LOAD SPECIALTY DATASET
# ----------------------------------------------------

def load_specialties():

    if not Path(DATASET_PATH).exists():

        raise FileNotFoundError(
            "Specialty dataset not found. Run specialty_dataset_builder first."
        )

    with open(DATASET_PATH, "r", encoding="utf8") as f:

        return json.load(f)


# ----------------------------------------------------
# TREND SCORE
# ----------------------------------------------------

def calculate_trend_score(item, trends):

    score = 0

    item = item.lower()

    for group in trends.values():

        if isinstance(group, list):

            for entry in group:

                if isinstance(entry, dict):

                    text = entry.get("title", "").lower()

                else:

                    text = str(entry).lower()

                if item in text:

                    score += 1

    return score


# ----------------------------------------------------
# RANKING ENGINE
# ----------------------------------------------------

def rank_items(items, trends):

    scored = []

    for item in items:

        score = calculate_trend_score(item, trends)

        scored.append({
            "name": item,
            "trend_score": score
        })

    scored.sort(key=lambda x: x["trend_score"], reverse=True)

    return scored


# ----------------------------------------------------
# BUILD SPECIALTY RECOMMENDATIONS
# ----------------------------------------------------

def generate_specialty_recommendations():

    specialties = load_specialties()

    trends = build_trend_dataset()

    must_eat = rank_items(specialties["must_eat"], trends)
    must_visit = rank_items(specialties["must_visit"], trends)
    must_buy = rank_items(specialties["must_buy"], trends)

    recommendations = {

        "city": "Mangalore",

        "generated_at": datetime.utcnow().isoformat(),

        "must_eat": must_eat,

        "must_visit": must_visit,

        "must_buy": must_buy
    }

    return recommendations


# ----------------------------------------------------
# MAIN
# ----------------------------------------------------

if __name__ == "__main__":

    data = generate_specialty_recommendations()

    print(json.dumps(data, indent=4))