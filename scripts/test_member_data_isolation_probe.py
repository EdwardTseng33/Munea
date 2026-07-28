#!/usr/bin/env python3
"""Tests for the non-production, read-only two-tenant isolation probe."""

from __future__ import annotations

import sys
import unittest
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from member_data_isolation_probe import ProbeConfig, run_probe, validate_targets


ACCOUNT_A = "11111111-1111-4111-8111-111111111111"
ACCOUNT_B = "22222222-2222-4222-8222-222222222222"
PERSON_A = "33333333-3333-4333-8333-333333333333"
PERSON_B = "44444444-4444-4444-8444-444444444444"
FAMILY_A = "55555555-5555-4555-8555-555555555555"
FAMILY_B = "66666666-6666-4666-8666-666666666666"
STAGING_REF = "abcdefghijklmnopqrst"


def config() -> ProbeConfig:
    return ProbeConfig(
        brain_url="https://munea-brain-staging-491603544409.asia-east1.run.app",
        supabase_url=f"https://{STAGING_REF}.supabase.co",
        staging_project_ref=STAGING_REF,
        publishable_key="staging-publishable",
        app_key="staging-app-key",
        tenant_a_token="token-a",
        tenant_b_token="token-b",
        removed_member_token="token-removed",
        tenant_a_account_id=ACCOUNT_A,
        tenant_b_account_id=ACCOUNT_B,
        tenant_a_person_id=PERSON_A,
        tenant_b_person_id=PERSON_B,
        tenant_a_family_id=FAMILY_A,
        tenant_b_family_id=FAMILY_B,
        exact_commit="a" * 40,
        evidence_reference="isolation-run-001",
        fixture_lifecycle_reference="staging-fixtures-001",
    )


class FakeTransport:
    def __init__(self, leak_cross_tenant: bool = False):
        self.leak_cross_tenant = leak_cross_tenant
        self.calls = []

    def __call__(self, method, url, headers, payload, timeout):
        self.calls.append((method, url, headers, payload, timeout))
        token = headers.get("authorization", "").removeprefix("Bearer ")
        parsed = urllib.parse.urlsplit(url)
        if parsed.path == "/version":
            return 200, {"revision": "brain-staging-00001-test"}
        if parsed.path == "/rest/v1/persons":
            person_filter = urllib.parse.parse_qs(parsed.query)["id"][0]
            person_id = person_filter.removeprefix("eq.")
            owner_token = "token-a" if person_id == PERSON_A else "token-b"
            if token == owner_token or self.leak_cross_tenant:
                return 200, [{"id": person_id, "account_id": "redacted"}]
            return 200, []
        if parsed.path == "/auth-status":
            return 200, {"ok": False, "auth": {"verified": False}}
        if token == "token-removed":
            return 403, {"ok": False, "error": {"code": "account_scope_missing"}}

        own_person = PERSON_A if token == "token-a" else PERSON_B
        own_family = FAMILY_A if token == "token-a" else FAMILY_B
        own_account = ACCOUNT_A if token == "token-a" else ACCOUNT_B
        if parsed.path == "/person-profile":
            requested = payload.get("personId")
            return (
                (200, {"ok": True, "profile": {}})
                if requested == own_person
                else (403, {"ok": False})
            )
        if parsed.path == "/family-members":
            return (
                (200, {"ok": True, "members": []})
                if payload.get("familyGroupId") == own_family
                else (403, {"ok": False})
            )
        if parsed.path == "/app-profile":
            return (
                (200, {"ok": True, "store": {}})
                if payload.get("accountId") == own_account
                else (403, {"ok": False})
            )
        raise AssertionError(f"unexpected probe request: {method} {url}")


class MemberDataIsolationProbeTests(unittest.TestCase):
    def test_complete_read_only_probe_passes_without_payloads_or_secrets(self) -> None:
        transport = FakeTransport()
        report = run_probe(
            config(),
            transport=transport,
            tested_at="2026-07-28T12:00:00Z",
        )
        self.assertEqual(report["result"], "pass")
        self.assertTrue(all(report["scenarios"].values()))
        self.assertTrue(report["scope"]["productionTargetsForbidden"])
        self.assertFalse(report["scope"]["writesAttempted"])
        serialized = str(report)
        for secret in ("token-a", "token-b", "staging-app-key", "staging-publishable"):
            self.assertNotIn(secret, serialized)
        for identifier in (ACCOUNT_A, ACCOUNT_B, PERSON_A, PERSON_B, FAMILY_A, FAMILY_B):
            self.assertNotIn(identifier, serialized)
        self.assertTrue(all(call[0] in ("GET", "POST") for call in transport.calls))
        self.assertTrue(all(
            call[0] == "GET" or urllib.parse.urlsplit(call[1]).path.startswith(
                ("/person-profile", "/family-members", "/app-profile", "/auth-status")
            )
            for call in transport.calls
        ))

    def test_cross_tenant_rls_leak_fails(self) -> None:
        report = run_probe(
            config(),
            transport=FakeTransport(leak_cross_tenant=True),
            tested_at="2026-07-28T12:00:00Z",
        )
        self.assertEqual(report["result"], "fail")
        self.assertFalse(report["scenarios"]["otherAccountPersonDeniedByRls"])

    def test_production_supabase_project_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "production or rollback"):
            validate_targets(
                config().brain_url,
                "https://fespbkdwafueyonppzwq.supabase.co",
                "fespbkdwafueyonppzwq",
            )

    def test_rollback_supabase_project_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "production or rollback"):
            validate_targets(
                config().brain_url,
                "https://uhmpmystjjdqqxlpsthc.supabase.co",
                "uhmpmystjjdqqxlpsthc",
            )

    def test_production_brain_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "staging"):
            validate_targets(
                "https://munea-brain-491603544409.asia-east1.run.app",
                config().supabase_url,
                STAGING_REF,
            )

    def test_supabase_project_ref_must_match_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly match"):
            validate_targets(
                config().brain_url,
                "https://zzzzzzzzzzzzzzzzzzzz.supabase.co",
                STAGING_REF,
            )


if __name__ == "__main__":
    unittest.main()
