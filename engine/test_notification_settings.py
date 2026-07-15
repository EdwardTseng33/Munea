#!/usr/bin/env python3
"""通知中心設定測試（2026-07-15 Edward 定稿）：
①沒存過設定＝不阻擋、分類全開 ②設定存取冪等 ③總開關/分類開關真的擋發送
④安全通知只管本人手機（家人收件人走自己的設定）⑤推播一律 public 文案。"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("GEMINI_API_KEY", "notification-settings-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
_TMP = tempfile.mkdtemp(prefix="munea-notif-settings-")
for _env, _name in (
    ("MUNEA_NOTIFICATION_SETTINGS_PATH", "notification_settings.json"),
    ("MUNEA_NOTIFICATION_EVENTS_PATH", "notification_events.json"),
    ("MUNEA_NOTIFICATION_DELIVERIES_PATH", "notification_deliveries.json"),
    ("MUNEA_PUSH_DEVICES_PATH", "push_devices.json"),
):
    os.environ[_env] = os.path.join(_TMP, _name)
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
import notification_service  # noqa: E402
import apns_service  # noqa: E402


class SettingsDefaultsAndRoundtripTest(unittest.TestCase):
    def test_defaults_allow_categories_on(self):
        # 沒存過設定＝覆蓋層不阻擋（預設關的 UX 由 App 端「未開啟不註冊裝置」實現）
        settings = server.load_notification_settings("person-x")
        self.assertTrue(settings["pushEnabled"])
        self.assertEqual(settings["categories"],
                         {c: True for c in notification_service.NOTIFICATION_CATEGORIES})

    def test_set_and_get_roundtrip(self):
        server.save_notification_settings(
            {"pushEnabled": True, "categories": {"medication": False, "bogus": False}},
            person_id="person-y")
        settings = server.load_notification_settings("person-y")
        self.assertTrue(settings["pushEnabled"])
        self.assertFalse(settings["categories"]["medication"])
        self.assertTrue(settings["categories"]["clinic"])
        self.assertNotIn("bogus", settings["categories"])

    def test_response_get_and_set(self):
        result = server.notification_settings_response(
            {"action": "set", "pushEnabled": True})
        self.assertTrue(result["ok"] and result["settings"]["pushEnabled"])
        self.assertTrue(server.notification_settings_response({})["settings"]["pushEnabled"])


class PushAllowedTest(unittest.TestCase):
    def test_master_switch_blocks_everything(self):
        settings = {"pushEnabled": False, "categories": {}}
        for event_type in ("medication_due", "health_alert", "family_relay"):
            self.assertFalse(notification_service.push_allowed(settings, event_type))

    def test_category_switch_blocks_only_its_type(self):
        settings = {"pushEnabled": True, "categories": {"medication": False}}
        self.assertFalse(notification_service.push_allowed(settings, "medication_due"))
        self.assertTrue(notification_service.push_allowed(settings, "clinic_upcoming"))
        self.assertTrue(notification_service.push_allowed(settings, "family_relay"))

    def test_safety_switch_is_per_recipient(self):
        """長輩關掉 safety 只影響長輩自己的手機；家人收件人用家人自己的設定。"""
        server.save_notification_settings(
            {"pushEnabled": True, "categories": {"safety": False}}, person_id="elder-1")
        server.save_notification_settings(
            {"pushEnabled": True}, person_id="family-1")
        elder = server.load_notification_settings("elder-1")
        family = server.load_notification_settings("family-1")
        self.assertFalse(notification_service.push_allowed(elder, "health_alert"))
        self.assertTrue(notification_service.push_allowed(family, "health_alert"))


class DrainSuppressionTest(unittest.TestCase):
    def test_drain_suppresses_when_settings_block(self):
        completed = []

        class FakeAdapter:
            def claim_notification_deliveries(self, limit=50):
                return [{"delivery_id": "d1", "recipient_person_id": "elder-1",
                         "event_type": "medication_due"}]

            def complete_notification_delivery(self, delivery_id, status, **kw):
                completed.append((delivery_id, status, kw.get("error_code")))

        result = apns_service.drain_outbox(
            FakeAdapter(), sender=object(),
            push_allowed_fn=lambda d: False)
        self.assertEqual(result["summary"]["suppressed"], 1)
        self.assertEqual(completed, [("d1", "suppressed", "push_disabled_by_settings")])


class PublicCopyAlwaysTest(unittest.TestCase):
    def test_payload_ignores_show_sensitive_flag(self):
        payload = apns_service.build_payload({
            "sensitivity": "health_sensitive", "show_sensitive_content": True,
            "title": "該吃脂溶錠了", "body": "脂溶錠 2 顆",
            "public_title": "沐寧提醒", "public_body": "你的健康提醒到了，解鎖後查看。",
        })
        alert = payload["aps"]["alert"]
        self.assertNotIn("脂溶錠", alert["title"] + alert["body"])
        self.assertEqual(alert["title"], "沐寧提醒")


if __name__ == "__main__":
    unittest.main(verbosity=2)
