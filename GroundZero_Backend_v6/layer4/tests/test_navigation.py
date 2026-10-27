import asyncio

from layer4.navigation import _dfs_priority_order, _fallback_route, dfs_shortest_path, haversine_m


def test_priority_dfs_preserves_queue_order():
    points = [{"place_id": "a"}, {"place_id": "b"}, {"place_id": "c"}]
    assert [p["place_id"] for p in _dfs_priority_order(points)] == ["a", "b", "c"]


def test_fallback_route_has_legs_and_geometry():
    route = _fallback_route([(12.90, 74.85), (12.91, 74.86)])
    assert route["routed"] is False
    assert len(route["legs"]) == 1
    assert route["distance"] > 0
    assert len(route["geometry"]) == 2


def test_haversine_zero():
    assert haversine_m((12.9, 74.85), (12.9, 74.85)) == 0


def test_dfs_shortest_path_finds_minimum_weight_route():
    graph = {"s": [("a", 5), ("b", 2)], "a": [("g", 5)], "b": [("g", 2)], "g": []}
    cost, path = dfs_shortest_path(graph, "s", "g")
    assert cost == 4 and path == ["s", "b", "g"]
