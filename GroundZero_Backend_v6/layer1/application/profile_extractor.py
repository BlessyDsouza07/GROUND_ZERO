"""
ProfileExtractor — the "Talk to Your Guide" idea: infer as much of the
Soul Survey as honestly possible from one open sentence, so the tourist
answers what a lexicon genuinely can't guess (budget, a hard yes/no)
rather than tapping through every question a human wouldn't need to ask.

Same deterministic, offline, zero-dependency lexicon-matching style as
CuriosityExtractor (composed here, not duplicated) — this is not an LLM
call, it's more of the same honest keyword matching, just widened to
cover four more fields. Each field is only ever set when the lexicon
found a genuinely clear signal; anything ambiguous is left None and falls
through to its normal survey question, exactly as document 4 specifies.
That's the whole safety property here: SurveyService only ever writes a
field's answer slot when this returns non-None for it, so an unconfident
guess never silently becomes the tourist's profile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.domain.entities import CrowdTolerance, CuriosityVector, EnergyBand, GroupConfig, Purpose

# field -> {enum_value: [trigger phrases]}. Same word-boundary + optional
# plural (e?s?) matching as CuriosityExtractor, and same honesty rule: only
# infer when exactly one enum value's lexicon actually matched. If two
# different values both matched (e.g. "relax but see everything" — both
# LOW and HIGH energy words present), that's a genuinely ambiguous
# sentence, not a coin flip — leave it unset and let the normal question
# ask directly, rather than guessing.

_ENERGY_LEXICON: dict[str, list[str]] = {
    EnergyBand.LOW.value: ["relax", "chill", "slow", "easy", "unwind", "lazy", "laid back", "take it easy", "low key"],
    EnergyBand.HIGH.value: ["pack it in", "see everything", "action packed", "non stop", "adrenaline", "energetic", "busy day", "as much as possible"],
}

_GROUP_LEXICON: dict[str, list[str]] = {
    GroupConfig.SOLO.value: ["by myself", "solo", "alone", "on my own", "just me"],
    GroupConfig.COUPLE.value: ["my partner", "my wife", "my husband", "my girlfriend", "my boyfriend", "my fiance", "my fiancee", "honeymoon", "just the two of us"],
    GroupConfig.FAMILY.value: ["my kids", "my children", "my family", "with my parents", "my son", "my daughter"],
    GroupConfig.FRIENDS.value: ["my friends", "with friends", "our group", "friend group", "buddies"],
}

_CROWD_LEXICON: dict[str, list[str]] = {
    CrowdTolerance.PREFER_QUIET.value: ["not touristy", "not too touristy", "off the beaten path", "hidden", "quiet place", "less crowded", "avoid crowds", "away from tourists"],
    CrowdTolerance.LOVE_THEM.value: ["popular spots", "famous places", "bustling", "lively", "busy places", "touristy is fine"],
}

_PURPOSE_LEXICON: dict[str, list[str]] = {
    Purpose.FOODIE.value: ["good food", "eat", "food tour", "restaurants", "cuisine", "hungry", "foodie"],
    Purpose.SPIRITUAL.value: ["temple", "temples", "spiritual", "pilgrimage", "prayer", "meditation"],
    Purpose.ADVENTURE.value: ["adventure", "adrenaline", "trekking", "watersports", "thrill"],
    Purpose.CULTURAL.value: ["history", "heritage", "culture", "museum", "old town", "architecture"],
    Purpose.LEISURE.value: ["relax", "leisure", "unwind", "nothing planned", "just wander"],
}


@dataclass
class InferredProfile:
    curiosity_vector: CuriosityVector
    purpose: Optional[Purpose] = None
    energy_band: Optional[EnergyBand] = None
    group_config: Optional[GroupConfig] = None
    crowd_tolerance: Optional[CrowdTolerance] = None


def _single_confident_match(text: str, lexicon: dict[str, list[str]]) -> Optional[str]:
    hit_values = set()
    for value, phrases in lexicon.items():
        for phrase in phrases:
            pattern = r"\b" + re.escape(phrase) + r"e?s?\b"
            if re.search(pattern, text):
                hit_values.add(value)
                break
    if len(hit_values) == 1:
        return next(iter(hit_values))
    return None  # zero matches (nothing to infer) or 2+ conflicting matches (genuinely ambiguous) — either way, don't guess


class ProfileExtractor:
    def __init__(self, curiosity_extractor: CuriosityExtractor | None = None):
        self.curiosity_extractor = curiosity_extractor or CuriosityExtractor()

    def extract(self, opening_text: str) -> InferredProfile:
        text = opening_text.lower().strip()
        curiosity_vector = self.curiosity_extractor.extract(opening_text)

        if not text:
            return InferredProfile(curiosity_vector=curiosity_vector)

        purpose = _single_confident_match(text, _PURPOSE_LEXICON)
        energy = _single_confident_match(text, _ENERGY_LEXICON)
        group = _single_confident_match(text, _GROUP_LEXICON)
        crowd = _single_confident_match(text, _CROWD_LEXICON)

        return InferredProfile(
            curiosity_vector=curiosity_vector,
            purpose=Purpose(purpose) if purpose else None,
            energy_band=EnergyBand(energy) if energy else None,
            group_config=GroupConfig(group) if group else None,
            crowd_tolerance=CrowdTolerance(crowd) if crowd else None,
        )
