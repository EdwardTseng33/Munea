#!/usr/bin/env python3
import os
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "family-relay-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
os.environ["MUNEA_FAMILY_RELAY_SIGNING_SECRET"] = "family-relay-unit-secret"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
import live_voice_server  # noqa: E402
from supabase_adapter import SupabaseAdapter  # noqa: E402


SENDER = "11111111-1111-4111-8111-111111111111"
RECIPIENT = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
FAMILY = "44444444-4444-4444-8444-444444444444"


def json_backend(person_id):
    return SupabaseAdapter(
        env={"MUNEA_DATABASE_PROVIDER": "json"},
        identity={"personId": person_id, "familyGroupId": FAMILY},
    )


class FamilyRelayTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        handle.write(b"[]")
        handle.close()
        self.path = handle.name
        self.path_patch = patch.object(server, "FAMILY_RELAYS_PATH", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def response(self, person_id, payload):
        with patch.object(server, "data_backend", return_value=json_backend(person_id)):
            return server.family_relays_response(payload)

    def test_relay_is_recipient_specific_and_delivered_once(self):
        created = self.response(SENDER, {
            "action": "create",
            "relay": {
                "senderPersonId": OTHER,
                "recipientPersonId": RECIPIENT,
                "senderLabel": "媽媽",
                "recipientLabel": "小宇",
                "content": "晚上早點睡，不要又熬夜了",
            },
        })
        self.assertTrue(created["ok"])
        self.assertEqual(created["relay"]["senderPersonId"], SENDER)
        self.assertIsNone(self.response(OTHER, {"action": "claim"})["relay"])

        claimed = self.response(RECIPIENT, {"action": "claim"})["relay"]
        self.assertEqual(claimed["content"], "晚上早點睡，不要又熬夜了")
        self.assertEqual(claimed["status"], "claimed")
        self.assertTrue(live_voice_server.verify_family_relay_proof(claimed))
        self.assertFalse(live_voice_server.verify_family_relay_proof({**claimed, "content": "被竄改的話"}))

        wrong = self.response(RECIPIENT, {"action": "ack", "id": claimed["id"], "claimToken": "wrong"})
        self.assertFalse(wrong["ok"])
        delivered = self.response(RECIPIENT, {
            "action": "ack", "id": claimed["id"], "claimToken": claimed["claimToken"],
        })
        self.assertTrue(delivered["ok"])
        self.assertEqual(delivered["relay"]["status"], "delivered")
        self.assertIsNone(self.response(RECIPIENT, {"action": "claim"})["relay"])

    def test_failed_call_can_release_for_next_attempt(self):
        self.response(SENDER, {
            "action": "create",
            "relay": {"recipientPersonId": RECIPIENT, "senderLabel": "阿嬤", "recipientLabel": "小宇", "content": "記得吃早餐"},
        })
        claimed = self.response(RECIPIENT, {"action": "claim"})["relay"]
        released = self.response(RECIPIENT, {
            "action": "release", "id": claimed["id"], "claimToken": claimed["claimToken"],
        })
        self.assertTrue(released["ok"])
        self.assertEqual(released["relay"]["status"], "pending")
        self.assertIsNotNone(self.response(RECIPIENT, {"action": "claim"})["relay"])

    def test_stale_claim_from_force_quit_is_requeued(self):
        self.response(SENDER, {
            "action": "create",
            "relay": {"recipientPersonId": RECIPIENT, "senderLabel": "媽媽", "recipientLabel": "小宇", "content": "早點休息"},
        })
        claimed = self.response(RECIPIENT, {"action": "claim"})["relay"]
        with open(self.path, encoding="utf-8") as source:
            items = json.load(source)
        items[0]["claimedAt"] = "2020-01-01T00:00:00+00:00"
        with open(self.path, "w", encoding="utf-8") as target:
            json.dump(items, target, ensure_ascii=False)
        reclaimed = self.response(RECIPIENT, {"action": "claim"})["relay"]
        self.assertEqual(reclaimed["id"], claimed["id"])
        self.assertNotEqual(reclaimed["claimToken"], claimed["claimToken"])


if __name__ == "__main__":
    unittest.main()
