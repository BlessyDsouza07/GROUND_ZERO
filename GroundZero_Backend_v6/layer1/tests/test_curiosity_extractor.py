from layer1.application.curiosity_extractor import CuriosityExtractor


def test_empty_text_gives_empty_vector():
    vector = CuriosityExtractor().extract("")
    assert vector.weights == {}


def test_beach_and_photography_sentence():
    vector = CuriosityExtractor().extract(
        "I really want to see a beautiful sunset point and take some photos"
    )
    assert "viewpoint" in vector.weights
    top_categories = [c for c, _ in vector.top()]
    assert "viewpoint" in top_categories


def test_local_food_sentence_weights_local_kitchen_highest():
    vector = CuriosityExtractor().extract(
        "I want to try authentic local food, not the touristy restaurants"
    )
    assert vector.weights
    top_category, _ = vector.top(1)[0]
    assert top_category == "local_kitchen"


def test_weights_sum_to_one():
    vector = CuriosityExtractor().extract("beach heritage temple church coffee")
    total = sum(vector.weights.values())
    assert abs(total - 1.0) < 1e-6


def test_affinity_neutral_prior_when_no_curiosity_signal():
    extractor = CuriosityExtractor()
    vector = extractor.extract("hello world nothing relevant here")
    affinity = extractor.affinity_for_category(vector, "beach", [])
    assert affinity == 0.5


def test_affinity_high_for_matching_category():
    extractor = CuriosityExtractor()
    vector = extractor.extract("I love the beach and the coast, take me to the sea")
    affinity = extractor.affinity_for_category(vector, "beach", ["coastal"])
    assert affinity > 0.5
