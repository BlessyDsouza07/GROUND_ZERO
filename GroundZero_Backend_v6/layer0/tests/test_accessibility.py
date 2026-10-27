from layer0.application.accessibility import AccessibilityDetector


def test_wheelchair_yes():
    result = AccessibilityDetector().detect({"wheelchair": "yes"})
    assert result.wheelchair is True
    assert "no-wheelchair-access" not in result.tags


def test_wheelchair_no_flags_no_access():
    result = AccessibilityDetector().detect({"wheelchair": "no"})
    assert result.wheelchair is False
    assert "no-wheelchair-access" in result.tags


def test_stairs_only_via_highway_steps():
    result = AccessibilityDetector().detect({"highway": "steps"})
    assert "stairs-only" in result.tags


def test_uneven_terrain_via_surface():
    result = AccessibilityDetector().detect({"surface": "sand"})
    assert "uneven-terrain" in result.tags


def test_clean_place_has_no_blocking_tags():
    result = AccessibilityDetector().detect({"wheelchair": "yes", "surface": "paved"})
    assert result.tags == []


def test_blocks_for_wheelchair_flag():
    detector = AccessibilityDetector()
    blocking = detector.blocks_for(["wheelchair"])
    assert "stairs-only" in blocking
    assert "uneven-terrain" in blocking


def test_blocks_for_no_accessibility_flags_blocks_nothing():
    detector = AccessibilityDetector()
    assert detector.blocks_for([]) == set()
