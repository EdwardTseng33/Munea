#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "growth-metrics-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
from supabase_adapter import SupabaseAdapter  # noqa: E402


ACCOUNT = "11111111-1111-4111-8111-111111111111"
PERSON = "22222222-2222-4222-8222-222222222222"


def _tmp_json(initial):
    handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    handle.write(initial.encode("utf-8"))
    handle.close()
    return handle.name


class AdminGrowthMetricsTests(unittest.TestCase):
    """後台『成長與黏著』：黏著度／留存 D1-D30／啟用漏斗（JSON 備援路徑）。"""

    def setUp(self):
        self.events_path = _tmp_json("{}")
        self.billing_path = _tmp_json("{}")
        self.profile_path = _tmp_json("{}")
        self.patches = [
            patch.object(server, "PRODUCT_EVENTS_PATH", self.events_path),
            patch.object(server, "BILLING_STORE_PATH", self.billing_path),
            patch.object(server, "APP_PROFILE_STORE_PATH", self.profile_path),
        ]
        for p in self.patches:
            p.start()
        server._APP_PROFILE_CACHE["store"] = None
        server._APP_PROFILE_CACHE["ts"] = 0.0

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for path in (self.events_path, self.billing_path, self.profile_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        server._APP_PROFILE_CACHE["store"] = None
        server._APP_PROFILE_CACHE["ts"] = 0.0

    @staticmethod
    def _iso(days_ago, hour=12):
        dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return dt.strftime("%Y-%m-%dT{:02d}:00:00Z".format(hour))

    def _seed_events(self, items):
        store = server.default_product_events_store()
        store["events"] = [server.normalize_product_event(item) for item in items]
        server.write_json_file(self.events_path, store)

    def _seed_billing(self, account_id, status="active", plan="plus"):
        server.write_json_file(self.billing_path, {
            "accountId": account_id,
            "activePlan": plan,
            "provider": "storekit2-or-revenuecat",
            "subscription": {"status": status},
            "updatedAt": server.utc_now(),
        })

    def test_empty_state_reports_null_not_zero(self):
        response = server.admin_growth_metrics({"days": 30})
        self.assertTrue(response["ok"])
        self.assertEqual(response["stickiness"], {
            "activePeople": 0, "meaningfulPersonDays": 0, "avgActiveDays": None, "rate": None,
        })
        for key in ("d1", "d7", "d14", "d30"):
            self.assertEqual(response["retention"][key], {"cohort": 0, "retained": 0, "rate": None})
        for step in response["funnel"]:
            self.assertEqual(step["count"], 0)
            self.assertIsNone(step["rate"])
        self.assertIsNone(response["dataRange"]["earliestEventAt"])
        self.assertIsNone(response["dataRange"]["days"])
        self.assertTrue(response["notes"])

    def test_stickiness_counts_distinct_active_days_in_window(self):
        self._seed_events([
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(0)},
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(1)},
            {"personId": "p2", "accountId": ACCOUNT, "eventName": "activity_created", "eventTime": self._iso(0)},
        ])
        response = server.admin_growth_metrics({"days": 30})
        st = response["stickiness"]
        self.assertEqual(st["activePeople"], 2)
        self.assertEqual(st["meaningfulPersonDays"], 3)
        self.assertAlmostEqual(st["avgActiveDays"], 1.5, places=2)
        self.assertAlmostEqual(st["rate"], 1.5 / 30, places=4)

    def test_stickiness_ignores_events_outside_window(self):
        self._seed_events([
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(45)},
        ])
        response = server.admin_growth_metrics({"days": 30})
        self.assertEqual(response["stickiness"]["activePeople"], 0)
        self.assertIsNone(response["stickiness"]["avgActiveDays"])

    def test_retention_d1_retained_when_meaningful_event_on_exact_day1(self):
        self._seed_events([
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(3)},
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(2)},
        ])
        response = server.admin_growth_metrics({"days": 30})
        d1 = response["retention"]["d1"]
        self.assertEqual(d1["cohort"], 1)
        self.assertEqual(d1["retained"], 1)
        self.assertEqual(d1["rate"], 1.0)

    def test_retention_not_retained_when_no_event_on_exact_day(self):
        self._seed_events([
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(5)},
        ])
        response = server.admin_growth_metrics({"days": 30})
        d1 = response["retention"]["d1"]
        self.assertEqual(d1["cohort"], 1)
        self.assertEqual(d1["retained"], 0)
        self.assertEqual(d1["rate"], 0.0)

    def test_retention_excludes_people_not_yet_matured(self):
        self._seed_events([
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(0)},
        ])
        response = server.admin_growth_metrics({"days": 30})
        d1 = response["retention"]["d1"]
        self.assertEqual(d1["cohort"], 0)
        self.assertIsNone(d1["rate"])

    def test_events_without_person_id_excluded_and_noted(self):
        # JSON 備援路徑寫入時一定會帶入本機示範 personId，測不出「真的沒有 personId」；
        # 這種情況只在 Supabase 原始列 person_id 真的是 null 時才會出現，所以這裡直接假造
        # 一筆已正規化、但 personId 被清成 None 的事件，繞開本機示範帳號的預設值。
        fake_event = server.normalize_product_event({
            "accountId": ACCOUNT,
            "eventName": "avatar_session_completed",
            "eventTime": self._iso(0),
        })
        fake_event["personId"] = None
        with patch.object(server, "load_admin_growth_product_events", return_value=[fake_event]):
            response = server.admin_growth_metrics({"days": 30})
        self.assertEqual(response["stickiness"]["activePeople"], 0)
        self.assertTrue(any("沒有帶長輩身分" in note for note in response["notes"]))

    def test_funnel_counts_registration_call_chat_and_paid(self):
        self._seed_events([
            {"accountId": ACCOUNT, "personId": PERSON, "eventName": "account_bootstrapped", "eventTime": self._iso(5)},
            {"accountId": ACCOUNT, "personId": PERSON, "eventName": "voice_session_started", "eventTime": self._iso(4)},
            {"accountId": ACCOUNT, "personId": PERSON, "eventName": "avatar_session_completed", "eventTime": self._iso(3)},
        ])
        self._seed_billing(ACCOUNT, status="active", plan="plus")
        response = server.admin_growth_metrics({"days": 30})
        funnel = {step["step"]: step for step in response["funnel"]}
        self.assertEqual(funnel["registered"]["count"], 1)
        self.assertEqual(funnel["firstCall"]["count"], 1)
        self.assertEqual(funnel["firstChat"]["count"], 1)
        self.assertEqual(funnel["paid"]["count"], 1)
        self.assertIsNone(funnel["registered"]["rate"])
        self.assertEqual(funnel["firstCall"]["rate"], 1.0)

    def test_paid_step_ignores_free_plan_and_inactive_status(self):
        self._seed_events([
            {"accountId": ACCOUNT, "personId": PERSON, "eventName": "account_bootstrapped", "eventTime": self._iso(5)},
        ])
        self._seed_billing(ACCOUNT, status="active", plan="free")
        response = server.admin_growth_metrics({"days": 30})
        funnel = {step["step"]: step for step in response["funnel"]}
        self.assertEqual(funnel["paid"]["count"], 0)

    def test_paid_step_does_not_trust_client_analytics_event(self):
        self._seed_events([
            {"accountId": ACCOUNT, "personId": PERSON, "eventName": "account_bootstrapped", "eventTime": self._iso(5)},
            {"accountId": ACCOUNT, "personId": PERSON, "eventName": "subscription_purchased", "eventTime": self._iso(4), "properties": {"plan": "plus"}},
        ])
        response = server.admin_growth_metrics({"days": 30})
        funnel = {step["step"]: step for step in response["funnel"]}
        self.assertEqual(funnel["paid"]["count"], 0)

    def test_data_range_reports_earliest_event(self):
        self._seed_events([
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(10)},
            {"personId": "p1", "accountId": ACCOUNT, "eventName": "avatar_session_completed", "eventTime": self._iso(2)},
        ])
        response = server.admin_growth_metrics({"days": 30})
        self.assertEqual(response["dataRange"]["earliestEventAt"], self._iso(10))
        self.assertGreaterEqual(response["dataRange"]["days"], 9)

    def test_no_engineering_jargon_in_principle_text(self):
        response = server.admin_growth_metrics({})
        for banned in ("person_id", "account_id", "SQL", "personId", "accountId"):
            self.assertNotIn(banned, response["principle"])
        self.assertIn("黏著度", response["principle"])


class SupabaseAdminGrowthMetricsCrossAccountTests(unittest.TestCase):
    """Adapter 層：後台成長與黏著查詢不能被單一 account_id 過濾掉。"""

    def _adapter(self):
        return SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )

    def test_load_admin_product_events_has_no_account_scope_filter(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "id": "evt-1",
                "account_id": "other-account-not-in-identity",
                "person_id": "other-person-not-in-identity",
                "event_name": "avatar_session_completed",
                "event_time": "2026-07-18T00:00:00Z",
                "properties": {},
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_product_events(limit=100)

        self.assertEqual(captured["table"], "product_events")
        self.assertNotIn("account_id", captured["query"])
        self.assertEqual(captured["query"]["order"], "event_time.asc")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accountId"], "other-account-not-in-identity")

    def test_load_admin_subscription_ledger_has_no_account_scope_filter(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "account_id": "other-account-not-in-identity",
                "status": "active",
                "active_plan": "plus",
                "provider": "storekit2-or-revenuecat",
                "created_at": "2026-07-01T00:00:00Z",
                "updated_at": "2026-07-18T00:00:00Z",
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_subscription_ledger(limit=100)

        self.assertEqual(captured["table"], "subscription_ledger")
        self.assertNotIn("account_id", captured["query"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accountId"], "other-account-not-in-identity")
        self.assertEqual(rows[0]["activePlan"], "plus")


if __name__ == "__main__":
    unittest.main()
