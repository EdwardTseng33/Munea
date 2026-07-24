#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "admin-safety-events-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402


def _tmp_json(initial):
    handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    handle.write(initial.encode("utf-8"))
    handle.close()
    return handle.name


class AdminSafetyEventsSummaryTests(unittest.TestCase):
    """後台「安全守護警示」：跨帳號 guardian_risk_evaluated 事件＋安全相關對話摘要（JSON 備援路徑）。"""

    def setUp(self):
        self.events_path = _tmp_json("{}")
        self.summaries_path = _tmp_json("[]")
        self.patches = [
            patch.object(server, "PRODUCT_EVENTS_PATH", self.events_path),
            patch.object(server, "CONVERSATION_SUMMARIES_PATH", self.summaries_path),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for path in (self.events_path, self.summaries_path):
            try:
                os.unlink(path)
            except OSError:
                pass

    @staticmethod
    def _iso(days_ago):
        dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _seed_events(self, items):
        store = server.default_product_events_store()
        store["events"] = [server.normalize_product_event(item) for item in items]
        server.write_json_file(self.events_path, store)

    def _seed_summaries(self, items):
        server.write_json_file(self.summaries_path, [server.normalize_conversation_summary(item) for item in items])

    def test_empty_state_reports_zero_counts(self):
        response = server.admin_safety_events_summary({"days": 30, "limit": 50})
        self.assertTrue(response["ok"])
        self.assertEqual(response["count"], 0)
        self.assertEqual(response["recent"], [])
        self.assertEqual(response["totals"]["byRiskLevel"], {})
        self.assertEqual(response["totals"]["requiresHumanEscalation"], 0)

    def test_guardian_risk_events_and_safety_summaries_aggregate_cross_account(self):
        self._seed_events([
            {
                "id": "ev-1", "accountId": "account-a", "personId": "elder-a",
                "eventName": "guardian_risk_evaluated", "eventTime": self._iso(0),
                "properties": {"riskLevel": "high", "categories": ["fall"]},
            },
            {
                "id": "ev-2", "accountId": "account-b", "personId": "elder-b",
                "eventName": "guardian_risk_evaluated", "eventTime": self._iso(1),
                "properties": {"riskLevel": "low", "categories": ["mood"]},
            },
        ])
        self._seed_summaries([
            {
                "id": "sum-1", "accountId": "account-c", "personId": "elder-c",
                "safetyRelevant": True, "memoryTags": ["fall"], "createdAt": self._iso(0),
            },
        ])
        response = server.admin_safety_events_summary({"days": 30, "limit": 50})
        self.assertEqual(response["count"], 3)
        self.assertEqual(response["totals"]["byRiskLevel"], {"high": 1, "low": 1, "review": 1})
        self.assertEqual(response["totals"]["requiresHumanEscalation"], 1)
        self.assertEqual(response["totals"]["summaryReviewRecords"], 1)

    def test_test_account_signals_are_excluded_from_counts(self):
        """2026-07-24 稽核補：這頁原本沒接測試帳號排除，示範／QA 帳號的安全事件會混進真實警示數字。"""
        self._seed_events([
            {
                "id": "ev-real", "accountId": "account-real", "personId": "elder-real",
                "eventName": "guardian_risk_evaluated", "eventTime": self._iso(0),
                "properties": {"riskLevel": "high", "categories": ["fall"]},
            },
            {
                "id": "ev-test", "accountId": "test-account-x", "personId": "elder-test",
                "eventName": "guardian_risk_evaluated", "eventTime": self._iso(0),
                "properties": {"riskLevel": "crisis", "categories": ["fall"]},
            },
        ])
        self._seed_summaries([
            {
                "id": "sum-test", "accountId": "test-account-x", "personId": "elder-test",
                "safetyRelevant": True, "memoryTags": ["fall"], "createdAt": self._iso(0),
            },
        ])
        server._TEST_ACCOUNT_ID_CACHE["ids"] = {"test-account-x"}
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = server.time.time() + 999
        try:
            response = server.admin_safety_events_summary({"days": 30, "limit": 50})
        finally:
            server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
            server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["totals"]["byRiskLevel"], {"high": 1})
        account_ids = [event.get("accountId") for event in response["recent"]]
        self.assertNotIn("test-account-x", account_ids)


if __name__ == "__main__":
    unittest.main()
