#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import apns_service  # noqa: E402


class FakeAdapter:
    def __init__(self, deliveries):
        self.deliveries = deliveries
        self.completed = []

    def claim_notification_deliveries(self, limit=50):
        return self.deliveries[:limit]

    def complete_notification_delivery(self, delivery_id, status, **kwargs):
        self.completed.append((delivery_id, status, kwargs))


class FakeSender:
    def __init__(self, results):
        self.results = list(results)

    def send(self, _delivery):
        return self.results.pop(0)


class APNSServiceTests(unittest.TestCase):
    def delivery(self, **overrides):
        base = {
            "delivery_id": "delivery-1",
            "event_id": "event-1",
            "event_type": "medication_due",
            "resource_id": "dose-1",
            "title": "晚餐後要吃降血壓藥",
            "body": "請服用 1 顆降血壓藥。",
            "public_title": "沐寧提醒",
            "public_body": "你的健康提醒到了，解鎖後查看。",
            "sensitivity": "health_sensitive",
            "deep_link": "munea://medications/dose-1",
            "show_sensitive_content": False,
        }
        return {**base, **overrides}

    def test_sensitive_details_are_hidden_by_default(self):
        payload = apns_service.build_payload(self.delivery())
        alert = payload["aps"]["alert"]
        self.assertEqual(alert["title"], "沐寧提醒")
        self.assertNotIn("降血壓藥", alert["body"])
        self.assertEqual(payload["deepLink"], "munea://medications/dose-1")

    def test_sensitive_opt_in_flag_is_ignored(self):
        # 2026-07-15 Edward 拍板拿掉「鎖定畫面內容」開關：推播一律通用文案、
        # 藥名/健康細節只在 App 內看；就算舊裝置還帶著 opt-in 旗標也不理會。
        payload = apns_service.build_payload(self.delivery(show_sensitive_content=True))
        alert = payload["aps"]["alert"]
        self.assertNotIn("降血壓藥", alert["title"] + alert["body"])
        self.assertEqual(alert["title"], "沐寧提醒")

    def test_apns_response_classification(self):
        self.assertEqual(apns_service.classify_response(200, {}, {"apns-id": "abc"})["status"], "accepted")
        self.assertEqual(apns_service.classify_response(410, {"reason": "Unregistered"})["status"], "invalid_token")
        retry = apns_service.classify_response(429, {"reason": "TooManyRequests"}, {"retry-after": "120"})
        self.assertEqual(retry["status"], "failed")
        self.assertEqual(retry["retryAfterSeconds"], 120)
        self.assertEqual(apns_service.classify_response(403, {"reason": "InvalidProviderToken"})["status"], "suppressed")

    def test_drain_writes_every_result_back_to_outbox(self):
        adapter = FakeAdapter([
            self.delivery(delivery_id="d1"),
            self.delivery(delivery_id="d2"),
            self.delivery(delivery_id="d3"),
        ])
        sender = FakeSender([
            {"status": "accepted", "apnsId": "a1"},
            {"status": "invalid_token", "errorCode": "Unregistered"},
            {"status": "failed", "errorCode": "ServiceUnavailable", "retryAfterSeconds": 60},
        ])
        result = apns_service.drain_outbox(adapter, sender=sender)
        self.assertEqual(result["summary"]["claimed"], 3)
        self.assertEqual(result["summary"]["accepted"], 1)
        self.assertEqual(result["summary"]["invalidToken"], 1)
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual([item[1] for item in adapter.completed], ["accepted", "invalid_token", "failed"])

    def test_missing_credentials_are_reported_without_secret_values(self):
        status = apns_service.APNSConfig.from_env({}).status()
        self.assertFalse(status["enabled"])
        self.assertIn("MUNEA_APNS_KEY_ID", status["missing"])
        self.assertNotIn("private_key", status)


if __name__ == "__main__":
    unittest.main()
