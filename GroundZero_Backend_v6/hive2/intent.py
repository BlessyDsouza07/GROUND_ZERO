"""Turn a free-text request into structured intent. Rule-based on purpose:
transparent, offline, and never invents constraints the person did not say."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

_INTERESTS = {
    "coastal": ("beach", "sea", "sunset", "coast", "waves", "fishing", "harbour", "backwater", "estuary"),
    "food": ("eat", "food", "hungry", "lunch", "dinner", "breakfast", "snack", "tiffin", "seafood", "coffee", "chai", "dessert", "biryani", "dosa", "ice cream"),
    "heritage": ("temple", "church", "mosque", "heritage", "history", "old", "palace", "museum", "culture", "basadi", "traditional"),
    "nature": ("nature", "park", "lake", "garden", "green", "walk", "trail", "quiet", "peaceful", "calm"),
    "neighbourhood": ("market", "bazaar", "local", "street", "lanes", "neighbourhood", "neighborhood", "shopping"),
}


@dataclass
class Intent:
    text: str = ""
    minutes: Optional[int] = None
    interests: list[str] = field(default_factory=list)
    avoid_crowds: bool = False
    low_energy: bool = False
    with_kids: bool = False
    with_elderly: bool = False
    budget_per_place: Optional[int] = None
    diet: list[str] = field(default_factory=list)
    mode: Optional[str] = None          # surprise | slow | less_touristy
    wants_stay: bool = False
    recognised: list[str] = field(default_factory=list)   # what we understood, shown back to the user


def parse_minutes(t: str) -> Optional[int]:
    t = t.lower()
    if re.search(r"half (an )?hour|30 ?min", t):
        return 30
    m = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", t)
    if m:
        return int(float(m.group(1)) * 60)
    m = re.search(r"(\d+)\s*(minutes?|mins?|m)\b", t)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(one|two|three|four|five|six)\s*(hours?|hrs?)\b", t)
    if m:
        return _NUM_WORDS[m.group(1)] * 60
    if re.search(r"an hour|1 hour", t):
        return 60
    if re.search(r"quick|short break|few minutes", t):
        return 45
    if re.search(r"half[- ]?day|morning free|afternoon free", t):
        return 240
    if re.search(r"whole day|full day|all day", t):
        return 480
    return None


def parse_intent(text: str) -> Intent:
    raw = (text or "").strip()[:400]
    t = raw.lower()
    it = Intent(text=raw)
    it.minutes = parse_minutes(t)
    if it.minutes:
        it.recognised.append(f"about {it.minutes} min")
    for key, words in _INTERESTS.items():
        if any(re.search(rf"\b{re.escape(w)}", t) for w in words):
            it.interests.append(key)
    if it.interests:
        it.recognised.append("interested in " + ", ".join(it.interests))
    if re.search(r"crowd|quiet|peaceful|calm|away from|not busy|less busy|alone time", t):
        it.avoid_crowds = True
        it.recognised.append("avoiding crowds")
    if re.search(r"tired|exhaust|low energy|relax|slow|lazy|rest\b|don'?t want to walk|not much walking", t):
        it.low_energy = True
        it.recognised.append("easy pace")
    if re.search(r"\bkids?\b|child|children|toddler|baby|family", t):
        it.with_kids = True
        it.recognised.append("with children")
    if re.search(r"elder|grandparent|grandmother|grandfather|senior|parents", t):
        it.with_elderly = True
        it.low_energy = True
        it.recognised.append("with older family")
    m = re.search(r"(?:under|below|within|max|upto|up to)\s*(?:rs\.?|₹|inr)?\s*(\d{2,5})", t)
    if m:
        it.budget_per_place = int(m.group(1))
        it.recognised.append(f"under ₹{it.budget_per_place} a place")
    elif re.search(r"cheap|budget|low cost|inexpensive", t):
        it.budget_per_place = 300
        it.recognised.append("budget-friendly")
    for word, tag in (("vegetarian", "veg"), ("veg ", "veg"), ("pure veg", "veg"), ("jain", "jain"), ("halal", "halal"), ("vegan", "vegan")):
        if word in t + " " and tag not in it.diet:
            it.diet.append(tag)
    if "non-veg" in t or "non veg" in t:
        it.diet = [d for d in it.diet if d != "veg"]
    if it.diet:
        it.recognised.append("diet: " + ", ".join(it.diet))
    if re.search(r"surprise|something different|random|anything", t):
        it.mode = "surprise"
    elif re.search(r"hidden|offbeat|off the beaten|not touristy|less touristy|local spots|like a local", t):
        it.mode = "less_touristy"
    elif it.low_energy and re.search(r"slow|unhurried|no rush|relax", t):
        it.mode = "slow"
    if it.mode:
        it.recognised.append({"surprise": "surprise me", "less_touristy": "less touristy", "slow": "slow down"}[it.mode])
    if re.search(r"hotel|stay\b|room|lodge|place to sleep|where to sleep", t):
        it.wants_stay = True
    return it
