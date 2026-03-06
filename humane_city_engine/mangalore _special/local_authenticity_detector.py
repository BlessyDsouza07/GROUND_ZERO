"""
Local Authenticity Detector

Purpose
-------
Identify authentic local places in Mangalore that
locals prefer but are not overly commercialized.

Signals Used
------------
- Trend dataset
- Specialty signals
- Local reference dataset

Output
------
List of hidden local gems with authenticity score
"""

import json
from collections import defaultdict

from mangalore_special.trend_sources_collector import build_trend_dataset
from mangalore_special.mangalore_specialty_collector import collect_specialty_signals


# -----------------------------------------------------
# Known Local Spots (Seed Dataset)
# -----------------------------------------------------

LOCAL_PLACE_CANDIDATES = [

    "ideal cafe",
    "hotel narayana",
    "machali restaurant",
    "giri manja's",
    "tannirbhavi beach",
    "central market mangalore",
    "pabbas ice cream",
    "taj mahal cafe hampankatta"
]


# -----------------------------------------------------
# TEXT NORMALIZATION
# -----------------------------------------------------

def normalize(text):

    return text.lower()


# -----------------------------------------------------
# AUTHENTICITY SCORE CALCULATION
# -----------------------------------------------------

def calculate_authenticity_scores():

    trends = build_trend_dataset()

    signals = collect_specialty_signals()

    scores = defaultdict(int)

    all_text = []

    for s in signals:

        all_text.append(normalize(str(s)))

    for group in trends.values():

        if isinstance(group, list):

            for item in group:

                if isinstance(item, dict):

                    text = item.get("title", "")

                else:

                    text = str(item)

                all_text.append(normalize(text))

    # detect mentions
    for place in LOCAL_PLACE_CANDIDATES:

        for text in all_text:

            if place in text:

                scores[place] += 1

    results = []

    for place, score in scores.items():

        results.append({

            "name": place,
            "authenticity_score": score
        })

    results.sort(key=lambda x: x["authenticity_score"], reverse=True)

    return results


# -----------------------------------------------------
# MAIN DETECTOR
# -----------------------------------------------------

def detect_local_gems():

    gems = calculate_authenticity_scores()

    dataset = {

        "city": "Mangalore",

        "local_gems": gems
    }

    return dataset


# -----------------------------------------------------
# MAIN
# -----------------------------------------------------

if __name__ == "__main__":

    data = detect_local_gems()

    print(json.dumps(data, indent=4))