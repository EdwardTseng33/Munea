#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "admin-subscription-mrr-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402


def _tmp_json(initial):
    handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    handle.write(initial.encode("utf-8"))
    handle.close()
    return handle.name


class AdminSubscriptionMetricsMrrTests(unittest.TestCase):
    """後台『訂閱營運聚合』MRR：目前有效訂閱（subscription_ledger 每帳號最新一筆）× 方案月費。
    2026-07-24 稽核補：這支原本 mrr 一律回 None，底層 subscription_ledger 資料其實已經存在。"""

    def setUp(self):
        self.events_path = _tmp_json("{}")
        self.events_patch = patch.object(server, "PRODUCT_EVENTS_PATH", self.events_path)
        self.events_patch.start()

    def tearDown(self):
        self.events_patch.stop()
        try:
            os.unlink(self.events_path)
        except OSError:
            pass

    @staticmethod
    def _iso(days_ago):
        dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_empty_ledger_reports_zero_mrr_not_none(self):
        with patch.object(server, "load_admin_growth_subscription_rows", return_value=[]):
            response = server.admin_subscription_metrics({"days": 30})
        self.assertTrue(response["ok"])
        self.assertEqual(response["mrr"], 0)
        self.assertEqual(response["activeSubscribersByPlan"], {})
        self.assertIsNone(response["churnRate"])
        self.assertNotIn("mrr", response["pending"])

    def test_mrr_sums_active_subscribers_by_plan_price(self):
        ledger_rows = [
            {"accountId": "acct-plus-1", "status": "active", "activePlan": "plus", "createdAt": self._iso(10), "updatedAt": self._iso(10)},
            {"accountId": "acct-plus-2", "status": "active", "activePlan": "plus", "createdAt": self._iso(5), "updatedAt": self._iso(5)},
            {"accountId": "acct-pro-1", "status": "active", "activePlan": "pro", "createdAt": self._iso(3), "updatedAt": self._iso(3)},
        ]
        with patch.object(server, "load_admin_growth_subscription_rows", return_value=ledger_rows):
            response = server.admin_subscription_metrics({"days": 30})
        self.assertEqual(response["activeSubscribersByPlan"], {"plus": 2, "pro": 1})
        self.assertEqual(response["mrr"], 2 * 599 + 1 * 1199)

    def test_inactive_and_free_rows_do_not_count_toward_mrr(self):
        ledger_rows = [
            {"accountId": "acct-cancelled", "status": "cancelled", "activePlan": "plus", "createdAt": self._iso(10), "updatedAt": self._iso(1)},
            {"accountId": "acct-free", "status": "active", "activePlan": "free", "createdAt": self._iso(10), "updatedAt": self._iso(1)},
        ]
        with patch.object(server, "load_admin_growth_subscription_rows", return_value=ledger_rows):
            response = server.admin_subscription_metrics({"days": 30})
        self.assertEqual(response["mrr"], 0)
        self.assertEqual(response["activeSubscribersByPlan"], {})

    def test_only_latest_ledger_row_per_account_counts(self):
        """一個帳號歷史上有 active 過，後來取消了——不能被舊那筆 active 誤算成現在還在付費。"""
        ledger_rows = [
            {"accountId": "acct-a", "status": "active", "activePlan": "pro", "createdAt": self._iso(60), "updatedAt": self._iso(60)},
            {"accountId": "acct-a", "status": "cancelled", "activePlan": "pro", "createdAt": self._iso(60), "updatedAt": self._iso(1)},
        ]
        with patch.object(server, "load_admin_growth_subscription_rows", return_value=ledger_rows):
            response = server.admin_subscription_metrics({"days": 30})
        self.assertEqual(response["mrr"], 0)
        self.assertEqual(response["activeSubscribersByPlan"], {})

    def test_test_account_ledger_rows_are_excluded_from_mrr(self):
        server._TEST_ACCOUNT_ID_CACHE["ids"] = {"test-account-x"}
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = server.time.time() + 999
        ledger_rows = [
            {"accountId": "acct-real", "status": "active", "activePlan": "plus", "createdAt": self._iso(10), "updatedAt": self._iso(10)},
            {"accountId": "test-account-x", "status": "active", "activePlan": "pro", "createdAt": self._iso(10), "updatedAt": self._iso(10)},
        ]
        try:
            with patch.object(server, "load_admin_growth_subscription_rows", return_value=ledger_rows):
                response = server.admin_subscription_metrics({"days": 30})
        finally:
            server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
            server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0
        self.assertEqual(response["mrr"], 599)
        self.assertEqual(response["activeSubscribersByPlan"], {"plus": 1})


if __name__ == "__main__":
    unittest.main()
