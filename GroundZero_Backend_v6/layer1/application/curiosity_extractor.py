"""
Curiosity Vector extraction from Q7's free text (blueprint 4.8: "the most
important input").

This is a deterministic, fully offline lexicon-matcher: it maps words and
phrases in the tourist's one honest sentence to Ground Zero place
categories/tags with a weight, normalizes the result to a probability-like
distribution, and that's the curiosity_vector Layer 2 scores places
against.

This is a genuine, working implementation — not a stub — but it is
intentionally the simplest correct approach (keyword/lexicon matching) so
it has zero external dependencies and zero network calls. It's the
natural place to later swap in embedding similarity (e.g. sentence
embeddings against category descriptions) or an LLM-based extractor
without touching anything downstream, since Layer 2 only ever consumes
the resulting `CuriosityVector.weights` dict.
"""
from __future__ import annotations

import re
from collections import Counter

from layer1.domain.entities import CuriosityVector

# category/tag -> trigger words/phrases. Deliberately broad and Mangaluru-
# tourism-specific (temples, beaches, local food, heritage) rather than a
# generic English lexicon.
_LEXICON: dict[str, list[str]] = {
    "beach": ["beach", "shore", "coast", "sea", "sand", "waves"],
    "heritage_site": ["heritage", "history", "historic", "old", "colonial", "fort", "church", "temple", "mosque", "basilica"],
    "local_kitchen": ["local food", "authentic food", "home cooked", "street food", "local cuisine", "traditional food"],
    "cafe": ["coffee", "cafe", "quiet place", "work from", "chill spot"],
    "nature_spot": ["nature", "hike", "trail", "forest", "greenery", "waterfall", "wildlife"],
    "viewpoint": ["view", "viewpoint", "photo", "photos", "photography", "scenic", "panorama", "sunset point", "sunset"],
    "shopping_mall": ["shopping", "mall", "market", "souvenir", "shop"],
    "art_gallery": ["art", "gallery", "museum", "exhibit", "craft"],
    "adventure": ["adventure", "adrenaline", "boat ride", "watersports", "trekking"],
    "hidden_gem": ["hidden", "offbeat", "less crowded", "secret", "local secret", "not touristy", "authentic experience", "unseen", "undiscovered", "off the beaten path"],
    "festival": ["festival", "event", "celebration", "fair"],
    "spiritual": ["spiritual", "peaceful", "meditation", "prayer", "pilgrimage"],
    "family_friendly": ["kids", "children", "family friendly", "family", "families"],
}

_WORD_RE = re.compile(r"[a-z]+(?:\s[a-z]+)?")


class CuriosityExtractor:
    def extract(self, curiosity_text: str) -> CuriosityVector:
        text = curiosity_text.lower().strip()
        if not text:
            return CuriosityVector(weights={})

        counts: Counter[str] = Counter()
        for category, phrases in _LEXICON.items():
            for phrase in phrases:
                # Word-boundary match, phrase may be multi-word. `e?s?`
                # after the phrase handles simple plurals of the LAST word
                # (beach->beaches, temple->temples, shop->shops) without a
                # stemming library — confirmed real gap (an architectural
                # audit found "beaches and old temples" matched neither
                # "beach" nor "temple" under the old exact-form-only \b..\b
                # pattern, because there's no word boundary between "beach"
                # and its trailing "es"). Irregular plurals that don't
                # follow +s/+es (family->families) aren't caught by this
                # and are listed as explicit extra lexicon entries instead
                # (see "families" above) — simpler and more honest than a
                # regex trying to encode English pluralization rules.
                pattern = r"\b" + re.escape(phrase) + r"e?s?\b"
                matches = re.findall(pattern, text)
                if matches:
                    counts[category] += len(matches)

        if not counts:
            return CuriosityVector(weights={})

        total = sum(counts.values())
        weights = {category: round(count / total, 4) for category, count in counts.items()}
        return CuriosityVector(weights=weights)

    def affinity_for_category(self, vector: CuriosityVector, category: str, tags: list[str]) -> float:
        """How strongly a specific place (by category + tags) matches the
        tourist's curiosity_vector. Used directly as `curiosity_score` in
        Layer 2's Personal Fit Score formula."""
        if not vector.weights:
            return 0.5  # neutral prior when Q7 gave us nothing to match against

        score = vector.weights.get(category, 0.0)
        for tag in tags:
            score = max(score, vector.weights.get(tag, 0.0))
        return min(1.0, score * 3.0)  # rescale: a single dominant match should read as strong affinity, not a sliver
