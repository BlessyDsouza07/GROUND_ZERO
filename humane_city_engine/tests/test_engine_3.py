"""
ENGINE 3 INTEGRATION TEST
Tests full bias-guard pipeline.
"""

from bias_guard.bias_auditor import audit_place


def run_engine_3_test():
    print("Running Engine 3 Integration Test...\n")

    # TEST CASE 1: Authentic place
    authentic_place = {
        "name": "Panambur Beach",
        "latitude": 12.9141,
        "longitude": 74.8037,
        "description": "Public beach managed by the city with regular visitors.",
        "sources": ["government", "community_map", "user_behavior"]
    }

    result_1 = audit_place(authentic_place)
    print("Test Case 1 – Authentic Place")
    print(result_1)
    print("-" * 50)

    # TEST CASE 2: Promotional content
    promotional_place = {
        "name": "Luxury Sea View Resort",
        "latitude": 12.91,
        "longitude": 74.80,
        "description": "Best luxury resort with amazing discounts and premium experience!",
        "sources": ["commercial"]
    }

    result_2 = audit_place(promotional_place)
    print("Test Case 2 – Promotional Place")
    print(result_2)
    print("-" * 50)

    # TEST CASE 3: Low consensus place
    weak_place = {
        "name": "Unknown Spot",
        "latitude": 12.90,
        "longitude": 74.79,
        "description": "Small local location.",
        "sources": ["user_behavior"]
    }

    result_3 = audit_place(weak_place)
    print("Test Case 3 – Low Consensus Place")
    print(result_3)
    print("-" * 50)


if __name__ == "__main__":
    run_engine_3_test()
