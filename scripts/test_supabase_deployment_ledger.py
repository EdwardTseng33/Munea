#!/usr/bin/env python3
"""Negative governance tests for the Supabase deployment ledger."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_supabase_deployment_ledger import validate


class SupabaseDeploymentLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_directory.name)
        for relative_path in (
            "supabase/migration-manifest.json",
            "supabase/deployment-ledger.json",
            "docs/supabase/DEPLOYMENT-LEDGER.md",
            "docs/supabase/evidence/2026-07-18-local-target-mismatch.json",
            "docs/supabase/TOKYO-CANARY-2026-07-15.md",
            "docs/RELEASE-STATE.md",
            "STATUS.md",
        ):
            source = ROOT / relative_path
            target = self.repo_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @property
    def ledger_path(self) -> Path:
        return self.repo_root / "supabase/deployment-ledger.json"

    def read_ledger(self) -> dict:
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))

    def write_ledger(self, ledger: dict) -> None:
        self.ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def assert_has_error(self, needle: str) -> None:
        errors = validate(self.repo_root)
        self.assertTrue(any(needle in error for error in errors), errors)

    def test_canonical_ledger_passes(self) -> None:
        self.assertEqual(validate(self.repo_root), [])

    def test_missing_manifest_migration_fails(self) -> None:
        ledger = self.read_ledger()
        ledger["environments"][0]["migrations"].pop()
        self.write_ledger(ledger)
        self.assert_has_error("must cover every manifest migration exactly once")

    def test_checksum_drift_fails(self) -> None:
        ledger = self.read_ledger()
        ledger["environments"][0]["migrations"][0]["sha256"] = "0" * 64
        self.write_ledger(ledger)
        self.assert_has_error("deployment checksum drift")

    def test_unverified_head_fails(self) -> None:
        ledger = self.read_ledger()
        ledger["environments"][0]["verifiedHead"] = "019_pricing_plus100_pro200.sql"
        self.write_ledger(ledger)
        self.assert_has_error("verifiedHead must be null without a contiguous verified chain")

    def test_verified_state_requires_evidence(self) -> None:
        ledger = self.read_ledger()
        item = ledger["environments"][0]["migrations"][17]
        item["status"] = "verified"
        self.write_ledger(ledger)
        self.assert_has_error("verified evidence for 017_notification_settings.sql")
        self.assert_has_error("verified migration must bind a source commit")

    def test_cleanup_requires_approval_and_before_after_evidence(self) -> None:
        ledger = self.read_ledger()
        item = ledger["environments"][0]["migrations"][18]
        item.update({
            "status": "verified",
            "evidenceRef": "docs/RELEASE-STATE.md",
            "verifiedAt": "2026-07-18T00:00:00Z",
            "captureMethod": "approved-migration-run",
            "sourceCommit": "608e7e2",
        })
        self.write_ledger(ledger)
        self.assert_has_error("verified data-cleanup migration is missing approvalRef")
        self.assert_has_error("verified data-cleanup migration is missing backupEvidenceRef")
        self.assert_has_error("verified data-cleanup migration is missing preCheck")
        self.assert_has_error("verified data-cleanup migration is missing postCheck")

    def test_unknown_state_cannot_carry_verification_evidence(self) -> None:
        ledger = self.read_ledger()
        ledger["environments"][0]["migrations"][19]["verifiedAt"] = "2026-07-18T00:00:00Z"
        self.write_ledger(ledger)
        self.assert_has_error("unknown migration cannot carry verification evidence")

    def test_probe_cannot_be_verified_against_the_wrong_project(self) -> None:
        ledger = self.read_ledger()
        attempt = ledger["environments"][0]["latestProbeAttempt"]
        attempt["status"] = "verified"
        attempt["requestIssued"] = True
        self.write_ledger(ledger)
        self.assert_has_error("verified probe observation must match environment projectRef")


if __name__ == "__main__":
    unittest.main()
