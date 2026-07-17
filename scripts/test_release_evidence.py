#!/usr/bin/env python3
"""Regression tests for secret-free runtime release evidence."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_evidence import TARGETS_PATH, capture_target, validate_evidence


class ReleaseEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.targets = json.loads((ROOT / TARGETS_PATH).read_text(encoding="utf-8"))
        cls.latest = json.loads((ROOT / "docs/RELEASE-EVIDENCE-LATEST.json").read_text(encoding="utf-8"))
        cls.source_version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]

    def validate(self, document: dict, **kwargs: object) -> list[str]:
        return validate_evidence(document, self.targets, source_version=self.source_version, **kwargs)

    def test_committed_evidence_schema_passes(self) -> None:
        self.assertEqual(self.validate(self.latest), [])

    def test_strict_freshness_rejects_stale_evidence(self) -> None:
        captured = datetime.fromisoformat(self.latest["capturedAt"].replace("Z", "+00:00"))
        errors = self.validate(self.latest, max_age_hours=24, now=captured + timedelta(hours=25))
        self.assertTrue(any("older than 24 hours" in error for error in errors), errors)

    def test_service_identity_tamper_fails(self) -> None:
        document = copy.deepcopy(self.latest)
        document["results"][0]["observed"]["service"] = "wrong-service"
        errors = self.validate(document)
        self.assertTrue(any("service identity drifted" in error for error in errors), errors)

    def test_missing_target_result_fails(self) -> None:
        document = copy.deepcopy(self.latest)
        document["results"].pop()
        errors = self.validate(document)
        self.assertTrue(any("result is missing" in error for error in errors), errors)

    def test_capture_service_version_keeps_only_release_identity(self) -> None:
        target = self.targets["targets"][0]
        body = json.dumps(
            {
                "ok": True,
                "release": {
                    "schema": "munea.service-release.v1",
                    "service": target["expectedService"],
                    "version": "1.2.3",
                    "commit": "a" * 40,
                    "revision": "rev-1",
                    "environment": target["expectedEnvironment"],
                    "secret": "must-not-survive",
                },
            }
        ).encode()
        result = capture_target(target, fetcher=lambda _url, _timeout: (200, {}, body))
        self.assertTrue(result["ok"])
        self.assertNotIn("secret", result["observed"])

    def test_capture_admin_shell_hashes_body_and_checks_headers(self) -> None:
        target = self.targets["targets"][-1]
        body = '<html>Munea<div id="pageRoot"></div><script src/admin.js></script></html>'.encode()
        headers = {name: value for name, value in target["requiredHeaders"].items()}
        result = capture_target(target, fetcher=lambda _url, _timeout: (200, headers, body))
        self.assertTrue(result["ok"])
        self.assertNotIn("body", result["observed"])
        self.assertEqual(len(result["observed"]["bodySha256"]), 64)


if __name__ == "__main__":
    unittest.main()
