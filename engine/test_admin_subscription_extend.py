#!/usr/bin/env python3
"""後台延長訂閱天數驗證：權限擋得住、上限擋得住、過期/無到期日從今天起算、
稽核有寫入、Apple 已驗證訂閱的 provider/productId 不被本功能覆蓋。"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "admin-subscription-extend-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"
PERSON_ID = "22222222-2222-4222-8222-222222222222"


def fake_target(account_name="測試家庭"):
    return {"accountName": account_name, "identity": {"accountId": ACCOUNT_ID, "personId": PERSON_ID}}


class AdminBillingRouteAuthTests(unittest.TestCase):
    def test_new_route_does_not_require_end_user_auth_token(self):
        self.assertFalse(server.auth_required_for_request("/admin/subscription/extend-days", {}))

    def test_new_route_is_scope_exempt(self):
        self.assertIn("/admin/subscription/extend-days", server.SCOPE_EXEMPT_PATHS)


class ValidationTests(unittest.TestCase):
    def test_missing_account_id_rejected(self):
        result = server.admin_extend_subscription_response({"days": 30})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_id_required")

    def test_days_required_when_not_dry_run(self):
        result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "days_required")

    def test_days_zero_rejected(self):
        # 0 落在「小於等於 0」的範圍檢查，回 days_out_of_range（不是 days_required）。
        result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 0})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "days_out_of_range")

    def test_days_missing_entirely_is_days_required_not_out_of_range(self):
        result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": None})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "days_required")

    def test_days_over_limit_rejected(self):
        result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 9999})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "days_out_of_range")
        self.assertEqual(result["error"]["limit"], 365)

    def test_days_at_limit_boundary_passes_validation(self):
        with patch.object(server, "_resolve_admin_target_identity", return_value=None):
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 365})
        # rejected for account_not_found, not for the days value itself
        self.assertEqual(result["error"]["code"], "account_not_found")

    def test_invalid_days_type_rejected(self):
        result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": "abc"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_days")

    def test_unknown_account_rejected(self):
        with patch.object(server, "_resolve_admin_target_identity", return_value=None):
            result = server.admin_extend_subscription_response({"accountId": "nope", "days": 30})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_not_found")


class DryRunTests(unittest.TestCase):
    def test_free_plan_is_ineligible_even_in_dry_run(self):
        billing = server.normalize_billing_store({"accountId": ACCOUNT_ID, "activePlan": "free"})
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_billing_store", return_value=billing):
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "dryRun": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "plan_not_eligible_for_extension")
        self.assertEqual(result["activePlan"], "free")

    def test_dry_run_without_days_reports_current_status_only(self):
        billing = server.normalize_billing_store({
            "accountId": ACCOUNT_ID, "activePlan": "pro",
            "subscription": {"status": "active", "expiresAt": "2026-08-01T00:00:00Z"},
        })
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target("陳先生家")), \
             patch.object(server, "load_billing_store", return_value=billing):
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "dryRun": True})
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["previousExpiresAt"], "2026-08-01T00:00:00Z")
        self.assertIsNone(result["newExpiresAt"])
        self.assertFalse(result["appleManagedSubscription"])
        self.assertFalse(result["wasLapsedOrMissing"])

    def test_dry_run_with_days_previews_new_date_without_saving(self):
        billing = server.normalize_billing_store({
            "accountId": ACCOUNT_ID, "activePlan": "plus",
            "subscription": {"status": "active", "expiresAt": "2026-08-01T00:00:00Z"},
        })
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_billing_store", return_value=billing), \
             patch.object(server, "save_billing_store") as save_mock:
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 30, "dryRun": True})
        save_mock.assert_not_called()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["newExpiresAt"], "2026-08-31T00:00:00Z")


class CommitExtendFromFutureDateTests(unittest.TestCase):
    def test_extends_from_existing_future_expiry_not_from_today(self):
        billing_state = {"store": server.normalize_billing_store({
            "accountId": ACCOUNT_ID, "activePlan": "pro", "provider": "manual-admin-grant",
            "subscription": {"status": "active", "expiresAt": "2026-08-01T00:00:00Z", "willRenew": False},
        })}

        def load_billing():
            return server.normalize_billing_store(billing_state["store"])

        def save_billing(data, reconcile=True):
            billing_state["store"] = server.normalize_billing_store(data)
            return billing_state["store"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target("王媽媽家")), \
             patch.object(server, "load_billing_store", side_effect=load_billing), \
             patch.object(server, "save_billing_store", side_effect=save_billing), \
             patch.object(server, "append_audit_event") as audit:
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 30, "reason": "客訴補償"})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["previousExpiresAt"], "2026-08-01T00:00:00Z")
        self.assertEqual(result["newExpiresAt"], "2026-08-31T00:00:00Z")
        self.assertFalse(result["wasLapsedOrMissing"])
        self.assertEqual(billing_state["store"]["subscription"]["expiresAt"], "2026-08-31T00:00:00Z")
        self.assertEqual(billing_state["store"]["subscription"]["status"], "active")
        audit.assert_called_once()
        event = audit.call_args.args[0]
        self.assertEqual(event["eventType"], "admin_subscription_extended")
        self.assertEqual(event["details"]["days"], 30)
        self.assertEqual(event["details"]["previousExpiresAt"], "2026-08-01T00:00:00Z")
        self.assertEqual(event["details"]["newExpiresAt"], "2026-08-31T00:00:00Z")


class CommitExtendFromTodayTests(unittest.TestCase):
    def _assert_new_expiry_close_to_now_plus_days(self, new_expires_iso, days, tolerance_seconds=30):
        parsed = server.parse_optional_iso_datetime(new_expires_iso)
        expected = datetime.now(timezone.utc) + timedelta(days=days)
        self.assertLess(abs((parsed - expected).total_seconds()), tolerance_seconds)

    def test_expired_status_extends_from_today_not_from_stale_expiry(self):
        billing_state = {"store": server.normalize_billing_store({
            "accountId": ACCOUNT_ID, "activePlan": "pro",
            "subscription": {"status": "expired", "expiresAt": "2020-01-01T00:00:00Z", "willRenew": False},
        })}

        def load_billing():
            return server.normalize_billing_store(billing_state["store"])

        def save_billing(data, reconcile=True):
            billing_state["store"] = server.normalize_billing_store(data)
            return billing_state["store"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_billing_store", side_effect=load_billing), \
             patch.object(server, "save_billing_store", side_effect=save_billing), \
             patch.object(server, "append_audit_event"):
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 14})

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["wasLapsedOrMissing"])
        self._assert_new_expiry_close_to_now_plus_days(result["newExpiresAt"], 14)
        self.assertEqual(billing_state["store"]["subscription"]["status"], "active")
        self.assertFalse(billing_state["store"]["subscription"]["willRenew"])

    def test_missing_expires_at_extends_from_today(self):
        billing_state = {"store": server.normalize_billing_store({
            "accountId": ACCOUNT_ID, "activePlan": "plus",
            "subscription": {"status": "active", "expiresAt": None},
        })}

        def load_billing():
            return server.normalize_billing_store(billing_state["store"])

        def save_billing(data, reconcile=True):
            billing_state["store"] = server.normalize_billing_store(data)
            return billing_state["store"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_billing_store", side_effect=load_billing), \
             patch.object(server, "save_billing_store", side_effect=save_billing), \
             patch.object(server, "append_audit_event"):
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 7})

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["wasLapsedOrMissing"])
        self._assert_new_expiry_close_to_now_plus_days(result["newExpiresAt"], 7)


class AppleManagedSubscriptionTests(unittest.TestCase):
    def test_does_not_touch_apple_provider_or_product_fields(self):
        billing_state = {"store": server.normalize_billing_store({
            "accountId": ACCOUNT_ID, "activePlan": "pro", "provider": "apple_storekit2",
            "subscription": {
                "status": "active", "expiresAt": "2026-08-01T00:00:00Z", "willRenew": True,
                "productId": "net.munea.app.pro.monthly", "originalTransactionId": "orig-tx-1",
            },
        })}

        def load_billing():
            return server.normalize_billing_store(billing_state["store"])

        def save_billing(data, reconcile=True):
            billing_state["store"] = server.normalize_billing_store(data)
            return billing_state["store"]

        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "load_billing_store", side_effect=load_billing), \
             patch.object(server, "save_billing_store", side_effect=save_billing), \
             patch.object(server, "append_audit_event") as audit:
            result = server.admin_extend_subscription_response({"accountId": ACCOUNT_ID, "days": 10})

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["appleManagedSubscription"])
        # 沒被本功能誤蓋：provider／productId／originalTransactionId 原封不動
        self.assertEqual(billing_state["store"]["provider"], "apple_storekit2")
        self.assertEqual(billing_state["store"]["subscription"]["productId"], "net.munea.app.pro.monthly")
        self.assertEqual(billing_state["store"]["subscription"]["originalTransactionId"], "orig-tx-1")
        # 已經是 active 續約中，延長不應該把 willRenew 動成 False
        self.assertTrue(billing_state["store"]["subscription"]["willRenew"])
        self.assertEqual(billing_state["store"]["subscription"]["expiresAt"], "2026-08-11T00:00:00Z")
        event = audit.call_args.args[0]
        self.assertTrue(event["details"]["appleManagedSubscription"])


if __name__ == "__main__":
    unittest.main()
