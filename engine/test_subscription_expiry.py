#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "subscription-expiry-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


def paid_store(expires_at):
    return server.normalize_billing_store({
        "accountId": "11111111-1111-4111-8111-111111111111",
        "activePlan": "plus",
        "serverVerificationRequired": False,
        "subscription": {"status": "active", "expiresAt": expires_at, "willRenew": False},
        "entitlements": {"familyCircleInvite": True, "familyCircleJoin": True, "familyMembersMax": 4},
    })


class SubscriptionExpiryTests(unittest.TestCase):
    def test_cancelled_but_not_expired_keeps_current_entitlements(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.assertIsNone(server.subscription_expiry_reason(paid_store(future)))

    def test_expired_subscription_becomes_free_and_loses_family_permissions(self):
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        expired = server.expire_billing_store(paid_store(past), "expired")
        self.assertEqual(expired["activePlan"], "free")
        self.assertEqual(expired["subscription"]["status"], "expired")
        self.assertFalse(expired["entitlements"]["familyCircleInvite"])
        self.assertFalse(expired["entitlements"]["familyCircleJoin"])
        self.assertEqual(expired["entitlements"]["familyMembersMax"], 1)

    def test_reconciliation_removes_external_family_memberships(self):
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        store = paid_store(past)
        with patch.object(server, "save_billing_store", side_effect=lambda data, reconcile=False: data), \
             patch.object(server.supabase_adapter, "make_adapter") as adapter, \
             patch.object(server, "append_audit_event") as audit:
            adapter.return_value.remove_external_family_memberships_for_account_unscoped.return_value = 2
            result = server.reconcile_billing_expiry(store)
        self.assertEqual(result["activePlan"], "free")
        adapter.return_value.remove_external_family_memberships_for_account_unscoped.assert_called_once_with(store["accountId"])
        self.assertEqual(audit.call_args.args[0]["details"]["externalFamilyMembershipsRemoved"], 2)

    def test_expired_member_cannot_read_another_accounts_family_state_before_cleanup(self):
        class ExternalCircleBackend:
            account_id = "11111111-1111-4111-8111-111111111111"

            def enabled(self):
                return True

            def family_group_account_id(self, _family_group_id):
                return "22222222-2222-4222-8222-222222222222"

        free = server.default_billing_store()
        with patch.object(server, "data_backend", return_value=ExternalCircleBackend()), \
             patch.object(server, "load_billing_store", return_value=free):
            result = server.family_state_response({"action": "load", "familyGroupId": "33333333-3333-4333-8333-333333333333"})
        self.assertEqual(result["error"], "family_access_expired")


if __name__ == "__main__":
    unittest.main()
