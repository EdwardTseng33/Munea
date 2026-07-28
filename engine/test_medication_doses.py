#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "medication-dose-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
from supabase_adapter import SupabaseAdapter  # noqa: E402


ACCOUNT = "11111111-1111-4111-8111-111111111111"
PERSON = "22222222-2222-4222-8222-222222222222"


class MedicationDoseTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        handle.write(b"[]")
        handle.close()
        self.path = handle.name
        self.path_patch = patch.object(server, "MEDICATION_DOSES_PATH", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_json_upsert_is_idempotent_and_queryable_by_date(self):
        base = {
            "personId": "person-a",
            "doseKey": "2026-07-15|med-a|早餐後",
            "medicationName": "血壓藥",
            "slot": "早餐後",
            "scheduledDate": "2026-07-15",
            "expectedCount": 2,
            "status": "scheduled",
        }
        first = server.medication_doses_response({"action": "save", "dose": base})
        second = server.medication_doses_response({"action": "save", "dose": {**base, "status": "taken"}})
        self.assertTrue(first["ok"] and second["ok"])
        listed = server.medication_doses_response({
            "action": "list", "personId": "person-a",
            "startDate": "2026-07-15", "endDate": "2026-07-15",
        })
        self.assertEqual(len(listed["doses"]), 1)
        self.assertEqual(listed["doses"][0]["status"], "taken")
        with open(self.path, encoding="utf-8") as source:
            self.assertEqual(len(json.load(source)), 1)

    def test_missing_dose_key_is_rejected(self):
        response = server.medication_doses_response({"action": "save", "dose": {"status": "taken"}})
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"], "dose_key_required")

    def test_adapter_scopes_person_and_preserves_non_uuid_ids_in_metadata(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )
        row = adapter.medication_dose_to_row({
            "accountId": "attacker-account",
            "personId": "local-person",
            "reminderId": "med-a",
            "doseKey": "2026-07-15|med-a|早餐後",
            "scheduledDate": "2026-07-15",
        })
        self.assertEqual(row["account_id"], ACCOUNT)
        self.assertEqual(row["person_id"], PERSON)
        self.assertIsNone(row["routine_reminder_id"])
        self.assertEqual(row["metadata"]["originalPersonId"], "local-person")
        self.assertEqual(row["metadata"]["originalReminderId"], "med-a")


class AdminMedicationAdherenceTests(unittest.TestCase):
    """後台「用藥與回診」：跨帳號依從率、每日趨勢、連續漏服（JSON 備援路徑）。"""

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        handle.write(b"[]")
        handle.close()
        self.path = handle.name
        self.path_patch = patch.object(server, "MEDICATION_DOSES_PATH", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def _seed(self, fixtures):
        items = [server.normalize_medication_dose(f) for f in fixtures]
        server.write_json_file(self.path, items)

    def test_empty_window_reports_null_rate_not_zero(self):
        response = server.admin_medication_adherence({"days": 30, "limit": 50})
        self.assertTrue(response["ok"])
        self.assertIsNone(response["adherenceRate"])
        self.assertEqual(response["daily"], [])
        self.assertEqual(response["people"], [])
        self.assertEqual(
            response["totals"],
            {"scheduled": 0, "taken": 0, "snoozed": 0, "skipped": 0, "missed": 0},
        )

    def test_totals_daily_and_missed_streak_cross_account(self):
        today = datetime.now(timezone.utc).date()

        def on(offset):
            return (today - timedelta(days=offset)).isoformat()

        self._seed([
            # 家庭 A：兩天連續漏服，再往前一天有做到 → 連續漏服應為 2
            {"personId": "person-a", "accountId": "account-a", "doseKey": "a1", "scheduledDate": on(0), "status": "missed"},
            {"personId": "person-a", "accountId": "account-a", "doseKey": "a2", "scheduledDate": on(1), "status": "missed"},
            {"personId": "person-a", "accountId": "account-a", "doseKey": "a3", "scheduledDate": on(2), "status": "taken"},
            # 家庭 B：今天做到、昨天跳過 → 連續漏服應為 0（沒有真的漏服）
            {"personId": "person-b", "accountId": "account-b", "doseKey": "b1", "scheduledDate": on(0), "status": "taken"},
            {"personId": "person-b", "accountId": "account-b", "doseKey": "b2", "scheduledDate": on(1), "status": "skipped"},
        ])
        response = server.admin_medication_adherence({"days": 30, "limit": 50})
        self.assertTrue(response["ok"])
        self.assertEqual(response["totals"], {"scheduled": 0, "taken": 2, "snoozed": 0, "skipped": 1, "missed": 2})
        self.assertAlmostEqual(response["adherenceRate"], 2 / 5, places=4)
        self.assertEqual(len(response["daily"]), 3)
        self.assertEqual(response["daily"][0]["date"], response["daily"][0]["date"])  # sorted ascending, sanity below
        self.assertEqual([d["date"] for d in response["daily"]], sorted(d["date"] for d in response["daily"]))

        by_person = {p["personId"]: p for p in response["people"]}
        self.assertEqual(by_person["person-a"]["missedStreak"], 2)
        self.assertAlmostEqual(by_person["person-a"]["adherenceRate"], 1 / 3, places=4)
        self.assertEqual(by_person["person-b"]["missedStreak"], 0)
        self.assertAlmostEqual(by_person["person-b"]["adherenceRate"], 1 / 2, places=4)
        # 連續漏服多、依從率低的人排前面
        self.assertEqual(response["people"][0]["personId"], "person-a")

    def test_no_medical_claims_in_principle_text(self):
        response = server.admin_medication_adherence({})
        # 只允許「不做診斷／不做醫療建議」這種否定句；不可出現任何實際醫療判讀措辭
        for banned in ("療效", "建議劑量", "確診", "病情"):
            self.assertNotIn(banned, response["principle"])
        self.assertIn("不做診斷", response["principle"])
        self.assertIn("提醒做到", response["principle"])

    def test_test_account_doses_are_excluded_from_totals_and_people(self):
        """2026-07-24 稽核補：這頁原本沒接測試帳號排除，示範／QA 帳號的用藥事件會混進真實依從率。"""
        today = datetime.now(timezone.utc).date()

        def on(offset):
            return (today - timedelta(days=offset)).isoformat()

        self._seed([
            {"personId": "person-real", "accountId": "account-real", "doseKey": "r1", "scheduledDate": on(0), "status": "taken"},
            {"personId": "person-test", "accountId": "test-account-x", "doseKey": "t1", "scheduledDate": on(0), "status": "missed"},
            {"personId": "person-test", "accountId": "test-account-x", "doseKey": "t2", "scheduledDate": on(1), "status": "missed"},
        ])
        server._TEST_ACCOUNT_ID_CACHE["ids"] = {"test-account-x"}
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = server.time.time() + 999
        try:
            response = server.admin_medication_adherence({"days": 30, "limit": 50})
        finally:
            server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
            server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0
        self.assertEqual(response["totals"], {"scheduled": 0, "taken": 1, "snoozed": 0, "skipped": 0, "missed": 0})
        person_ids = [p["personId"] for p in response["people"]]
        self.assertIn("person-real", person_ids)
        self.assertNotIn("person-test", person_ids)


class SupabaseAdminMedicationCrossAccountTests(unittest.TestCase):
    """Adapter 層：後台跨帳號用藥查詢不能被單一 account_id 過濾掉。"""

    def test_load_admin_medication_doses_has_no_account_scope_filter(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "id": "dose-1",
                "account_id": "other-account-not-in-identity",
                "person_id": "other-person-not-in-identity",
                "status": "taken",
                "scheduled_date": "2026-07-18",
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_medication_doses(since_date="2026-06-19", limit=100)

        self.assertEqual(captured["table"], "medication_dose_events")
        self.assertNotIn("account_id", captured["query"])
        self.assertNotIn("person_id", captured["query"])
        self.assertEqual(captured["query"]["scheduled_date"], "gte.2026-06-19")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accountId"], "other-account-not-in-identity")

    def test_load_persons_by_ids_filters_out_non_uuid_and_returns_display_name_map(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{"id": PERSON, "display_name": "陳奶奶"}]

        with patch.object(adapter, "_select", side_effect=fake_select):
            names = adapter.load_persons_by_ids([PERSON, "not-a-uuid", None])

        self.assertEqual(captured["table"], "persons")
        self.assertIn(PERSON, captured["query"]["id"])
        self.assertNotIn("not-a-uuid", captured["query"]["id"])
        self.assertEqual(names, {PERSON: "陳奶奶"})


if __name__ == "__main__":
    unittest.main()
