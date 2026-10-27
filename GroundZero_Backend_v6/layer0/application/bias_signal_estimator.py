"""
Bias signal estimation — computes real, non-default inputs to the Bias
Index (`layer0/application/bias_audit.py`) for automatically-ingested
places. An architectural audit found that every OSM-ingested place
received `BiasSignals()` — i.e. every field at zero/default — meaning
every single place, regardless of actual character, produced the
identical bias_index (~0.35, "balanced"). This module closes that gap
with defensible, documented signals rather than leaving it unaddressed
or filling it with arbitrary numbers.

Honesty about what's a real signal vs. a heuristic prior, per field:

  - commercial_flags: REAL — counted directly from OSM tags that
    genuinely indicate commercial/touristy signals (a paid entry fee, a
    brand/franchise tag, an on-site shop tag). Not a guess.
  - tourist_popularity: PARTIALLY REAL — starts at a category-level
    prior (a "tourist_attraction"-tagged OSM place is more likely to be
    tourist-oriented than a "local_kitchen" by definition of the tag
    itself), then is bumped up by a REAL signal once enrichment
    completes: whether Wikidata/Wikipedia has an entry at all is a real,
    externally-verifiable fact about public documentation/notability,
    not fabricated.
  - local_percentage: HEURISTIC PRIOR ONLY — there is no real behavioral
    data source available (no review/check-in/foot-traffic API in this
    system's data sources). This is a category-level starting point
    only, clearly weaker evidence than the other two signals, and is
    documented as such everywhere it's used. It should be replaced by a
    real source (e.g. a review-platform integration) when one becomes
    available — this module is written so that's a drop-in change to
    _LOCAL_PERCENTAGE_PRIOR and nothing else.
  - media_mentions: HEURISTIC PROXY ONLY — no dedicated news/blog
    scanning source exists in this system's specified data sources
    (OSM, Wikidata, Wikipedia, Karnataka Tourism, local listings,
    community submissions, weather, tide, event RSS — none of these are
    a media-mention counter). Approximated from real fetched data (the
    length of the Wikipedia summary, when one exists) as a weak proxy
    for "how much has been written about this place," not fabricated,
    but explicitly the least reliable signal here.
"""
from __future__ import annotations

from layer0.domain.entities import BiasSignals

_COMMERCIAL_FLAG_TAGS = ("brand", "operator")

_TOURIST_POPULARITY_PRIOR: dict[str, float] = {
    "tourist_attraction": 0.6, "shopping_mall": 0.5, "beach": 0.4, "food_court": 0.4,
    "heritage_site": 0.3, "museum": 0.3, "viewpoint": 0.3, "theatre": 0.25,
    "art_gallery": 0.2, "market": 0.2, "craft_centre": 0.15,
    "cafe": 0.15, "restaurant": 0.15, "park": 0.1, "garden": 0.1,
    "local_kitchen": 0.05, "street_food": 0.05, "hidden_gem": 0.02,
}
_DEFAULT_TOURIST_POPULARITY_PRIOR = 0.15

_LOCAL_PERCENTAGE_PRIOR: dict[str, float] = {
    "local_kitchen": 0.85, "street_food": 0.8, "market": 0.75, "hidden_gem": 0.85,
    "bakery": 0.6, "dessert_shop": 0.55, "cafe": 0.5, "craft_centre": 0.5,
    "park": 0.5, "garden": 0.5, "library": 0.6,
    "restaurant": 0.4, "food_court": 0.3,
    "heritage_site": 0.3, "museum": 0.25, "art_gallery": 0.25, "viewpoint": 0.25,
    "beach": 0.2, "theatre": 0.3,
    "tourist_attraction": 0.1, "shopping_mall": 0.15,
}
_DEFAULT_LOCAL_PERCENTAGE_PRIOR = 0.4

_MEDIA_MENTIONS_FOR_SUMMARY_LENGTH = [(200, 1), (600, 3), (1500, 6)]
_MEDIA_MENTIONS_LONG_SUMMARY = 10


class BiasSignalEstimator:
    def estimate_from_osm_tags(self, category: str, osm_tags: dict[str, str]) -> BiasSignals:
        commercial_flags = 0
        if osm_tags.get("fee") == "yes":
            commercial_flags += 1
        if any(tag in osm_tags for tag in _COMMERCIAL_FLAG_TAGS):
            commercial_flags += 1
        if osm_tags.get("shop") is not None and category not in {"market", "craft_centre"}:
            commercial_flags += 1

        return BiasSignals(
            media_mentions=0,
            local_percentage=_LOCAL_PERCENTAGE_PRIOR.get(category, _DEFAULT_LOCAL_PERCENTAGE_PRIOR),
            commercial_flags=commercial_flags,
            tourist_popularity=_TOURIST_POPULARITY_PRIOR.get(category, _DEFAULT_TOURIST_POPULARITY_PRIOR),
            sponsored_indicator=False,
        )

    def refine_with_enrichment(
        self,
        signals: BiasSignals,
        has_wikidata_match: bool,
        has_wikipedia_match: bool,
        wiki_summary_length: int = 0,
    ) -> BiasSignals:
        if has_wikidata_match or has_wikipedia_match:
            signals.tourist_popularity = min(1.0, signals.tourist_popularity + 0.15)

        if wiki_summary_length > 0:
            for threshold, mentions in _MEDIA_MENTIONS_FOR_SUMMARY_LENGTH:
                if wiki_summary_length <= threshold:
                    signals.media_mentions = mentions
                    break
            else:
                signals.media_mentions = _MEDIA_MENTIONS_LONG_SUMMARY

        return signals

    def refine_with_community_feedback(
        self,
        signals: BiasSignals,
        thumbs_up: int,
        thumbs_down: int,
        times_removed: int,
        times_manually_added: int,
    ) -> BiasSignals:
        """A fourth, REAL signal source, added once the itinerary feedback
        feature exists: actual tourist behavior on this specific place,
        aggregated across every trip that included it (PlaceFeedbackSignal
        — see layer2/domain/feedback_entities.py). Unlike local_percentage
        and media_mentions above, this is measured, not guessed — it's
        just sparse early on (a new place has 0 signals, which is why this
        is a nudge on top of the existing priors, not a replacement for
        them). Small, bounded, and one-directional per event count so a
        handful of early signals can't swing bias_index wildly:

          - net thumbs (up - down), each worth up to 0.03 on
            local_percentage, capped at +-0.15 total — genuine tourists
            liking or disliking a place is closer evidence of authenticity
            than any prior.
          - times_manually_added nudges local_percentage up slightly
            (worth +0.02 each, capped at +0.1) — a place tourists actively
            sought out and added themselves, beyond what HIVE recommended,
            is real evidence it's not just algorithmically surfaced.
          - times_removed nudges tourist_popularity down slightly (worth
            -0.02 each, capped at -0.1) — repeatedly getting cut from
            people's actual plans is real evidence against it, independent
            of whatever media/wiki signals said.

        Called by scripts/apply_community_feedback.py, not by the live ETL
        pipeline — this is a periodic maintenance pass over EXISTING
        stored places (join PlaceFeedbackSignal -> Place, recompute,
        upsert), not something that runs during ingestion of new places
        (which have no feedback yet by definition).
        """
        net_thumbs = thumbs_up - thumbs_down
        local_pct_delta = max(-0.15, min(0.15, net_thumbs * 0.03))
        local_pct_delta += min(0.1, times_manually_added * 0.02)
        signals.local_percentage = max(0.0, min(1.0, signals.local_percentage + local_pct_delta))

        popularity_delta = -min(0.1, times_removed * 0.02)
        signals.tourist_popularity = max(0.0, min(1.0, signals.tourist_popularity + popularity_delta))

        return signals
