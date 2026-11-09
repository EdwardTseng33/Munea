#!/usr/bin/env python3
"""緊急聯絡人通知（2026-11-09 1.0.72）：
一、選人只收同家庭圈成員，最多 3 位、排除自己
二、存檔按人合併（vitals 同招）
三、派送去重／限頻（30 分鐘同桶不多排）
四、鎖定畫面文案完全通用（無健康數值／逐字稿／長輩名）
五、守護腦 hook：familyNotificationCandidate 才派送、沒 person_id 不派送。"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("GEMINI_API_KEY", "safety-contacts-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
_TMP = tempfile.mkdtemp(prefix="munea-safety-contacts-")
for _env, _name in (
    ("MUNEA_FAMILY_STATE_STORE_PATH", "family_state_store.json"),
    ("MUNEA_APP_PROFILE_STORE_PATH", "app_profile_store.json"),
    ("MUNEA_NOTIFICATION_EVENTS_PATH", "notification_events.json"),
    ("MUNEA_NOTIFICATION_DELIVERIES_PATH", "notification_deliveries.json"),
    ("MUNEA_PUSH_DEVICES_PATH", "push_devices.json"),
    ("MUNEA_NOTIFICATION_SETTINGS_PATH", "notification_settings.json"),
):
    os.environ[_env] = os.path.join(_TMP, _name)
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
import notification_service  # noqa: E402


def _seed_members(*ids_and_names):
    for pid, name in ids_and_names:
        server.save_family_member({"id": pid, "displayName": name, "role": "family_contact"})


class SelectionValidationTest(unittest.TestCase):
    def test_filters_non_members_and_self_and_caps_at_three(self):
        _seed_members(("m1", "大女兒"), ("m2", "二兒子"), ("m3", "小兒子"), ("m4", "媳婦"))
        cleaned = server.normalize_safety_contacts_selection(
            "elder-a", "shared",
            ["m1", "m2", "m3", "m4", "stranger", "elder-a", "m1"],
        )
        self.assertEqual(cleaned, ["m1", "m2", "m3"])

    def test_no_members_rejects_everything(self):
        cleaned = server.normalize_safety_contacts_selection("elder-b", "shared-empty-group", ["ghost-1"])
        self.assertEqual(cleaned, [])


class SaveLoadRoundtripTest(unittest.TestCase):
    def test_save_merges_by_person_not_overwrite(self):
        _seed_members(("c1", "大女兒"), ("c2", "二兒子"))
        server.save_safety_contacts_entry("shared", "elder-x", ["c1"])
        server.save_safety_contacts_entry("shared", "elder-y", ["c2"])
        entry = server.load_safety_contacts_entry("shared")
        self.assertEqual(entry.get("elder-x"), ["c1"])
        self.assertEqual(entry.get("elder-y"), ["c2"])

    def test_response_save_then_load_roundtrip(self):
        _seed_members(("c3", "媳婦"))
        save_result = server.safety_contacts_response({
            "action": "save", "personId": "elder-z", "familyGroupId": "shared",
            "contactPersonIds": ["c3", "nobody"],
        })
        self.assertTrue(save_result["ok"])
        self.assertEqual(save_result["contactPersonIds"], ["c3"])
        load_result = server.safety_contacts_response({"action": "load", "personId": "elder-z", "familyGroupId": "shared"})
        self.assertEqual(load_result["contactPersonIds"], ["c3"])


class DispatchDedupeTest(unittest.TestCase):
    def test_no_contacts_is_clean_noop(self):
        result = server.dispatch_safety_alert("elder-lonely", "vitals")
        self.assertEqual(result, {"queued": 0, "contactCount": 0})

    def test_unknown_category_is_clean_noop(self):
        result = server.dispatch_safety_alert("elder-x", "something_else")
        self.assertEqual(result, {"queued": 0, "contactCount": 0})

    def test_dispatch_dedupes_within_same_time_bucket(self):
        _seed_members(("d1", "大女兒"), ("d2", "二兒子"))
        server.save_safety_contacts_entry("shared", "elder-dedupe", ["d1", "d2"])
        first = server.dispatch_safety_alert("elder-dedupe", "guardian")
        second = server.dispatch_safety_alert("elder-dedupe", "guardian")
        self.assertEqual(first["contactCount"], 2)
        self.assertEqual(second["contactCount"], 2)
        events, _backend = server.load_notification_events(limit=200)
        matching = [e for e in events if e.get("actorPersonId") == "elder-dedupe"]
        self.assertEqual(len(matching), 2)

    def test_lock_screen_has_no_sensitive_specifics(self):
        _seed_members(("e1", "大女兒"))
        server.save_safety_contacts_entry("shared", "elder-privacy", ["e1"])
        server.dispatch_safety_alert("elder-privacy", "vitals")
        events, _backend = server.load_notification_events(limit=200)
        ev = next(e for e in events if e.get("actorPersonId") == "elder-privacy")
        lock_title, lock_body = notification_service.lock_screen_content(ev, show_sensitive_content=False)
        self.assertEqual(lock_title, "沐寧提醒")
        self.assertNotIn("elder-privacy", lock_body)
        self.assertNotIn("血壓", lock_body)
        self.assertNotIn("心率", lock_body)
        self.assertEqual(ev["sensitivity"], "health_sensitive")
        self.assertEqual(ev["eventType"], "health_alert")


class SafetyAlertEndpointGuardTest(unittest.TestCase):
    def test_guardian_category_rejected_from_public_endpoint(self):
        result = server.safety_alert_response({"category": "guardian", "personId": "elder-1"})
        self.assertEqual(result, {"ok": False, "error": "category_not_allowed"})

    def test_vitals_category_allowed(self):
        _seed_members(("f1", "大女兒"))
        server.save_safety_contacts_entry("shared", "elder-vitals", ["f1"])
        result = server.safety_alert_response({
            "category": "vitals", "personId": "elder-vitals", "familyGroupId": "shared",
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["queued"], 1)


class ReadinessTest(unittest.TestCase):
    def test_readiness_reflects_push_device_state(self):
        device = notification_service.normalize_device({
            "personId": "ready-contact", "accountId": "acc-1", "authUserId": "auth-1",
            "token": "b" * 64, "bundleId": "net.munea.app",
            "permissionStatus": "authorized", "notificationsEnabled": True,
        })
        server.save_push_device(device)
        readiness = server.safety_contacts_readiness(["ready-contact", "not-ready-contact"])
        self.assertEqual(readiness, {"ready-contact": True, "not-ready-contact": False})


class GuardianHookTest(unittest.TestCase):
    """守護腦 high/critical -> server.dispatch_safety_alert 的接線（2026-11-09）：
    familyNotificationCandidate 為真且有 person_id 才派送；protection_event／沒 person_id 都不派送。"""

    def setUp(self):
        import live_voice_server as voice
        self.voice = voice
        self.calls = []
        self._original_dispatch = server.dispatch_safety_alert

        def _fake_dispatch(person_id, category, **kw):
            self.calls.append((person_id, category))
            return {"queued": 0, "contactCount": 0}

        server.dispatch_safety_alert = _fake_dispatch

    def tearDown(self):
        server.dispatch_safety_alert = self._original_dispatch

    def _risk(self, level, category, family_candidate, protection_event=False):
        return {
            "risk": {
                "level": level, "categories": [category],
                "requiresAuditEvent": True, "requiresHumanEscalation": level in ("high", "critical"),
                "protectionEvent": protection_event,
            },
            "responsePolicy": {"familyNotificationCandidate": family_candidate},
        }

    def test_dispatches_for_high_risk_with_person_id(self):
        self.voice.guardian_record_and_alert(
            "user", 1, self._risk("high", "medical_emergency_signal", True),
            record_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None,
            person_id="elder-call-1",
        )
        self.assertEqual(self.calls, [("elder-call-1", "guardian")])

    def test_skips_without_person_id(self):
        self.voice.guardian_record_and_alert(
            "user", 1, self._risk("high", "medical_emergency_signal", True),
            record_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None,
            person_id=None,
        )
        self.assertEqual(self.calls, [])

    def test_skips_protection_event_even_with_person_id(self):
        self.voice.guardian_record_and_alert(
            "user", 1, self._risk("high", "protection_event", False, protection_event=True),
            record_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None,
            person_id="elder-call-2",
        )
        self.assertEqual(self.calls, [])

    def test_skips_low_level_risk(self):
        self.voice.guardian_record_and_alert(
            "user", 1, self._risk("low", "emotional_distress", False),
            record_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None,
            person_id="elder-call-3",
        )
        self.assertEqual(self.calls, [])

    def test_dispatch_failure_does_not_raise(self):
        def _boom(*a, **k):
            raise RuntimeError("boom")

        server.dispatch_safety_alert = _boom
        try:
            self.voice.guardian_record_and_alert(
                "user", 1, self._risk("critical", "self_harm_crisis", True),
                record_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None,
                person_id="elder-call-4",
            )
        except Exception as e:
            self.fail("guardian_record_and_alert must never raise, got: %s" % e)


if __name__ == "__main__":
    unittest.main(verbosity=2)
