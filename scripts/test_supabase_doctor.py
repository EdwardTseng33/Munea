#!/usr/bin/env python3
"""Contract tests for migration 017 live observability and error safety."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "scripts"))

import supabase_adapter  # noqa: E402
import supabase_doctor  # noqa: E402


ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"
PERSON_ID = "22222222-2222-4222-8222-222222222222"
ENV = {
    "MUNEA_DATABASE_PROVIDER": "supabase",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
    "MUNEA_SUPABASE_ACCOUNT_ID": ACCOUNT_ID,
    "MUNEA_SUPABASE_PERSON_ID": PERSON_ID,
}


class FakeDoctorAdapter:
    def __init__(self, failure=None):
        self.failure = failure

    def enabled(self):
        return True

    def status(self):
        return {
            "provider": "supabase",
            "enabled": True,
            "missing": [],
            "tables": ["notification_settings"],
        }

    def check_table(self, table):
        if self.failure:
            raise self.failure
        return True

    def load_app_profile_store(self):
        return {}

    def load_companion_profile(self):
        return {}

    def load_billing_store(self):
        return {}

    def load_privacy_requests_store(self):
        return {}


class SupabaseDoctorContractTests(unittest.TestCase):
    def setUp(self):
        supabase_adapter._MISSING_TABLES.clear()
        supabase_adapter._reset_circuit()

    def tearDown(self):
        supabase_adapter._MISSING_TABLES.clear()
        supabase_adapter._reset_circuit()

    def adapter(self):
        return supabase_adapter.SupabaseAdapter(env=ENV)

    def http_failure(self, status, code, message):
        body = json.dumps({"code": code, "message": message}).encode("utf-8")
        return urllib.error.HTTPError(
            "https://example.supabase.co/rest/v1/notification_settings",
            status,
            message,
            {},
            io.BytesIO(body),
        )

    def run_doctor(self, failure):
        fake = FakeDoctorAdapter(failure=failure)
        with (
            mock.patch.object(supabase_doctor, "load_engine_env", return_value=set(ENV)),
            mock.patch.object(supabase_doctor.supabase_adapter, "make_adapter", return_value=fake),
            mock.patch.dict(os.environ, ENV, clear=True),
        ):
            return supabase_doctor.doctor(live=True)

    def test_status_and_schema_map_include_migration_017(self):
        self.assertIn("notification_settings", self.adapter().status()["tables"])
        self.assertEqual(
            supabase_doctor.schema_files_for_tables(["notification_settings"]),
            ["supabase/sql/017_notification_settings.sql"],
        )

    def test_notification_settings_probe_uses_person_id_primary_key(self):
        adapter = self.adapter()
        with mock.patch.object(adapter, "_request", return_value=[]) as request:
            self.assertTrue(adapter.check_table("notification_settings"))
        request.assert_called_once_with(
            "GET",
            "notification_settings",
            query={"select": "person_id", "limit": "1"},
        )

    def test_adapter_classifies_missing_permission_and_configuration(self):
        cases = [
            (404, "PGRST205", "table missing", "missing_table"),
            (403, "42501", "permission denied", "permission"),
            (401, "42501", "permission denied", "configuration"),
            (401, "PGRST301", "invalid API key", "configuration"),
            (401, "PGRST205", "table missing", "configuration"),
            (403, "PGRST205", "table missing", "permission"),
        ]
        for status, code, message, expected in cases:
            with self.subTest(status=status, code=code):
                with mock.patch.object(
                    supabase_adapter.urllib.request,
                    "urlopen",
                    side_effect=self.http_failure(status, code, message),
                ):
                    with self.assertRaises(supabase_adapter.SupabaseRequestError) as raised:
                        self.adapter().check_table("notification_settings")
                self.assertEqual(raised.exception.error_kind, expected)
                self.assertEqual(raised.exception.error_code, code)
                supabase_adapter._MISSING_TABLES.clear()

    def test_doctor_recommends_017_only_for_pgrst205(self):
        missing = supabase_adapter.SupabaseRequestError(
            "PGRST205 missing",
            error_kind="missing_table",
            status_code=404,
            error_code="PGRST205",
        )
        result = self.run_doctor(missing)
        self.assertFalse(result["ok"])
        self.assertEqual(result["tableChecks"][0]["status"], "missing")
        self.assertEqual(
            result["recommendedSqlFiles"],
            ["supabase/sql/017_notification_settings.sql"],
        )

    def test_permission_or_configuration_failure_never_recommends_sql(self):
        cases = [
            supabase_adapter.SupabaseRequestError(
                "permission denied",
                error_kind="permission",
                status_code=403,
                error_code="42501",
            ),
            supabase_adapter.SupabaseRequestError(
                "invalid API key",
                error_kind="configuration",
                status_code=401,
                error_code="PGRST301",
            ),
            supabase_adapter.SupabaseRequestError(
                "PGRST205 table missing",
                error_kind="configuration",
                status_code=401,
                error_code="PGRST205",
            ),
            supabase_adapter.SupabaseRequestError(
                "PGRST205 table missing",
                error_kind="permission",
                status_code=403,
                error_code="PGRST205",
            ),
        ]
        for failure in cases:
            with self.subTest(kind=failure.error_kind):
                result = self.run_doctor(failure)
                self.assertFalse(result["ok"])
                self.assertEqual(result["recommendedSqlFiles"], [])
                self.assertIn(result["tableChecks"][0]["status"], {"permission", "configuration"})

    def test_cached_missing_table_remains_structured(self):
        supabase_adapter._mark_table_missing("notification_settings")
        with self.assertRaises(supabase_adapter.SupabaseRequestError) as raised:
            self.adapter().check_table("notification_settings")
        self.assertEqual(raised.exception.error_kind, "missing_table")
        self.assertEqual(raised.exception.error_code, "PGRST205")


if __name__ == "__main__":
    unittest.main()
