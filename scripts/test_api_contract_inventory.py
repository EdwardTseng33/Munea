#!/usr/bin/env python3
"""Negative governance tests for the source-derived API inventory."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from api_contract_inventory import INVENTORY_PATH, ROOT, Route, extract_routes, validate_inventory


class ApiContractInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = json.loads((ROOT / INVENTORY_PATH).read_text(encoding="utf-8"))
        cls.routes = extract_routes(ROOT)

    def assert_error(self, errors: list[str], marker: str) -> None:
        self.assertTrue(any(marker in error for error in errors), f"missing {marker!r} in {errors}")

    def route_entry(self, inventory: dict, surface: str, method: str, path: str) -> dict:
        return next(
            entry for entry in inventory["routes"]
            if (entry["surface"], entry["method"], entry["path"]) == (surface, method, path)
        )

    def test_committed_inventory_matches_source(self) -> None:
        self.assertEqual(validate_inventory(self.inventory, ROOT, self.routes), [])
        # 2026-07-20 營運後台擴充 4 支指標接口 ＋ 企業席次 13 支管理接口
        self.assertEqual(self.inventory["routeCounts"], {"brain": 84, "gateway": 23, "voice": 4})
        self.assertIn(Route("voice", "WS", "/"), self.routes)

    def test_new_source_route_must_be_registered(self) -> None:
        routes = set(self.routes)
        routes.add(Route("brain", "POST", "/governance-fixture"))
        errors = validate_inventory(self.inventory, ROOT, routes)
        self.assert_error(errors, "source route is not registered: brain POST /governance-fixture")

    def test_deleted_source_route_cannot_remain_in_inventory(self) -> None:
        routes = {route for route in self.routes if route != Route("brain", "POST", "/chat")}
        errors = validate_inventory(self.inventory, ROOT, routes)
        self.assert_error(errors, "inventory route no longer exists: brain POST /chat")

    def test_auth_downgrade_is_blocked(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        entry = self.route_entry(inventory, "gateway", "POST", "/v1/internal/reap")
        entry["auth"] = "public"
        errors = validate_inventory(inventory, ROOT, self.routes)
        self.assert_error(errors, "auth downgrade for gateway POST /v1/internal/reap")

    def test_duplicate_route_is_blocked(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["routes"].append(copy.deepcopy(inventory["routes"][0]))
        errors = validate_inventory(inventory, ROOT, self.routes)
        self.assert_error(errors, "duplicate route:")

    def test_critical_route_requires_test_evidence(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        entry = self.route_entry(inventory, "gateway", "POST", "/v1/calls")
        entry["tests"] = []
        errors = validate_inventory(inventory, ROOT, self.routes)
        self.assert_error(errors, "critical route has no test: gateway POST /v1/calls")

    def test_test_evidence_must_point_to_a_repo_file(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        entry = self.route_entry(inventory, "gateway", "POST", "/v1/calls")
        entry["tests"] = ["scripts/does-not-exist.py"]
        errors = validate_inventory(inventory, ROOT, self.routes)
        self.assert_error(errors, "route test target does not exist for gateway POST /v1/calls")


if __name__ == "__main__":
    unittest.main()
