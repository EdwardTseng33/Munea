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
  六、通知家人等整段話講完才決定（#717 複審）：先講症狀、後講「是他打的」也不通知；這通提過受暴，整通都不通知；
      電話掛斷就立刻決定；一通最多通知一次；寧寧自己的話不排通知。
  七、收線前把守護腦的事做完（最後幾句判完、送 Brain 的工作做完）；沒通知到走最高級告警、不帶 ID；
      沒有家庭圈的人，紀錄不會被共用快取補上別人的圈。
跑法：python -m unittest test_voice_guardian_brain_route
"""
import asyncio
import os
import sys
import tempfile
import time
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
            hit = _risk("high", "medical_emergency_signal", True)
            for _ in range(5):                                            # 字幕每進一小段就重判一次
                voice._guardian_side_effects(1, "user", hit, "u", st, (3, "user", "high", ("medical_emergency_signal",)))
            voice._guardian_side_effects(1, "user", hit, "u", st, (4, "user", "high", ("medical_emergency_signal",)))
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


class HoldFamilyNoticeTests(unittest.TestCase):
    """通知家人等整段話講完才決定（#717 複審）：字幕一小段一小段進來，長輩常先講症狀、再講原因。"""

    def setUp(self):
        import live_voice_server as voice
        self.voice = voice
        self.records, self.notices = [], []
        self._orig = (voice.guardian_record_and_alert, voice.guardian_family_notify,
                      voice.perception_engine.guardian_semantic_review, voice.GUARDIAN_FAMILY_HOLD_S)
        voice.guardian_record_and_alert = lambda who, cid, result, person_id=None, **k: self.records.append(
            (who, result["risk"].get("level"), bool(result["risk"].get("protectionMentioned")), k.get("defer_family")))
        voice.guardian_family_notify = lambda cid, pid, level, cats, **k: self.notices.append((pid, level, list(cats))) or True
        voice.perception_engine.guardian_semantic_review = lambda *a, **k: None
        voice.GUARDIAN_FAMILY_HOLD_S = 0.2

    def tearDown(self):
        v = self.voice
        (v.guardian_record_and_alert, v.guardian_family_notify,
         v.perception_engine.guardian_semantic_review, v.GUARDIAN_FAMILY_HOLD_S) = self._orig

    def _state(self):
        st = self.voice._new_call_state()
        st["memory_scope"] = "voice-auth-user-1"
        return st

    async def _speak(self, st, chunks, turn_id=1):
        buf = ""
        for c in chunks:                                                  # 字幕每進一小段，就拿整段重判一次
            buf = (buf + c)[-200:]
            await self.voice.guardian_watch(1, "user", buf, st, None, turn_id=turn_id, allow_cue=True)

    def test_symptom_first_abuse_later_never_notifies_family(self):
        async def run():
            st = self._state()
            await self._speak(st, ["我", "胸口好痛", "，喘不過氣", "，因為", "他打我"])
            await asyncio.sleep(0.5)
            await self.voice._guardian_drain_on_close(1, st)
        asyncio.run(run())
        self.assertEqual(self.notices, [])
        self.assertTrue(any(r[2] for r in self.records))                  # 後半句補記一筆、帶受暴標記
        self.assertTrue(self.records and all(r[3] for r in self.records))  # 通話中的記錄一律請 Brain 先別通知

    def test_plain_emergency_notifies_once_after_the_hold(self):
        async def run():
            st = self._state()
            await self._speak(st, ["我胸口好痛", "，喘不過氣"])
            before = list(self.notices)
            await asyncio.sleep(0.5)
            return st, before
        st, before = asyncio.run(run())
        self.assertEqual(before, [])                                      # 還在等
        self.assertEqual(len(self.notices), 1)
        self.assertEqual(self.notices[0][0], "auth-user-1")
        self.assertIn(self.notices[0][1], ("high", "critical"))
        self.assertTrue(st.get("guardian_family_notified"))

    def test_hangup_decides_right_away(self):
        self.voice.GUARDIAN_FAMILY_HOLD_S = 30
        async def run():
            st = self._state()
            await self._speak(st, ["我胸口好痛，喘不過氣"])
            t0 = time.monotonic()
            await self.voice._guardian_drain_on_close(1, st)
            return time.monotonic() - t0
        took = asyncio.run(run())
        self.assertEqual(len(self.notices), 1)
        self.assertLess(took, 5)

    def test_abuse_earlier_in_the_call_blocks_later_emergencies(self):
        async def run():
            st = self._state()
            await self._speak(st, ["他打我"], turn_id=1)
            await self._speak(st, ["我胸口好痛，喘不過氣"], turn_id=2)
            await asyncio.sleep(0.5)
            await self.voice._guardian_drain_on_close(1, st)
        asyncio.run(run())
        self.assertEqual(self.notices, [])

    def test_only_one_family_notice_per_call(self):
        async def run():
            st = self._state()
            await self._speak(st, ["我胸口好痛，喘不過氣"], turn_id=1)
            await asyncio.sleep(0.5)
            await self._speak(st, ["我不想活了"], turn_id=2)
            await asyncio.sleep(0.5)
            await self.voice._guardian_drain_on_close(1, st)
        asyncio.run(run())
        self.assertEqual(len(self.notices), 1)

    def test_ai_speech_never_queues_a_family_notice(self):
        async def run():
            st = self._state()
            await self.voice.guardian_watch(1, "ai", "胸口痛、喘不過氣要馬上打 119", st, None, turn_id=1, allow_cue=False)
            await self.voice._guardian_drain_on_close(1, st)
        asyncio.run(run())
        self.assertEqual(self.notices, [])


class CloseDrainTests(unittest.TestCase):
    """收線前把守護腦的事做完：Voice 沒開 CPU 常駐，handler 一返回背景工作就可能卡死。"""

    def test_close_waits_for_brain_work_still_in_flight(self):
        import live_voice_server as voice
        done = []
        original = voice.guardian_record_and_alert

        def slow(*a, **k):
            time.sleep(0.5)
            done.append(True)

        voice.guardian_record_and_alert = slow
        try:
            async def run():
                st = voice._new_call_state()
                voice._guardian_side_effects(1, "user", _risk("medium", "medical_boundary", False), "u", st,
                                             (1, "user", "medium", ("medical_boundary",)))
                started = list(done)
                await voice._guardian_drain_on_close(1, st)
                return started, list(done)
            started, finished = asyncio.run(run())
        finally:
            voice.guardian_record_and_alert = original
        self.assertEqual((started, finished), ([], [True]))

    def test_close_gives_the_last_sentence_a_moment_to_be_judged(self):
        import live_voice_server as voice

        async def run():
            st = voice._new_call_state()
            finished = []

            async def slow_watch():
                await asyncio.sleep(0.3)
                finished.append(True)

            voice._spawn_guardian_watch(st, slow_watch())
            await voice._guardian_drain_on_close(1, st)
            return finished
        self.assertEqual(asyncio.run(run()), [True])


    def test_handler_drains_before_cancelling_background_work(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_voice_server.py"), encoding="utf-8").read()
        block = src[src.index("        if _key_idx is not None:"):]
        block = block[:block.index('        fw = st.get("face_ws")')]
        self.assertLess(block.index("await _guardian_drain_on_close(cid, st)"), block.index('for t in st.get("bg_tasks", []):'))


class NotifyWaitTests(unittest.TestCase):
    def test_wait_sends_before_returning(self):
        import threading
        import notify
        seen = []
        with patch.object(notify, "_ALERT", "https://alerts.invalid/x"),                 patch.object(notify.urllib.request, "urlopen",
                             side_effect=lambda *a, **k: seen.append(threading.current_thread().name) or _Resp()):
            notify.alert("voice", "guardian:wait-test-%s" % time.time(), "d", critical=True, wait=True)
            sent_inline = list(seen)
        self.assertEqual(sent_inline, [threading.current_thread().name])   # 回來之前就送完、在同一條執行緒


class _Resp:
    def read(self):
        return b"ok"

class VoiceDeferTests(unittest.TestCase):
    def test_in_call_record_asks_brain_not_to_notify_yet(self):
        import live_voice_server as voice
        posted = []
        voice.guardian_record_and_alert("user", 1, _risk("high", "medical_emergency_signal", True), alert_fn=lambda *a, **k: None,
                                        person_id="u1", defer_family=True,
                                        brain_post=lambda p: posted.append(p) or {"identityResolved": True, "recorded": True})
        self.assertEqual((posted[0]["notify"], posted[0]["familyNotificationCandidate"], posted[0]["record"]), (False, True, True))

    def test_deferred_record_does_not_report_contacts_not_queued(self):
        import live_voice_server as voice
        alerts = []
        voice.guardian_record_and_alert("user", 1, _risk("high", "medical_emergency_signal", True),
                                        alert_fn=lambda *a, **k: alerts.append(a), person_id="u1", defer_family=True,
                                        brain_post=lambda p: {"identityResolved": True, "recorded": True,
                                                              "dispatch": {"contactCount": 2, "queued": 0}})
        self.assertFalse([a for a in alerts if a[1] == "guardian:delivery_failed"])

    def test_family_notice_payload_and_urgent_failure_alert(self):
        import live_voice_server as voice
        posted, alerts = [], []
        ok = voice.guardian_family_notify(1, "auth-user-secret", "critical", ["self_harm_crisis"],
                                          alert_fn=lambda *a, **k: alerts.append((a, k)),
                                          brain_post=lambda p: posted.append(p) or {"identityResolved": True,
                                                                                    "dispatch": {"queued": 1, "contactCount": 1}})
        self.assertTrue(ok)
        self.assertEqual((posted[0]["record"], posted[0]["notify"], posted[0]["who"], posted[0]["familyNotificationCandidate"]),
                         (False, True, "user", True))
        calls = []

        def boom(payload):
            calls.append(payload)
            raise RuntimeError("brain down")

        ok = voice.guardian_family_notify(1, "auth-user-secret", "critical", ["self_harm_crisis"],
                                          alert_fn=lambda *a, **k: alerts.append((a, k)), brain_post=boom)
        self.assertFalse(ok)
        self.assertEqual(len(calls), 2)                                   # 重試一次
        failed = [x for x in alerts if x[0][1] == "guardian:delivery_failed"]
        self.assertEqual(len(failed), 1)
        self.assertTrue(failed[0][1].get("critical"))                     # 「叫不到人」那一級
        self.assertIn("reason=brain_unreachable", failed[0][0][2])
        self.assertNotIn("auth-user-secret", str(alerts))                # 不帶任何 ID

    def test_unqueued_contacts_on_the_notice_are_reported(self):
        import live_voice_server as voice
        alerts = []
        ok = voice.guardian_family_notify(1, "u", "high", ["medical_emergency_signal"],
                                          alert_fn=lambda *a, **k: alerts.append(a),
                                          brain_post=lambda p: {"identityResolved": True, "dispatch": {"queued": 0, "contactCount": 2}})
        self.assertFalse(ok)
        self.assertTrue(any("contacts_not_queued" in a[2] for a in alerts if a[1] == "guardian:delivery_failed"))


class BrainNotifyFlagTests(unittest.TestCase):
    def setUp(self):
        self.recorded, self.dispatched = [], []
        self._patches = [
            patch.object(server, "append_product_event", side_effect=lambda ev: self.recorded.append(ev) or ev),
            patch.object(server, "dispatch_safety_alert",
                         side_effect=lambda pid, cat, family_group_id=None, **kw: self.dispatched.append((pid, cat)) or {"queued": 1}),
            patch.object(server, "_voice_identity_scope", return_value=(None, "person-1")),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_notify_false_records_but_does_not_notify(self):
        out = server.voice_guardian_event_response({"userId": "u1", "level": "high", "who": "user",
                                                    "familyNotificationCandidate": True, "notify": False})
        self.assertEqual((len(self.recorded), self.dispatched, out["dispatch"]), (1, [], None))

    def test_notice_only_call_notifies_without_a_second_record(self):
        server.voice_guardian_event_response({"userId": "u1", "level": "high", "who": "user",
                                              "familyNotificationCandidate": True, "record": False, "notify": True})
        self.assertEqual((self.recorded, len(self.dispatched)), ([], 1))

    def test_old_voice_without_the_flag_still_notifies(self):
        server.voice_guardian_event_response({"userId": "u1", "level": "critical", "who": "user", "familyNotificationCandidate": True})
        self.assertEqual(len(self.dispatched), 1)

    def test_record_never_borrows_someone_elses_circle(self):
        with patch.object(server, "_current_family_group_id", return_value=None):
            server.voice_guardian_event_response({"userId": "u1", "level": "high", "who": "user", "familyNotificationCandidate": False})
        self.assertTrue(self.recorded[0].get("explicitScope"))
        cached = {"familyGroup": {"id": "someone-elses-circle"}, "primaryCareRecipientId": "someone-else"}
        with patch.object(server, "load_app_profile_store", return_value=cached):
            ev = server.normalize_product_event(self.recorded[0])
            legacy = server.normalize_product_event({"eventName": "x", "personId": "person-1"})
        self.assertEqual((ev["personId"], ev["familyGroupId"]), ("person-1", None))
        self.assertEqual(legacy["familyGroupId"], "someone-elses-circle")    # 其他舊呼叫照舊


class ProtectionWordingTests(unittest.TestCase):
    """複審抓到的兩種說法：關鍵字一定會漏，這兩種先補；長得像的不能誤擋。"""

    def test_new_abuse_wordings_block_family(self):
        import model_router
        for text in ("我兒子一直對我動手，我好想死", "我胸口好痛，是我兒子打的"):
            r = model_router.guardian_evaluate_response({"text": text, "effort": "quick"})
            self.assertTrue(r["risk"]["protectionMentioned"], text)
            self.assertFalse(r["responsePolicy"]["familyNotificationCandidate"], text)

    def test_look_alikes_still_notify_family(self):
        import model_router
        for text in ("醫生說要對我動手術，我胸口好痛喘不過氣", "電話是我兒子打的，我胸口好痛喘不過氣",
                     "119是我女兒打的，我胸口好痛喘不過氣"):
            r = model_router.guardian_evaluate_response({"text": text, "effort": "quick"})
            self.assertFalse(r["risk"]["protectionMentioned"], text)
            self.assertTrue(r["responsePolicy"]["familyNotificationCandidate"], text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
