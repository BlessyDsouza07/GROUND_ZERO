"""
Tests the Bias Audit formula against the blueprint's own worked examples
where possible, and general correctness properties otherwise. Note: the
blueprint's Table 10 worked examples use bias_index values (0.25, 0.85,
0.05) as GIVEN inputs to the Personal Fit Score formula — it does not show
how those specific numbers were derived from raw signals. So these tests
verify our formula's *properties* (a high local_percentage + low media
mentions must land in the "authentic" band; a sponsored, heavily-mentioned,
mostly-tourist place must land "commercialised") rather than asserting we
reproduce Table 10's exact numbers from invented raw inputs.
"""
from layer0.application.bias_audit import BiasAuditService
from layer0.domain.entities import BiasSignals, Grade


def test_high_local_percentage_low_mentions_is_authentic():
    service = BiasAuditService()
    signals = BiasSignals(
        media_mentions=2, local_percentage=0.95, commercial_flags=0,
        tourist_popularity=0.05, sponsored_indicator=False,
    )
    breakdown = service.compute(signals)
    assert breakdown.bias_index < 0.3
    assert service.grade_for(breakdown.bias_index) == Grade.AUTHENTIC


def test_sponsored_heavily_mentioned_tourist_trap_is_commercialised():
    service = BiasAuditService()
    signals = BiasSignals(
        media_mentions=400, local_percentage=0.05, commercial_flags=8,
        tourist_popularity=0.95, sponsored_indicator=True,
    )
    breakdown = service.compute(signals)
    assert breakdown.bias_index >= 0.6
    assert service.grade_for(breakdown.bias_index) == Grade.COMMERCIALISED


def test_bias_index_always_in_unit_interval():
    service = BiasAuditService()
    extreme = BiasSignals(
        media_mentions=1_000_000, local_percentage=0.0, commercial_flags=1000,
        tourist_popularity=1.0, sponsored_indicator=True,
    )
    breakdown = service.compute(extreme)
    assert 0.0 <= breakdown.bias_index <= 1.0

    zero = BiasSignals(media_mentions=0, local_percentage=1.0, commercial_flags=0, tourist_popularity=0.0)
    breakdown_zero = service.compute(zero)
    assert 0.0 <= breakdown_zero.bias_index <= 1.0
    assert breakdown_zero.bias_index < breakdown.bias_index


def test_more_media_mentions_never_decreases_bias_index_all_else_equal():
    service = BiasAuditService()
    low = service.compute(BiasSignals(media_mentions=5, local_percentage=0.5))
    high = service.compute(BiasSignals(media_mentions=100, local_percentage=0.5))
    assert high.bias_index >= low.bias_index


def test_grade_boundaries():
    service = BiasAuditService()
    assert service.grade_for(0.0) == Grade.AUTHENTIC
    assert service.grade_for(0.29) == Grade.AUTHENTIC
    assert service.grade_for(0.3) == Grade.BALANCED
    assert service.grade_for(0.59) == Grade.BALANCED
    assert service.grade_for(0.6) == Grade.COMMERCIALISED
    assert service.grade_for(1.0) == Grade.COMMERCIALISED
