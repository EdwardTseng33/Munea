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


class RelayConfirmationRuleTests(unittest.TestCase):
    """傳話要「整理過、唸回去、他點頭」才送（Edward 2026-07-31）。

    他對寧寧說的是「幫我跟他說他晚餐的藥忘記吃了」——那是講給寧寧聽的第三人稱。
    原句照送，收到的人會看到一句在講別人的話。所以要先轉成「直接對收件人說」的口氣；
    但整理會有走鐘風險，唸回去讓他點頭就是那道保險。這兩件缺一不可，所以一起守。
    """

    def setUp(self):
        with open(live_voice_server.__file__, encoding="utf-8") as source:
            self.source = source.read()

    def _relay_rule(self):
        start = self.source.index("他要傳話給家庭圈成員時")
        return self.source[start:start + 900]

    def test_relay_rule_requires_rewriting_into_second_person(self):
        rule = self._relay_rule()
        self.assertIn("直接對收件人說", rule)
        self.assertIn("第二人稱", rule)

    def test_relay_rule_keeps_meaning_locked_while_rewording(self):
        rule = self._relay_rule()
        self.assertIn("只能改說法", rule)
        for forbidden in ("不補他沒說的事", "不刪他交代的細節", "不猜他的用意"):
            self.assertIn(forbidden, rule)

    def test_relay_rule_requires_read_back_and_explicit_yes(self):
        rule = self._relay_rule()
        self.assertIn("這樣可以嗎", rule)
        self.assertIn("他明確說可以才呼叫 send_family_relay", rule)
        self.assertIn("沒得到同意就不要送", rule)

    def test_relay_rule_handles_a_correction_round(self):
        # 他說「不對，要改」的時候不能就這樣送出去，也不能默默丟掉——要重整理再確認一次
        self.assertIn("重整理、再唸一次確認", self._relay_rule())

    def test_relay_tool_description_states_the_gate(self):
        declaration = next(
            fn for tool in (live_voice_server._REMINDER_TOOLS,)
            for fn in tool.function_declarations if fn.name == "send_family_relay"
        )
        self.assertIn("明確說可以之後", declaration.description)
        self.assertIn("不要呼叫", declaration.description)
        message = declaration.parameters.properties["message"].description
        self.assertIn("直接對收件人說", message)


if __name__ == "__main__":
    unittest.main()
