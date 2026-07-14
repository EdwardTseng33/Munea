#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
