#!/usr/bin/env python3
import os
import sys
import unittest
import copy
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


def credit_store(included=0, purchased=0, period="2026-07"):
    return server.normalize_credits_store({
        "accountId": "11111111-1111-4111-8111-111111111111",
        "wallets": [
            {"id": "included-" + period, "type": "included_monthly", "period": period, "balance": included, "status": "active"},
            {"id": "purchased", "type": "purchased", "balance": purchased, "status": "active"},
        ],
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
             patch.object(server, "load_credits_store", return_value=credit_store()), \
             patch.object(server, "save_credits_store", side_effect=lambda data: data), \
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


class MonthlyCreditAllowanceTests(unittest.TestCase):
    def test_annual_plan_still_creates_one_month_at_a_time(self):
        billing = server.normalize_billing_store({
            "activePlan": "pro",
            "subscription": {
                "status": "active",
                "productId": "net.munea.app.pro.yearly",
                "originalTransactionId": "annual-1",
                "expiresAt": "2027-01-31T10:00:00Z",
            },
            "entitlements": {
                "monthlyCredits": 200,
                "monthlyCreditAnchorAt": "2026-01-31T10:00:00Z",
            },
        })
        details = server.monthly_allowance_details(billing, now=datetime(2026, 2, 15, tzinfo=timezone.utc))
        self.assertEqual(details["amount"], 200)
        self.assertIn("2026-01-31T10:00Z/2026-02-28T10:00Z", details["period"])
        march = server.monthly_allowance_details(billing, now=datetime(2026, 3, 15, tzinfo=timezone.utc))
        self.assertIn("2026-02-28T10:00Z/2026-03-31T10:00Z", march["period"])

    def test_monthly_allowance_resets_but_purchased_points_accumulate(self):
        state = {"store": credit_store(included=40, purchased=25, period="period-1")}

        def load():
            return copy.deepcopy(state["store"])

        def save(value):
            state["store"] = server.normalize_credits_store(copy.deepcopy(value))
            return copy.deepcopy(state["store"])

        with patch.object(server, "load_credits_store", side_effect=load), \
             patch.object(server, "save_credits_store", side_effect=save):
            next_period = server.credits_grant_response({
                "amount": 150,
                "walletType": "included_monthly",
                "period": "period-2",
                "expiresAt": "2099-09-01T00:00:00Z",
                "source": "included_monthly",
                "idempotencyKey": "allowance-period-2",
            })
            bought = server.credits_grant_response({
                "amount": 50,
                "walletType": "purchased",
                "source": "apple_iap",
                "idempotencyKey": "purchase-50",
            })

        self.assertEqual(next_period["walletSummary"]["includedMonthly"], 150)
        self.assertEqual(next_period["walletSummary"]["purchased"], 25)
        self.assertEqual(bought["walletSummary"]["purchased"], 75)
        old = next(w for w in state["store"]["wallets"] if w.get("period") == "period-1")
        self.assertEqual(old["status"], "closed")
        self.assertEqual(old["balance"], 0)

    def test_expired_subscription_drops_monthly_points_but_keeps_purchased(self):
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        credits = credit_store(included=90, purchased=40)
        saved_credits = {}
        with patch.object(server, "save_billing_store", side_effect=lambda data, reconcile=False: data), \
             patch.object(server, "load_credits_store", return_value=credits), \
             patch.object(server, "save_credits_store", side_effect=lambda data: saved_credits.update({"store": data}) or data), \
             patch.object(server.supabase_adapter, "make_adapter") as adapter, \
             patch.object(server, "append_audit_event"):
            adapter.return_value.remove_external_family_memberships_for_account_unscoped.return_value = 0
            server.reconcile_billing_expiry(paid_store(past))

        summary = server.credit_wallet_summary(saved_credits["store"])
        self.assertEqual(summary["includedMonthly"], 0)
        self.assertEqual(summary["purchased"], 40)

    def test_expired_wallet_is_never_counted_or_consumed(self):
        store = credit_store(included=100, purchased=8)
        store["wallets"][0]["expiresAt"] = "2020-01-01T00:00:00Z"
        self.assertEqual(server.credit_wallet_summary(store)["total"], 8)


if __name__ == "__main__":
    unittest.main()
