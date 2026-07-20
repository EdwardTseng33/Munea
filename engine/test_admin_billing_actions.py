#!/usr/bin/env python3
"""後台會員維運（手動發點數／改方案）驗證：權限擋得住、上限擋得住、稽核有寫入、方案真的改到。"""
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "admin-billing-actions-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"
PERSON_ID = "22222222-2222-4222-8222-222222222222"


def fake_target(account_name="測試家庭"):
    return {"accountName": account_name, "identity": {"accountId": ACCOUNT_ID, "personId": PERSON_ID}}


class AdminBillingRouteAuthTests(unittest.TestCase):
    def test_new_routes_do_not_require_end_user_auth_token(self):
        self.assertFalse(server.auth_required_for_request("/admin/credits/grant", {}))
        self.assertFalse(server.auth_required_for_request("/admin/subscription/set-plan", {}))

    def test_new_routes_are_scope_exempt(self):
        self.assertIn("/admin/credits/grant", server.SCOPE_EXEMPT_PATHS)
        self.assertIn("/admin/subscription/set-plan", server.SCOPE_EXEMPT_PATHS)


class AdminGrantCreditsTests(unittest.TestCase):
    def test_missing_account_id_rejected(self):
        result = server.admin_grant_credits_response({"amount": 10})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_id_required")

    def test_invalid_amount_rejected(self):
        result = server.admin_grant_credits_response({"accountId": ACCOUNT_ID, "amount": 0})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_credit_amount")

    def test_amount_over_admin_limit_rejected(self):
        result = server.admin_grant_credits_response({"accountId": ACCOUNT_ID, "amount": 50000})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "amount_exceeds_admin_limit")
        self.assertEqual(result["error"]["limit"], 2000)

    def test_amount_at_limit_is_allowed_boundary(self):
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_credits_store", return_value=server.default_credits_store()), \
             patch.object(server, "save_credits_store", side_effect=lambda store: store), \
             patch.object(server, "append_audit_event") as audit:
            result = server.admin_grant_credits_response({"accountId": ACCOUNT_ID, "amount": 2000})
        self.assertTrue(result["ok"], result)
        audit.assert_called_once()

    def test_unknown_account_rejected(self):
        with patch.object(server, "_resolve_admin_target_identity", return_value=None):
            result = server.admin_grant_credits_response({"accountId": "does-not-exist", "amount": 10})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_not_found")

    def test_happy_path_grants_into_purchased_wallet_and_writes_audit(self):
        state = {"credits": server.normalize_credits_store({
            "accountId": ACCOUNT_ID,
            "wallets": [
                {"id": "included", "type": "included_monthly", "period": "2026-07", "balance": 50, "status": "active"},
                {"id": "purchased", "type": "purchased", "balance": 10, "status": "active"},
            ],
        })}

        def load():
            return state["credits"]

        def save(store):
            state["credits"] = server.normalize_credits_store(store)
            return state["credits"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target("陳先生家")), \
             patch.object(server, "load_credits_store", side_effect=load), \
             patch.object(server, "save_credits_store", side_effect=save), \
             patch.object(server, "append_audit_event") as audit:
            result = server.admin_grant_credits_response({
                "accountId": ACCOUNT_ID, "amount": 100, "reason": "客服補償",
            }, headers={"X-Munea-Admin-Token": "t"})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["accountId"], ACCOUNT_ID)
        self.assertEqual(result["accountName"], "陳先生家")
        purchased = next(w for w in state["credits"]["wallets"] if w["type"] == "purchased")
        self.assertEqual(purchased["balance"], 110)
        included = next(w for w in state["credits"]["wallets"] if w["type"] == "included_monthly")
        self.assertEqual(included["balance"], 50)
        audit.assert_called_once()
        event = audit.call_args.args[0]
        self.assertEqual(event["eventType"], "admin_credits_granted")
        self.assertEqual(event["accountId"], ACCOUNT_ID)
        self.assertEqual(event["details"]["amount"], 100)
        self.assertEqual(event["details"]["balanceBefore"], 60)
        self.assertEqual(event["details"]["balanceAfter"], 160)

    def test_identity_is_scoped_during_call_and_reset_after(self):
        seen = {}

        def load():
            seen["identity_during_call"] = server.REQUEST_DATA_IDENTITY.get()
            return server.default_credits_store()

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_credits_store", side_effect=load), \
             patch.object(server, "save_credits_store", side_effect=lambda store: store), \
             patch.object(server, "append_audit_event"):
            self.assertIsNone(server.REQUEST_DATA_IDENTITY.get())
            server.admin_grant_credits_response({"accountId": ACCOUNT_ID, "amount": 5})
            self.assertIsNone(server.REQUEST_DATA_IDENTITY.get())
        self.assertEqual(seen["identity_during_call"], {"accountId": ACCOUNT_ID, "personId": PERSON_ID})


class AdminSetPlanTests(unittest.TestCase):
    def test_missing_account_id_rejected(self):
        result = server.admin_set_plan_response({"plan": "pro"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_id_required")

    def test_invalid_plan_rejected(self):
        result = server.admin_set_plan_response({"accountId": ACCOUNT_ID, "plan": "enterprise"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_plan")

    def test_unknown_account_rejected(self):
        with patch.object(server, "_resolve_admin_target_identity", return_value=None):
            result = server.admin_set_plan_response({"accountId": "nope", "plan": "pro"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_not_found")

    def test_upgrade_to_pro_grants_monthly_allowance_and_entitlements(self):
        billing_state = {"store": server.normalize_billing_store({"accountId": ACCOUNT_ID})}
        credits_state = {"store": server.default_credits_store()}

        def load_billing():
            return server.normalize_billing_store(billing_state["store"])

        def save_billing(data, reconcile=True):
            billing_state["store"] = server.normalize_billing_store(data)
            return billing_state["store"]

        def load_credits():
            return credits_state["store"]

        def save_credits(data):
            credits_state["store"] = server.normalize_credits_store(data)
            return credits_state["store"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target("王媽媽家")), \
             patch.object(server, "load_billing_store", side_effect=load_billing), \
             patch.object(server, "save_billing_store", side_effect=save_billing), \
             patch.object(server, "load_credits_store", side_effect=load_credits), \
             patch.object(server, "save_credits_store", side_effect=save_credits), \
             patch.object(server, "append_audit_event") as audit:
            result = server.admin_set_plan_response({"accountId": ACCOUNT_ID, "plan": "pro"})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["previousPlan"], "free")
        self.assertEqual(result["activePlan"], "pro")
        self.assertEqual(billing_state["store"]["activePlan"], "pro")
        self.assertEqual(billing_state["store"]["entitlements"]["familyMembersMax"], 12)
        self.assertEqual(billing_state["store"]["entitlements"]["monthlyCredits"], 200)
        self.assertEqual(billing_state["store"]["provider"], "manual-admin-grant")
        # 新方案的當月贈點錢包要是「有效」的那個；舊的每月贈點錢包（若有）已被關閉、不能混進來算。
        self.assertEqual(server.credit_wallet_summary(credits_state["store"])["includedMonthly"], 200)
        audit.assert_called_once()
        event = audit.call_args.args[0]
        self.assertEqual(event["eventType"], "admin_plan_changed")
        self.assertEqual(event["details"]["previousPlan"], "free")
        self.assertEqual(event["details"]["newPlan"], "pro")

    def test_downgrade_to_free_closes_monthly_wallet_but_keeps_purchased(self):
        billing_state = {"store": server.normalize_billing_store({
            "accountId": ACCOUNT_ID,
            "activePlan": "plus",
            "provider": "manual-admin-grant",
            "subscription": {"status": "active"},
            "entitlements": {"familyCircleInvite": True, "familyCircleJoin": True, "familyMembersMax": 4, "monthlyCredits": 100},
        })}
        credits_state = {"store": server.normalize_credits_store({
            "accountId": ACCOUNT_ID,
            "wallets": [
                {"id": "included", "type": "included_monthly", "period": "2026-07", "balance": 80, "status": "active"},
                {"id": "purchased", "type": "purchased", "balance": 30, "status": "active"},
            ],
        })}

        def load_billing():
            return server.normalize_billing_store(billing_state["store"])

        def save_billing(data, reconcile=True):
            billing_state["store"] = server.normalize_billing_store(data)
            return billing_state["store"]

        def load_credits():
            return credits_state["store"]

        def save_credits(data):
            credits_state["store"] = server.normalize_credits_store(data)
            return credits_state["store"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_billing_store", side_effect=load_billing), \
             patch.object(server, "save_billing_store", side_effect=save_billing), \
             patch.object(server, "load_credits_store", side_effect=load_credits), \
             patch.object(server, "save_credits_store", side_effect=save_credits), \
             patch.object(server, "append_audit_event"):
            result = server.admin_set_plan_response({"accountId": ACCOUNT_ID, "plan": "free"})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["previousPlan"], "plus")
        self.assertEqual(result["activePlan"], "free")
        self.assertEqual(billing_state["store"]["activePlan"], "free")
        self.assertFalse(billing_state["store"]["entitlements"]["familyCircleInvite"])
        included = next(w for w in credits_state["store"]["wallets"] if w["type"] == "included_monthly")
        self.assertEqual(included["status"], "closed")
        self.assertEqual(included["balance"], 0)
        purchased = next(w for w in credits_state["store"]["wallets"] if w["type"] == "purchased")
        self.assertEqual(purchased["balance"], 30)

    def test_does_not_touch_real_apple_provider_when_upgrading(self):
        billing_state = {"store": server.normalize_billing_store({
            "accountId": ACCOUNT_ID,
            "activePlan": "plus",
            "provider": "apple_storekit2",
            "subscription": {"status": "active", "productId": "net.munea.app.plus.monthly"},
        })}

        def load_billing():
            return server.normalize_billing_store(billing_state["store"])

        def save_billing(data, reconcile=True):
            billing_state["store"] = server.normalize_billing_store(data)
            return billing_state["store"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_billing_store", side_effect=load_billing), \
             patch.object(server, "save_billing_store", side_effect=save_billing), \
             patch.object(server, "load_credits_store", return_value=server.default_credits_store()), \
             patch.object(server, "save_credits_store", side_effect=lambda d: d), \
             patch.object(server, "append_audit_event"):
            server.admin_set_plan_response({"accountId": ACCOUNT_ID, "plan": "pro"})

        self.assertEqual(billing_state["store"]["provider"], "apple_storekit2")


if __name__ == "__main__":
    unittest.main()
