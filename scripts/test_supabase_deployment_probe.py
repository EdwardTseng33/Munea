#!/usr/bin/env python3
"""Contract tests for the secret-safe Tokyo deployment probe."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import supabase_deployment_probe as probe


class FakeResponse:
    def __init__(self, payload, content_range=None):
        self.payload = json.dumps(payload).encode("utf-8")
        self.headers = {"Content-Range": content_range} if content_range else {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class SupabaseDeploymentProbeTests(unittest.TestCase):
    def env(self, project_ref=probe.TOKYO_PROJECT_REF):
        return mock.patch.dict(os.environ, {
            "SUPABASE_URL": f"https://{project_ref}.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "MUNEA_SKIP_ENV_LOCAL": "1",
            "MUNEA_RELEASE_COMMIT": "608e7e2",
        }, clear=False)

    def test_target_project_mismatch_fails_without_network(self):
        with self.env("aaaaaaaaaaaaaaaaaaaa"), mock.patch.object(probe.urllib.request, "urlopen") as urlopen:
            result = probe.probe()
        self.assertEqual(result["error"], "target_project_mismatch")
        self.assertFalse(result["requestIssued"])
        urlopen.assert_not_called()

    def test_probe_uses_get_only_and_returns_no_secrets(self):
        responses = [
            FakeResponse([]),
            FakeResponse([], "*/0"),
            FakeResponse([{
                "version": 4,
                "active": True,
                "policy": {"plus": {"monthlyPoints": 100}, "pro": {"monthlyPoints": 200}},
            }]),
        ]
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return responses.pop(0)

        with self.env(), mock.patch.object(probe.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = probe.probe()
        self.assertTrue(result["ok"])
        self.assertTrue(result["readOnly"])
        self.assertTrue(result["requestIssued"])
        self.assertFalse(result["ledgerPromotionAllowed"])
        self.assertIn("018_requires_approved_backup_and_full_before_after_evidence", result["promotionBlockers"])
        self.assertEqual(result["checks"]["018_strip_medication_photos"]["photoKeyRows"], 0)
        self.assertTrue(all(request.method == "GET" for request in requests))
        self.assertNotIn("test-service-key", json.dumps(result))

    def test_wrong_policy_does_not_pass(self):
        responses = [
            FakeResponse([]),
            FakeResponse([], "*/0"),
            FakeResponse([{
                "version": 4,
                "active": True,
                "policy": {"plus": {"monthlyPoints": 150}, "pro": {"monthlyPoints": 300}},
            }]),
        ]
        with self.env(), mock.patch.object(probe.urllib.request, "urlopen", side_effect=responses):
            result = probe.probe()
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["019_pricing_plus100_pro200"]["policyV4Matches"])

    def test_http_error_is_sanitized(self):
        error = probe.urllib.error.HTTPError("https://redacted", 403, "forbidden", {}, None)
        with self.env(), mock.patch.object(probe.urllib.request, "urlopen", side_effect=error):
            result = probe.probe()
        serialized = json.dumps(result)
        self.assertIn("http_403", serialized)
        self.assertNotIn("test-service-key", serialized)


if __name__ == "__main__":
    unittest.main()
