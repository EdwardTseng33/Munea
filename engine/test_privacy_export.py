#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "privacy-export-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server
from supabase_adapter import SupabaseAdapter


ACCOUNT = "11111111-1111-4111-8111-111111111111"
PERSON = "22222222-2222-4222-8222-222222222222"
AUTH_USER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class PrivacyExportTests(unittest.TestCase):
    def test_response_delivers_completed_scoped_package(self):
        class Backend:
            request_scoped = True

            def enabled(self):
                return True

            def export_scoped_personal_data(self):
                return {"schemaVersion": 1, "scope": "authenticated_person", "person": {"id": PERSON}}

        with patch.object(server, "data_backend", return_value=Backend()), \
             patch.object(server, "append_privacy_request", return_value={"id": "export-1", "status": "completed"}) as append:
            response = server.privacy_export_response({"action": "request"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["mediaType"], "application/json")
        self.assertEqual(response["exportPackage"]["person"]["id"], PERSON)
        self.assertTrue(response["filename"].endswith(".json"))
        self.assertEqual(append.call_args.args[1]["status"], "completed")

    def test_adapter_never_queries_another_person(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON, "authUserId": AUTH_USER},
        )
        queries = []

        def fake_select(table, query):
            queries.append((table, dict(query)))
            if table == "accounts":
                return [{"id": ACCOUNT, "name": "Test"}]
            if table == "account_members":
                return [{"id": "member", "account_id": ACCOUNT, "user_id": AUTH_USER}]
            if table == "persons":
                return [{"id": PERSON, "account_id": ACCOUNT, "display_name": "Owner"}]
            return []

        with patch.object(adapter, "_select", side_effect=fake_select):
            package = adapter.export_scoped_personal_data()
        self.assertEqual(package["person"]["id"], PERSON)
        for _table, query in queries:
            if "person_id" in query:
                self.assertEqual(query["person_id"], f"eq.{PERSON}")
            if "account_id" in query:
                self.assertEqual(query["account_id"], f"eq.{ACCOUNT}")

    def test_export_fails_closed_without_scoped_identity(self):
        adapter = SupabaseAdapter(env={})
        with self.assertRaisesRegex(RuntimeError, "request-scoped"):
            adapter.export_scoped_personal_data()


if __name__ == "__main__":
    unittest.main()
