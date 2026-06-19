"""Unit tests for injection routing — Lx × Sy × Depth → L1/L2/L3."""

import pytest


class TestRouteToL1:
    """L1 恒常注入: S1/S2 + KW."""

    def test_s1_kw_routes_to_l1(self):
        from src.core.route import route_to_l1
        assert route_to_l1(sy="S1", depth="KW") is True

    def test_s2_kw_routes_to_l1(self):
        from src.core.route import route_to_l1
        assert route_to_l1(sy="S2", depth="KW") is True

    def test_s3_kw_does_not_route_to_l1(self):
        from src.core.route import route_to_l1
        assert route_to_l1(sy="S3", depth="KW") is False

    def test_s1_kh_does_not_route_to_l1(self):
        from src.core.route import route_to_l1
        assert route_to_l1(sy="S1", depth="KH") is False

    def test_s1_ky_does_not_route_to_l1(self):
        from src.core.route import route_to_l1
        assert route_to_l1(sy="S1", depth="KY") is False


class TestRouteToL2:
    """L2 按需检索: S1/S2 + KH/KY."""

    def test_s1_kh_routes_to_l2(self):
        from src.core.route import route_to_l2
        assert route_to_l2(sy="S1", depth="KH") is True

    def test_s2_ky_routes_to_l2(self):
        from src.core.route import route_to_l2
        assert route_to_l2(sy="S2", depth="KY") is True

    def test_s1_kw_does_not_route_to_l2(self):
        from src.core.route import route_to_l2
        assert route_to_l2(sy="S1", depth="KW") is False


class TestRouteToL3:
    """L3 按需+专项保护: everything else."""

    def test_s3_kw_routes_to_l3(self):
        from src.core.route import route_to_l3
        assert route_to_l3(sy="S3", depth="KW") is True

    def test_s4_kh_routes_to_l3(self):
        from src.core.route import route_to_l3
        assert route_to_l3(sy="S4", depth="KH") is True

    def test_s5_ky_routes_to_l3(self):
        from src.core.route import route_to_l3
        assert route_to_l3(sy="S5", depth="KY") is True

    def test_l1_items_not_in_l3(self):
        from src.core.route import route_to_l1, route_to_l3
        # Items that route to L1 should not also route to L3
        assert route_to_l1(sy="S1", depth="KW") is True
        assert route_to_l3(sy="S1", depth="KW") is False


class TestTruncationStrategy:
    """L1+L2 > 4K tokens → truncation: S1 priority > S2 > drop L3."""

    def test_no_truncation_under_limit(self):
        from src.core.route import apply_truncation
        items = [
            {"sy": "S1", "depth": "KW", "tokens": 1000},
            {"sy": "S2", "depth": "KW", "tokens": 1000},
        ]
        result = apply_truncation(items, token_budget=4000)
        assert result["truncated"] is False
        assert len(result["included"]) == 2

    def test_truncation_drops_l3_first(self):
        from src.core.route import apply_truncation
        items = [
            {"sy": "S1", "depth": "KW", "tokens": 1500},
            {"sy": "S2", "depth": "KW", "tokens": 1500},
            {"sy": "S3", "depth": "KH", "tokens": 1500},
        ]
        result = apply_truncation(items, token_budget=4000)
        assert result["truncated"] is True
        assert len(result["included"]) == 2
        # L3 item dropped
        included_sys = {item["sy"] for item in result["included"]}
        assert included_sys == {"S1", "S2"}

    def test_s1_priority_over_s2(self):
        from src.core.route import apply_truncation
        items = [
            {"sy": "S1", "depth": "KW", "tokens": 2500},
            {"sy": "S1", "depth": "KW", "tokens": 1500},
            {"sy": "S2", "depth": "KW", "tokens": 1500},
        ]
        result = apply_truncation(items, token_budget=4000)
        # S1 items included first
        included_sys = [item["sy"] for item in result["included"]]
        assert included_sys[:2] == ["S1", "S1"]
