#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "notification-platform-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import notification_service  # noqa: E402
import server  # noqa: E402
from supabase_adapter import SupabaseAdapter  # noqa: E402


ACCOUNT = "11111111-1111-4111-8111-111111111111"
SENDER = "22222222-2222-4222-8222-222222222222"
RECIPIENT = "33333333-3333-4333-8333-333333333333"
AUTH_USER = "44444444-4444-4444-8444-444444444444"
FAMILY = "55555555-5555-4555-8555-555555555555"


class NotificationPlatformTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.files = {
            "PUSH_DEVICES_PATH": root / "push_devices.json",
            "NOTIFICATION_EVENTS_PATH": root / "notification_events.json",
            "NOTIFICATION_DELIVERIES_PATH": root / "notification_deliveries.json",
            "FAMILY_RELAYS_PATH": root / "family_relays.json",
        }
        self.patches = []
        for name, path in self.files.items():
            path.write_text("[]", encoding="utf-8")
            current = patch.object(server, name, str(path))
            current.start()
            self.patches.append(current)
        self.identity_token = None

    def tearDown(self):
        if self.identity_token is not None:
            server.REQUEST_DATA_IDENTITY.reset(self.identity_token)
        for current in reversed(self.patches):
            current.stop()
        self.tempdir.cleanup()

    def bind(self, person_id):
        if self.identity_token is not None:
            server.REQUEST_DATA_IDENTITY.reset(self.identity_token)
        self.identity_token = server.REQUEST_DATA_IDENTITY.set({
            "accountId": ACCOUNT,
            "personId": person_id,
            "authUserId": AUTH_USER,
            "familyGroupId": FAMILY,
        })

    def test_device_registration_is_scoped_and_token_is_not_returned(self):
        self.bind(RECIPIENT)
        result = server.push_devices_response({
            "action": "register",
            "device": {
                "token": "a" * 64,
                "environment": "sandbox",
                "bundleId": "net.munea.app",
                "permissionStatus": "authorized",
                "notificationsEnabled": True,
            },
        })
        self.assertTrue(result["ok"])
        self.assertNotIn("token", result["device"])
        self.assertNotIn("tokenHash", result["device"])
        listed = server.push_devices_response({"action": "list"})
        self.assertEqual(len(listed["devices"]), 1)
        stored = json.loads(self.files["PUSH_DEVICES_PATH"].read_text(encoding="utf-8"))
        self.assertEqual(stored[0]["personId"], RECIPIENT)
        self.assertEqual(stored[0]["tokenHash"], notification_service.token_hash("a" * 64))

    def test_private_event_creates_durable_inbox_and_outbox(self):
        self.bind(RECIPIENT)
        server.push_devices_response({
            "action": "register",
            "token": "b" * 64,
            "environment": "production",
            "permissionStatus": "authorized",
            "notificationsEnabled": True,
        })
        event, backend = server.enqueue_notification_event({
            "eventType": "medication_due",
            "recipientPersonId": RECIPIENT,
            "resourceType": "medication_dose",
            "resourceId": "dose-1",
            "title": "晚餐後要吃降血壓藥",
            "body": "請服用 1 顆降血壓藥。",
            "sensitivity": "health_sensitive",
            "deepLink": "munea://medications/dose-1",
            "dedupeKey": "medication-due:dose-1",
        })
        self.assertEqual(backend, "json")
        public_title, public_body = notification_service.lock_screen_content(event, False)
        self.assertEqual(public_title, "沐寧提醒")
        self.assertNotIn("降血壓藥", public_body)
        private_title, private_body = notification_service.lock_screen_content(event, True)
        self.assertIn("降血壓藥", private_title + private_body)

        listed = server.notification_events_response({"action": "list", "unreadOnly": True})
        self.assertEqual(listed["unreadCount"], 1)
        self.assertEqual(listed["notifications"][0]["id"], event["id"])
        deliveries = json.loads(self.files["NOTIFICATION_DELIVERIES_PATH"].read_text(encoding="utf-8"))
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["status"], "queued")

        marked = server.notification_events_response({"action": "opened", "id": event["id"]})
        self.assertTrue(marked["ok"])
        self.assertIsNotNone(marked["notification"]["readAt"])
        self.assertEqual(server.notification_events_response({"unreadOnly": True})["unreadCount"], 0)

    def test_event_dedupe_prevents_duplicate_push(self):
        self.bind(RECIPIENT)
        base = {
            "eventType": "clinic_upcoming",
            "recipientPersonId": RECIPIENT,
            "title": "明天要回診",
            "body": "記得帶健保卡。",
            "deepLink": "munea://visits/visit-1",
            "dedupeKey": "clinic:visit-1:day-before",
        }
        first, _ = server.enqueue_notification_event(base)
        second, _ = server.enqueue_notification_event(base)
        self.assertEqual(first["id"], second["id"])
        events = json.loads(self.files["NOTIFICATION_EVENTS_PATH"].read_text(encoding="utf-8"))
        self.assertEqual(len(events), 1)

    def test_json_family_relay_also_creates_inbox_event(self):
        self.bind(SENDER)
        result = server.family_relays_response({
            "action": "create",
            "relay": {
                "recipientPersonId": RECIPIENT,
                "senderLabel": "媽媽",
                "recipientLabel": "小宇",
                "content": "晚上要早點睡",
            },
        })
        self.assertTrue(result["ok"])
        self.assertTrue(result["notificationQueued"])
        self.bind(RECIPIENT)
        inbox = server.notification_events_response({"action": "list"})
        self.assertEqual(inbox["notifications"][0]["eventType"], "family_relay")
        self.assertEqual(inbox["notifications"][0]["deepLink"], f"munea://relay/{result['relay']['id']}")

    def test_adapter_never_trusts_device_identity_from_client(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": RECIPIENT, "authUserId": AUTH_USER},
        )
        row = adapter.push_device_to_row({
            "accountId": "attacker-account",
            "personId": "attacker-person",
            "authUserId": "attacker-user",
            "token": "c" * 64,
            "permissionStatus": "authorized",
        })
        self.assertEqual(row["account_id"], ACCOUNT)
        self.assertEqual(row["person_id"], RECIPIENT)
        self.assertEqual(row["auth_user_id"], AUTH_USER)

    def test_migration_contains_private_tables_and_atomic_outbox_rpc(self):
        sql_path = Path(__file__).resolve().parents[1] / "supabase" / "sql" / "016_notification_platform.sql"
        sql = sql_path.read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.push_devices", sql)
        self.assertIn("create table if not exists public.notification_events", sql)
        self.assertIn("create table if not exists public.notification_deliveries", sql)
        self.assertIn("public.enqueue_notification_event", sql)
        self.assertIn("for update skip locked", sql.lower())
        self.assertIn("revoke all on public.push_devices from anon, authenticated", sql)


if __name__ == "__main__":
    unittest.main()
