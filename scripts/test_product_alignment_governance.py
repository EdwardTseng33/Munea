#!/usr/bin/env python3
"""Focused regression tests for product-alignment governance."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_product_alignment import _taipei_today, validate


COPIED_PATHS = [
    "package.json",
    "package-lock.json",
    "web/src/version.js",
    "web/src/app.js",
    "ios/App/App.xcodeproj/project.pbxproj",
    "engine/apple_store.py",
    "supabase/sql/019_pricing_plus100_pro200.sql",
    "supabase/migration-manifest.json",
    "supabase/deployment-ledger.json",
    "docs/CURRENT-AUTHORITIES.json",
    "docs/API-CONTRACT-INVENTORY.json",
    "docs/ADMIN-DATA-QUALITY-CONTRACT.md",
    "docs/RELEASE-EVIDENCE-TARGETS.json",
    "docs/RELEASE-EVIDENCE-LATEST.json",
    "docs/00-總綱-從這裡開始.md",
    "docs/SPEC-沐寧-v1-2026-06-28.md",
    "docs/BILLING-CREDITS-ENTITLEMENT-v1.md",
    "docs/PRODUCT-QUALITY-CONFIDENCE.md",
    "docs/RELEASE-STATE.md",
    "docs/PRODUCT-ALIGNMENT-REGISTER.md",
    "docs/AI-SERVICE-DESIGN-v1.md",
    "docs/BACKEND-ARCHITECTURE-v1.md",
    "deploy/cloudrun/SERVICE-TOPOLOGY.md",
    "docs/協作看板-雙AI分工.md",
    "docs/HEALTH-90-SCORECARD-2026-07-16.md",
    "docs/APP-STORE-PRODUCTION-READINESS.md",
]


class ProductAlignmentGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_directory.name)
        for relative_path in COPIED_PATHS:
            source = ROOT / relative_path
            target = self.repo_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def read_json(self, relative_path: str) -> dict:
        return json.loads((self.repo_root / relative_path).read_text(encoding="utf-8"))

    def write_json(self, relative_path: str, value: dict) -> None:
        (self.repo_root / relative_path).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def replace(self, relative_path: str, before: str, after: str) -> None:
        path = self.repo_root / relative_path
        source = path.read_text(encoding="utf-8")
        self.assertIn(before, source)
        path.write_text(source.replace(before, after, 1), encoding="utf-8")

    def assert_has_error(self, needle: str) -> None:
        errors = validate(self.repo_root)
        self.assertTrue(any(needle in error for error in errors), errors)

    def test_canonical_alignment_passes(self) -> None:
        self.assertEqual(validate(self.repo_root), [])

    def test_duplicate_authority_topic_fails(self) -> None:
        authority = self.read_json("docs/CURRENT-AUTHORITIES.json")
        authority["authorities"].append(dict(authority["authorities"][0]))
        self.write_json("docs/CURRENT-AUTHORITIES.json", authority)
        self.assert_has_error("authority topic is duplicated: docs-entry")

    def test_future_authority_date_fails_in_product_timezone(self) -> None:
        authority = self.read_json("docs/CURRENT-AUTHORITIES.json")
        authority["updated"] = (_taipei_today() + timedelta(days=1)).isoformat()
        self.write_json("docs/CURRENT-AUTHORITIES.json", authority)
        self.assert_has_error("authority index updated date cannot be in the future")

    def test_api_contract_authority_cannot_drift(self) -> None:
        authority = self.read_json("docs/CURRENT-AUTHORITIES.json")
        for entry in authority["authorities"]:
            if entry["topic"] == "api-contracts":
                entry["path"] = "docs/BACKEND-ARCHITECTURE-v1.md"
        self.write_json("docs/CURRENT-AUTHORITIES.json", authority)
        self.assert_has_error("API contracts must be owned by API-CONTRACT-INVENTORY.json")

    def test_admin_data_quality_authority_cannot_drift(self) -> None:
        authority = self.read_json("docs/CURRENT-AUTHORITIES.json")
        for entry in authority["authorities"]:
            if entry["topic"] == "admin-data-quality":
                entry["path"] = "docs/BACKEND-ARCHITECTURE-v1.md"
        self.write_json("docs/CURRENT-AUTHORITIES.json", authority)
        self.assert_has_error("Admin data quality must be owned by ADMIN-DATA-QUALITY-CONTRACT.md")

    def test_database_deployment_ledger_authority_cannot_drift(self) -> None:
        authority = self.read_json("docs/CURRENT-AUTHORITIES.json")
        for entry in authority["authorities"]:
            if entry["topic"] == "database-deployment-ledger":
                entry["path"] = "docs/RELEASE-STATE.md"
        self.write_json("docs/CURRENT-AUTHORITIES.json", authority)
        self.assert_has_error("Database deployment state must be owned by supabase/deployment-ledger.json")

    def test_stale_release_state_source_fails(self) -> None:
        self.replace(
            "docs/RELEASE-STATE.md",
            "| Latest source | `1.0.41 (Build 48)`",
            "| Latest source | `1.0.40 (Build 47)`",
        )
        self.assert_has_error("current source marker is stale in docs/RELEASE-STATE.md")

    def test_historical_document_without_marker_fails(self) -> None:
        self.replace(
            "docs/HEALTH-90-SCORECARD-2026-07-16.md",
            "Historical snapshot",
            "Archived evidence",
        )
        self.assert_has_error("historical document lacks a Historical snapshot marker")

    def test_backend_pricing_drift_fails(self) -> None:
        self.replace(
            "engine/apple_store.py",
            '"net.munea.app.points.200": {"kind": "points", "points": 100}',
            '"net.munea.app.points.200": {"kind": "points", "points": 150}',
        )
        self.assert_has_error("PRODUCTS does not match the approved pricing contract")

    def test_ai_provider_reality_cannot_point_to_design_intent(self) -> None:
        authority = self.read_json("docs/CURRENT-AUTHORITIES.json")
        for entry in authority["authorities"]:
            if entry["topic"] == "ai-provider-reality":
                entry["path"] = "docs/AI-SERVICE-DESIGN-v1.md"
        self.write_json("docs/CURRENT-AUTHORITIES.json", authority)
        self.assert_has_error("AI provider reality must be owned by PRODUCT-ALIGNMENT-REGISTER.md")


if __name__ == "__main__":
    unittest.main()
