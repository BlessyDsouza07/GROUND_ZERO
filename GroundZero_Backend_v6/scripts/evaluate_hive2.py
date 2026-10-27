"""Offline evaluation of HIVE 2 on the real master data.
Run:  python scripts/evaluate_hive2.py
Reports only what it measures. These are rule-based checks on the current
data, not user outcomes; nothing here says people liked the results."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from explore.hours import open_info  # noqa: E402
from hive2.dataset import load_places  # noqa: E402
from hive2.intent import parse_intent  # noqa: E402
from hive2.ranker import Context, Profile, rank  # noqa: E402
from layer0.application.opening_hours_parser import OpeningHoursParser  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
PAR = OpeningHoursParser()
PLACES = load_places()
CENTRE = (12.8698, 74.8420)

PERSONAS = {
    "family_kids_veg": ("2 hours with kids, vegetarian", Profile()),
    "solo_quiet": ("quiet green walk, away from crowds", Profile()),
    "low_energy_elder": ("easy outing with my parents, not much walking", Profile()),
    "food_focused": ("local food, tiffin, snacks", Profile(affinities={"exp:food": {"weight": 0.9, "confidence": 0.9, "source": "stated"}})),
    "heritage": ("temples and old heritage", Profile()),
    "tight_budget": ("cheap, under 150", Profile()),
    "wheelchair_strict": ("easy sightseeing", Profile(constraints={"accessibility": ["wheelchair"], "accessibility_strict": True})),
    "less_touristy": ("hidden local spots", Profile()),
}
HOURS = [8, 11, 14, 17, 20, 23]


def of(p, now):
    i = open_info(p, PAR, now)
    return i.state, i.source, i.label


def main() -> None:
    runs = viol = cards = empty = typical = good = 0
    div = []
    for name, (text, prof) in PERSONAS.items():
        for h in HOURS:
            now = datetime(2026, 10, 13, h, 0, tzinfo=IST)
            it = parse_intent(text)
            res = rank(PLACES, Context(*CENTRE, now, minutes=it.minutes or 180, intent=it), prof, of)
            runs += 1
            if not res.items:
                empty += 1
                continue
            div.append(len({s.k.category for s in res.items}) / len(res.items))
            for s in res.items:
                cards += 1
                ev = s.k.evidence
                if s.open_state == "closed": viol += 1
                if it.budget_per_place and ev.estimated_cost is not None and ev.estimated_cost > it.budget_per_place: viol += 1
                if prof.constraints.get("accessibility_strict") and ev.wheelchair is not True: viol += 1
                if s.open_source != "listed": typical += 1
                if s.confidence_label in ("good", "fair"): good += 1
    print(f"places in data            : {len(PLACES)}")
    print(f"persona x hour runs       : {runs}  (empty results: {empty})")
    print(f"cards produced            : {cards}")
    print(f"constraint violations     : {viol}  ({viol / max(cards, 1):.1%})")
    print(f"mean category diversity   : {sum(div) / max(len(div), 1):.2f}  (1.0 = every stop a different category)")
    print(f"cards on typical hours    : {typical / max(cards, 1):.1%}  (not confirmed; labelled as such)")
    print(f"cards with fair+ evidence : {good / max(cards, 1):.1%}")


if __name__ == "__main__":
    main()
