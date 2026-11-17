#!/usr/bin/env python3
"""通話中守護腦亮燈改走 Brain（2026-11-18）。

查到的病：Voice 那台沒有雲端鑰匙、認不出來電者。原本亮燈紀錄寫在 Voice 本機暫存檔（家人週摘要、機構提醒都看不到），
「通知緊急聯絡人」在 Voice 本機也查不到聯絡人（等於沒發）。

守的線：
  一、有來電者身分且 Brain 通道設好 → 交給 Brain（/voice/guardian-event），Voice 本機不記、不發。
  二、寧寧自己講的話（who=ai）照記、標 who=ai，但不會要求通知家人。
  三、沒有來電者身分 → 退回本機舊寫法；Brain 送不出去 → 絕不拋例外。
  四、Brain 端：認不出人就不記不發；長輩本人說、而且是通知候選才通知；等級亂填一律當 none。
  五、家人週摘要與機構提醒都不把 who=ai 的亮燈算進去。
跑法：python -m unittest test_voice_guardian_brain_route
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "voice-guardian-brain-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
_TMP = tempfile.mkdtemp(prefix="munea-voice-guardian-brain-")
os.environ["MUNEA_PRODUCT_EVENTS_PATH"] = os.path.join(_TMP, "product_events.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server  # noqa: E402


def _risk(level, category, family_candidate, audit=True):
    return {
        "risk": {"level": level, "categories": [category], "requiresAuditEvent": audit,
                 "requiresHumanEscalation": level in ("high", "critical"), "protectionEvent": category == "protection_event"},
        "responsePolicy": {"familyNotificationCandidate": family_candidate,
                           "protectionLine": "113" if category == "protection_event" else None},
    }


class VoiceSideTests(unittest.TestCase):
    def setUp(self):
        import live_voice_server as voice
        self.voice = voice
        self.local_dispatch, self.local_record, self.posted = [], [], []
        self._orig_dispatch = server.dispatch_safety_alert
        self._orig_append = server.append_product_event
        server.dispatch_safety_alert = lambda pid, cat, **kw: self.local_dispatch.append((pid, cat)) or {"queued": 0}
        server.append_product_event = lambda ev: self.local_record.append(ev) or ev

    def tearDown(self):
        server.dispatch_safety_alert = self._orig_dispatch
        server.append_product_event = self._orig_append

    def _post(self, payload):
        self.posted.append(payload)
        return {"ok": True, "identityResolved": True, "recorded": True, "dispatch": {"queued": 1}}

    def test_user_high_risk_goes_to_brain_not_local(self):
        self.voice.guardian_record_and_alert("user", 1, _risk("high", "medical_emergency_signal", True),
                                             alert_fn=lambda *a, **k: None, person_id="auth-user-1", brain_post=self._post)
        self.assertEqual(len(self.posted), 1)
        p = self.posted[0]
        self.assertEqual((p["userId"], p["level"], p["who"], p["familyNotificationCandidate"], p["record"]),
                         ("auth-user-1", "high", "user", True, True))
        self.assertEqual(self.local_dispatch, [])     # 不在 Voice 本機發
        self.assertEqual(self.local_record, [])       # 不在 Voice 本機記

    def test_ai_speech_is_recorded_but_never_asks_to_notify_family(self):
        self.voice.guardian_record_and_alert("ai", 1, _risk("high", "medical_emergency_signal", True),
                                             alert_fn=lambda *a, **k: None, person_id="auth-user-1", brain_post=self._post)
        self.assertEqual(len(self.posted), 1)
        self.assertEqual((self.posted[0]["who"], self.posted[0]["familyNotificationCandidate"]), ("ai", False))
        self.assertEqual(self.local_dispatch, [])

    def test_ai_speech_never_dispatches_on_the_local_path_either(self):
        self.voice.guardian_record_and_alert("ai", 1, _risk("critical", "self_harm_crisis", True),
                                             record_fn=lambda *a, **k: None, alert_fn=lambda *a, **k: None, person_id="elder-1")
        self.assertEqual(self.local_dispatch, [])

    def test_without_caller_identity_falls_back_to_local_record(self):
        self.voice.guardian_record_and_alert("user", 1, _risk("high", "medical_emergency_signal", True),
                                             alert_fn=lambda *a, **k: None, person_id=None, brain_post=self._post)
        self.assertEqual(self.posted, [])
        self.assertEqual(len(self.local_record), 1)
        self.assertEqual(self.local_record[0]["properties"]["who"], "user")

    def test_brain_failure_never_raises_and_does_not_double_send_locally(self):
        def boom(_payload):
            raise RuntimeError("brain down")
        try:
            self.voice.guardian_record_and_alert("user", 1, _risk("critical", "self_harm_crisis", True),
                                                 alert_fn=lambda *a, **k: None, person_id="auth-user-2", brain_post=boom)
        except Exception as e:  # noqa: BLE001
            self.fail("must never raise: %s" % e)
        self.assertEqual(self.local_dispatch, [])

    def test_uses_internal_channel_when_configured(self):
        captured = {}
        def fake_post_internal(url, secret, path, body, timeout=8, app_key=""):
            captured.update(url=url, path=path, body=body)
            return {"ok": True, "identityResolved": True, "recorded": True, "dispatch": None}
        with patch.dict(os.environ, {"MUNEA_BRAIN_INTERNAL_URL": "https://brain.internal", "MUNEA_VOICE_BRAIN_SECRET": "s3cret"}), \
                patch.object(self.voice, "post_internal", fake_post_internal):
            self.voice.guardian_record_and_alert("user", 1, _risk("high", "medical_emergency_signal", True),
                                                 alert_fn=lambda *a, **k: None, person_id="auth-user-3")
        self.assertEqual(captured.get("path"), "/voice/guardian-event")
        self.assertEqual(captured["body"]["userId"], "auth-user-3")
        self.assertEqual(self.local_record, [])


class BrainSideTests(unittest.TestCase):
    def setUp(self):
        self.recorded, self.dispatched = [], []
        self._patches = [
            patch.object(server, "append_product_event", side_effect=lambda ev: self.recorded.append(ev) or ev),
            patch.object(server, "dispatch_safety_alert", side_effect=lambda pid, cat, **kw: self.dispatched.append((pid, cat)) or {"queued": 2}),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def call(self, data, person="person-1"):
        with patch.object(server, "_voice_identity_scope", return_value=(None, person)):
            return server.voice_guardian_event_response(data)

    def test_user_candidate_is_recorded_and_contacts_notified(self):
        out = self.call({"userId": "u1", "level": "high", "categories": ["medical_emergency_signal"], "who": "user",
                         "familyNotificationCandidate": True})
        self.assertEqual((out["identityResolved"], out["recorded"]), (True, True))
        self.assertEqual(self.dispatched, [("person-1", "guardian")])
        props = self.recorded[0]["properties"]
        self.assertEqual((props["who"], props["riskLevel"], props["source"]), ("user", "high", "live_voice"))

    def test_ai_speech_recorded_but_no_contacts_notified(self):
        self.call({"userId": "u1", "level": "high", "categories": ["medical_emergency_signal"], "who": "ai",
                   "familyNotificationCandidate": True})
        self.assertEqual(self.dispatched, [])
        self.assertEqual(self.recorded[0]["properties"]["who"], "ai")

    def test_unknown_caller_records_nothing(self):
        out = self.call({"userId": "ghost", "level": "critical", "who": "user", "familyNotificationCandidate": True}, person=None)
        self.assertEqual((out["identityResolved"], out["recorded"]), (False, False))
        self.assertEqual((self.recorded, self.dispatched), ([], []))

    def test_bad_level_becomes_none_and_record_flag_is_respected(self):
        self.call({"userId": "u1", "level": "NUCLEAR", "who": "user"})
        self.assertEqual(self.recorded[0]["properties"]["riskLevel"], "none")
        self.recorded.clear()
        self.call({"userId": "u1", "level": "high", "who": "user", "familyNotificationCandidate": True, "record": False})
        self.assertEqual(self.recorded, [])
        self.assertEqual(len(self.dispatched), 1)

    def test_route_is_behind_the_internal_secret(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), encoding="utf-8").read()
        gate = src[src.index('if request_path in ("/voice/call-memory"'):src.index('self._json(_voice_internal[request_path](data))')]
        self.assertIn('"/voice/guardian-event"', gate)
        self.assertIn('"/voice/guardian-event": voice_guardian_event_response', gate)


class ProtectionLineTests(unittest.TestCase):
    """受暴受剝削：加害人可能是家人。一句話同時提到受暴與急症／想不開，也一律不通知家庭圈（#717 信任關卡）。"""

    def test_mixed_sentences_never_become_family_candidates(self):
        import model_router
        for text in ("他打我，我胸口好痛喘不過氣", "被家暴好想死", "兒子把我錢拿走了，我很喘"):
            r = model_router.guardian_evaluate_response({"text": text, "effort": "quick"})
            self.assertIn(r["risk"]["level"], ("high", "critical"), text)
            self.assertTrue(r["risk"]["protectionMentioned"], text)
            self.assertFalse(r["responsePolicy"]["familyNotificationCandidate"], text)

    def test_plain_emergencies_still_notify_family(self):
        import model_router
        for text in ("我胸口好痛喘不過氣", "我不想活了"):
            r = model_router.guardian_evaluate_response({"text": text, "effort": "quick"})
            self.assertTrue(r["responsePolicy"]["familyNotificationCandidate"], text)
            self.assertFalse(r["risk"]["protectionMentioned"], text)

    def test_whole_path_never_asks_brain_to_notify_family(self):
        import live_voice_server as voice
        import model_router
        posted = []
        result = model_router.guardian_evaluate_response({"text": "他打我，我胸口好痛喘不過氣", "effort": "quick"})
        voice.guardian_record_and_alert("user", 1, result, alert_fn=lambda *a, **k: None, person_id="u1",
                                        brain_post=lambda p: posted.append(p) or {"identityResolved": True, "recorded": True})
        self.assertFalse(posted[0]["familyNotificationCandidate"])
        self.assertTrue(posted[0]["protectionMentioned"])


class VoiceSideProtectionTests(unittest.TestCase):
    def test_voice_blocks_family_even_if_the_policy_said_yes(self):
        import live_voice_server as voice
        posted = []
        result = _risk("high", "medical_emergency_signal", True)
        result["risk"]["protectionMentioned"] = True                      # 規則層說可以通知，但句子提到受暴
        voice.guardian_record_and_alert("user", 1, result, alert_fn=lambda *a, **k: None, person_id="u1",
                                        brain_post=lambda p: posted.append(p) or {"identityResolved": True, "recorded": True})
        self.assertFalse(posted[0]["familyNotificationCandidate"])

    def test_ai_second_look_path_blocks_family_when_abuse_is_mentioned(self):
        import asyncio
        import live_voice_server as voice
        captured = []
        low = {"risk": {"level": "low", "categories": ["emotional_distress"], "requiresAuditEvent": False},
               "responsePolicy": {"softSignalForReview": True, "reviewForced": False}}
        originals = (voice.guardian_scan_text, voice.perception_engine.guardian_semantic_review, voice._guardian_side_effects)
        voice.guardian_scan_text = lambda text: low
        voice.perception_engine.guardian_semantic_review = lambda *a, **k: {"level": "high", "category": "medical_emergency", "confidence": 0.9}
        voice._guardian_side_effects = lambda cid, who, result, pid, st, key: captured.append(result)
        try:
            st = voice._new_call_state()
            st["memory_scope"] = "voice-u1"
            asyncio.run(voice.guardian_watch(1, "user", "他昨天又打我了，現在胸口悶悶的", st, None, turn_id=1, allow_cue=True))
        finally:
            voice.guardian_scan_text, voice.perception_engine.guardian_semantic_review, voice._guardian_side_effects = originals
        sem = [r for r in captured if r["risk"]["level"] == "high"]
        self.assertTrue(sem)
        self.assertFalse(sem[0]["responsePolicy"]["familyNotificationCandidate"])
        self.assertTrue(sem[0]["risk"]["protectionMentioned"])


class BrainLocksTests(unittest.TestCase):
    def setUp(self):
        self.recorded, self.dispatched = [], []
        self._patches = [
            patch.object(server, "append_product_event", side_effect=lambda ev: self.recorded.append(ev) or ev),
            patch.object(server, "dispatch_safety_alert",
                         side_effect=lambda pid, cat, family_group_id=None, **kw: self.dispatched.append((pid, cat, family_group_id)) or {"queued": 1}),
            patch.object(server, "_current_family_group_id", return_value="group-of-caller"),
            patch.object(server, "_voice_identity_scope", return_value=(None, "person-1")),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_brain_refuses_to_notify_when_abuse_is_mentioned(self):
        for extra in ({"protectionMentioned": True}, {"protectionEvent": True}, {"categories": ["protection_event"]}):
            server.voice_guardian_event_response({"userId": "u1", "level": "high", "who": "user",
                                                  "familyNotificationCandidate": True, **extra})
        self.assertEqual(self.dispatched, [])

    def test_only_high_or_critical_notifies(self):
        server.voice_guardian_event_response({"userId": "u1", "level": "medium", "who": "user", "familyNotificationCandidate": True})
        self.assertEqual(self.dispatched, [])

    def test_record_and_dispatch_use_the_callers_own_person_and_circle(self):
        server.voice_guardian_event_response({"userId": "u1", "level": "critical", "who": "user", "familyNotificationCandidate": True})
        self.assertEqual(self.dispatched, [("person-1", "guardian", "group-of-caller")])
        self.assertEqual((self.recorded[0]["personId"], self.recorded[0]["familyGroupId"]), ("person-1", "group-of-caller"))

    def test_record_failure_does_not_swallow_the_notification(self):
        with patch.object(server, "append_product_event", side_effect=RuntimeError("db down")):
            out = server.voice_guardian_event_response({"userId": "u1", "level": "high", "who": "user", "familyNotificationCandidate": True})
        self.assertFalse(out["recorded"])
        self.assertEqual(len(self.dispatched), 1)


class DeliveryFailureTests(unittest.TestCase):
    def setUp(self):
        import live_voice_server as voice
        self.voice = voice
        self.alerts = []

    def _alert(self, *args, **kw):
        self.alerts.append(args)

    def test_high_risk_retries_once_then_raises_an_internal_alert_without_ids(self):
        calls = []
        def boom(payload):
            calls.append(payload)
            raise RuntimeError("brain down")
        self.voice.guardian_record_and_alert("user", 1, _risk("critical", "self_harm_crisis", True), alert_fn=self._alert,
                                             person_id="auth-user-secret", brain_post=boom)
        self.assertEqual(len(calls), 2)                                   # 重試一次
        failed = [a for a in self.alerts if a[1] == "guardian:delivery_failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("reason=brain_unreachable", failed[0][2])
        self.assertNotIn("auth-user-secret", " ".join(map(str, self.alerts)))   # 不帶任何 ID

    def test_unresolved_caller_and_unqueued_contacts_are_reported(self):
        self.voice.guardian_record_and_alert("user", 1, _risk("high", "medical_emergency_signal", True), alert_fn=self._alert,
                                             person_id="u", brain_post=lambda p: {"identityResolved": False})
        self.voice.guardian_record_and_alert("user", 1, _risk("high", "medical_emergency_signal", True), alert_fn=self._alert,
                                             person_id="u", brain_post=lambda p: {"identityResolved": True, "recorded": True,
                                                                                    "dispatch": {"contactCount": 2, "queued": 0}})
        reasons = [a[2] for a in self.alerts if a[1] == "guardian:delivery_failed"]
        self.assertTrue(any("caller_not_resolved" in r for r in reasons))
        self.assertTrue(any("contacts_not_queued" in r for r in reasons))

    def test_low_risk_failure_does_not_alert(self):
        self.voice.guardian_record_and_alert("user", 1, _risk("medium", "medical_boundary", False), alert_fn=self._alert,
                                             person_id="u", brain_post=lambda p: (_ for _ in ()).throw(RuntimeError("x")))
        self.assertFalse([a for a in self.alerts if a[1] == "guardian:delivery_failed"])


class DedupeTests(unittest.TestCase):
    def test_same_turn_same_category_is_sent_once(self):
        import live_voice_server as voice
        calls = []
        original = voice.guardian_record_and_alert
        voice.guardian_record_and_alert = lambda *a, **k: calls.append(a)
        try:
            st = {}
            for _ in range(5):                                            # 字幕每進一小段就重判一次
                voice._guardian_side_effects(1, "user", {}, "u", st, (3, "user", "high", ("medical_emergency_signal",)))
            voice._guardian_side_effects(1, "user", {}, "u", st, (4, "user", "high", ("medical_emergency_signal",)))
        finally:
            voice.guardian_record_and_alert = original
        self.assertEqual(len(calls), 2)                                   # 第 3 輪一次、第 4 輪一次


class AiSpeechNotCountedTests(unittest.TestCase):
    def test_org_loader_skips_ai_speech(self):
        import org_api
        fake = {"productEvents": [
            {"eventName": "guardian_risk_evaluated", "accountId": "a1", "personId": "p1", "eventTime": "2026-11-17T10:00:00Z",
             "properties": {"riskLevel": "high", "categories": ["medical_emergency_signal"], "who": "ai"}},
            {"eventName": "guardian_risk_evaluated", "accountId": "a1", "personId": "p1", "eventTime": "2026-11-17T11:00:00Z",
             "properties": {"riskLevel": "high", "categories": ["self_harm_crisis"], "who": "user"}},
        ]}
        with patch.object(org_api.org_portal, "load_cohort_activity", return_value=fake):
            events = org_api.default_loaders()["guardianEvents"](["a1"], "2026-11-10T00:00:00Z")
        self.assertEqual([e["categories"] for e in events], [["self_harm_crisis"]])

    def test_family_care_week_skips_ai_speech(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), encoding="utf-8").read()
        block = src[src.index('for ev in load_product_events(since_iso=since_iso, limit=2000) or []:'):]
        block = block[:block.index("except Exception as e:")]
        self.assertIn('props.get("who") == "ai"', block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
