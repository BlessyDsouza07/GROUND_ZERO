from layer0.application.bias_signal_estimator import BiasSignalEstimator


def test_local_kitchen_gets_high_local_percentage_prior():
    result = BiasSignalEstimator().estimate_from_osm_tags("local_kitchen", {})
    assert result.local_percentage >= 0.8


def test_tourist_attraction_gets_low_local_percentage_prior():
    result = BiasSignalEstimator().estimate_from_osm_tags("tourist_attraction", {})
    assert result.local_percentage <= 0.2


def test_fee_yes_increments_commercial_flags():
    with_fee = BiasSignalEstimator().estimate_from_osm_tags("museum", {"fee": "yes"})
    without_fee = BiasSignalEstimator().estimate_from_osm_tags("museum", {})
    assert with_fee.commercial_flags > without_fee.commercial_flags


def test_brand_tag_increments_commercial_flags():
    result = BiasSignalEstimator().estimate_from_osm_tags("cafe", {"brand": "Cafe Coffee Day"})
    baseline = BiasSignalEstimator().estimate_from_osm_tags("cafe", {})
    assert result.commercial_flags > baseline.commercial_flags


def test_media_mentions_always_zero_before_enrichment():
    result = BiasSignalEstimator().estimate_from_osm_tags("heritage_site", {})
    assert result.media_mentions == 0


def test_sponsored_indicator_never_auto_set():
    result = BiasSignalEstimator().estimate_from_osm_tags("shopping_mall", {"brand": "Big Chain"})
    assert result.sponsored_indicator is False


def test_unmapped_category_uses_default_priors():
    result = BiasSignalEstimator().estimate_from_osm_tags("some_unknown_category", {})
    assert result.local_percentage == 0.4
    assert result.tourist_popularity == 0.15


def test_refine_with_wikipedia_match_bumps_tourist_popularity():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("hidden_gem", {})
    before = signals.tourist_popularity
    estimator.refine_with_enrichment(signals, has_wikidata_match=False, has_wikipedia_match=True)
    assert signals.tourist_popularity > before


def test_refine_without_any_match_does_not_change_tourist_popularity():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("hidden_gem", {})
    before = signals.tourist_popularity
    estimator.refine_with_enrichment(signals, has_wikidata_match=False, has_wikipedia_match=False)
    assert signals.tourist_popularity == before


def test_refine_caps_tourist_popularity_at_one():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("tourist_attraction", {})
    signals.tourist_popularity = 0.95
    estimator.refine_with_enrichment(signals, has_wikidata_match=True, has_wikipedia_match=True)
    assert signals.tourist_popularity <= 1.0


def test_refine_sets_media_mentions_from_summary_length_short():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("heritage_site", {})
    estimator.refine_with_enrichment(signals, True, True, wiki_summary_length=100)
    assert signals.media_mentions == 1


def test_refine_sets_media_mentions_from_summary_length_long():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("heritage_site", {})
    estimator.refine_with_enrichment(signals, True, True, wiki_summary_length=2000)
    assert signals.media_mentions == 10


def test_refine_zero_summary_length_leaves_media_mentions_at_zero():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("heritage_site", {})
    estimator.refine_with_enrichment(signals, False, False, wiki_summary_length=0)
    assert signals.media_mentions == 0


def test_community_feedback_net_thumbs_up_raises_local_percentage():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("local_kitchen", {})
    before = signals.local_percentage
    estimator.refine_with_community_feedback(signals, thumbs_up=5, thumbs_down=0, times_removed=0, times_manually_added=0)
    assert signals.local_percentage > before


def test_community_feedback_net_thumbs_down_lowers_local_percentage():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("local_kitchen", {})
    before = signals.local_percentage
    estimator.refine_with_community_feedback(signals, thumbs_up=0, thumbs_down=5, times_removed=0, times_manually_added=0)
    assert signals.local_percentage < before


def test_community_feedback_local_percentage_delta_is_capped():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("local_kitchen", {})
    before = signals.local_percentage
    estimator.refine_with_community_feedback(signals, thumbs_up=1000, thumbs_down=0, times_removed=0, times_manually_added=0)
    assert signals.local_percentage <= before + 0.15 + 1e-9


def test_community_feedback_times_removed_lowers_tourist_popularity():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("heritage_site", {})
    before = signals.tourist_popularity
    estimator.refine_with_community_feedback(signals, thumbs_up=0, thumbs_down=0, times_removed=10, times_manually_added=0)
    assert signals.tourist_popularity < before
    assert signals.tourist_popularity >= before - 0.1 - 1e-9


def test_community_feedback_stays_within_bounds():
    estimator = BiasSignalEstimator()
    signals = estimator.estimate_from_osm_tags("local_kitchen", {})
    estimator.refine_with_community_feedback(signals, thumbs_up=10000, thumbs_down=0, times_removed=0, times_manually_added=10000)
    assert 0.0 <= signals.local_percentage <= 1.0
    assert 0.0 <= signals.tourist_popularity <= 1.0
