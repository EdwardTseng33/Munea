# -*- coding: utf-8 -*-
"""機構端異常提醒匣＋逐筆判定守門測試（第 3 段 · 補助案 C4 · 2026-11-18）。

盯的事：
  一、同一件事只發一次（編號穩定、重算不重發、同一段心情低潮 7 天內不重發）。
  二、看得到誰照舊：沒同意的不算也不列、撤回後舊提醒一起消失、別家看不到也判不到、
      社工只看自己分點、照服員與企業 HR 沒有這頁。
  三、判定只能新增、最後一筆為準；寫不進紀錄就不算數；提醒內容沒有原句。
  四、營運端匯出欄位順序對齊 C4 逐筆判定表，演練編號取自名冊稱呼。

跑法：python -m unittest test_org_alerts（純本子模式、不需網路／鑰匙）
"""
import json
import os
import sys
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_org_api as W  # noqa: E402  先載入：它設好測試用的本子路徑與假世界
from test_org_api import (  # noqa: E402
    ACC_A1, ACC_A2, ADMIN_A, ADMIN_B, CASE_A, HR_ESG, ORG_A, PER_A1, PER_A2, SEAT_A1, SEAT_A2, SEAT_A3, WORKER_A,
    auth, call, fake_loaders, guardian, sig, walk_strings, write,
)
import org_alerts  # noqa: E402
import org_api  # noqa: E402

PILL = "毒餌原句ZQ9"


class AlertsBase(W.Base):
    def setUp(self):
        super().setUp()
        org_alerts.set_event_loader(self._load)
        # A1：連三天心情低（2、1、2）、前天守護腦亮 high、昨天有通話 → 心情下降＋守護腦
        # A2：整週沒通話 → 沒聯絡
        self.loaders = fake_loaders(
            signals={PER_A1: [sig(PER_A1, 3, 2, PILL, [PILL + "掛心"]), sig(PER_A1, 2, 1, PILL), sig(PER_A1, 1, 2, PILL)]},
            summaries={PER_A1: [call(PER_A1, 3), call(PER_A1, 1)]},
            events=[guardian(ACC_A1, PER_A1, 2, "high")],
        )

    def tearDown(self):
        org_alerts.set_event_loader(None)
        super().tearDown()

    def _load(self, client_id, since_iso, types):
        out = []
        for i, e in enumerate(self.audit):
            if e.get("eventType") not in types:
                continue
            d = e.get("details") or {}
            # 本機測試沒有資料庫時間：用寫入順序當時間（後寫的比較新）
            stamp = d.get("raisedAt") or d.get("markedAt") or d.get("savedAt") or ""
            out.append({"eventType": e["eventType"], "details": d, "createdAt": f"{stamp}#{i:06d}"})
        return out

    def raised_events(self):
        return [e for e in self.audit if e["eventType"] == org_alerts.EVENT_RAISED]

    def alerts(self, who=ADMIN_A, **data):
        out = org_alerts.org_alerts_response(auth(who), data, loaders=self.loaders)
        self.assertTrue(out.get("ok"), out)
        return out


class RaiseOnceTests(AlertsBase):
    def test_first_look_raises_and_second_look_does_not(self):
        first = self.alerts()
        types = sorted((a["seatId"], a["type"]) for a in first["alerts"])
        self.assertIn((SEAT_A1, "mood_drop"), types)
        self.assertIn((SEAT_A1, "guardian"), types)
        self.assertIn((SEAT_A2, "no_contact"), types)
        self.assertNotIn(SEAT_A3, {a["seatId"] for a in first["alerts"]})   # 沒同意：不算也不列
        n = len(self.raised_events())
        self.assertEqual(n, len(first["alerts"]))
        second = self.alerts()
        self.assertEqual(len(self.raised_events()), n)                      # 重算不重發
        self.assertEqual({a["alertId"] for a in first["alerts"]}, {a["alertId"] for a in second["alerts"]})
        for a in second["alerts"]:
            self.assertTrue(a["alertId"].startswith("ALR-"))
            self.assertEqual(a["status"], "unmarked")
            self.assertTrue(a["raisedAt"])

    def test_alert_ids_are_stable_and_never_called_uses_none(self):
        self.assertEqual(org_alerts.alert_id("s", "no_contact", "2026-11-10"), org_alerts.alert_id("s", "no_contact", "2026-11-10"))
        self.assertNotEqual(org_alerts.alert_id("s", "no_contact", "2026-11-10"), org_alerts.alert_id("s", "no_contact", "2026-11-11"))
        self.assertTrue(org_alerts.alert_id("s", "no_contact", "none").startswith("ALR-NONE-"))
        self.assertTrue(org_alerts.alert_id("s", "guardian", "2026-11-16T11:00:00Z").startswith("ALR-20261116-"))

    def test_same_low_mood_episode_is_not_raised_twice(self):
        import datetime
        today = datetime.date.today()
        raised = {"x": {"seatId": SEAT_A1, "type": "mood_drop", "raisedAt": today.isoformat() + "T01:00:00Z"}}
        cand = {"seatId": SEAT_A1, "type": "mood_drop"}
        self.assertTrue(org_alerts._suppressed(cand, raised, today))
        self.assertFalse(org_alerts._suppressed({"seatId": SEAT_A2, "type": "mood_drop"}, raised, today))
        self.assertFalse(org_alerts._suppressed({"seatId": SEAT_A1, "type": "guardian"}, raised, today))
        old = {"x": {"seatId": SEAT_A1, "type": "mood_drop", "raisedAt": (today - datetime.timedelta(days=8)).isoformat()}}
        self.assertFalse(org_alerts._suppressed(cand, old, today))

    def test_no_original_sentences_reach_the_org(self):
        out = self.alerts()
        text = json.dumps(out, ensure_ascii=False)
        self.assertNotIn(PILL, text)
        self.assertNotIn("對話摘要正文", text)
        guardian_alert = next(a for a in out["alerts"] if a["type"] == "guardian")
        self.assertIn("看不到通話原句", guardian_alert["suggestion"])
        self.assertNotIn("即時通知已另外送出", guardian_alert["fact"])   # 機構沒收到即時通知，不能這樣寫
        self.assertTrue(guardian_alert["fact"].startswith("守護腦這週亮了"))


class WhoSeesWhatTests(AlertsBase):
    def test_case_manager_sees_only_own_site(self):
        out = self.alerts(CASE_A)
        self.assertEqual({a["seatId"] for a in out["alerts"]}, {SEAT_A1})   # 北院只有 A1；A2 在南院

    def test_care_worker_and_company_hr_have_no_inbox(self):
        self.assertEqual(org_alerts.org_alerts_response(auth(WORKER_A), {}, loaders=self.loaders), {"ok": False, "error": "not_found"})
        self.assertEqual(org_alerts.org_alerts_response(auth(HR_ESG), {}, loaders=self.loaders), {"ok": False, "error": "not_found"})
        self.assertEqual(org_alerts.org_alerts_response(auth(str(uuid.uuid4())), {}, loaders=self.loaders), {"ok": False, "error": "not_found"})

    def test_other_org_cannot_mark(self):
        alert = self.alerts()["alerts"][0]
        out = org_alerts.org_alert_mark_response(auth(ADMIN_B), {"alertId": alert["alertId"], "result": "correct"}, loaders=self.loaders)
        self.assertEqual(out, {"ok": False, "error": "not_found"})
        self.assertFalse([e for e in self.audit if e["eventType"] == org_alerts.EVENT_MARKED])

    def test_case_manager_cannot_mark_other_site(self):
        a2 = next(a for a in self.alerts()["alerts"] if a["seatId"] == SEAT_A2)
        out = org_alerts.org_alert_mark_response(auth(CASE_A), {"alertId": a2["alertId"], "result": "correct"}, loaders=self.loaders)
        self.assertEqual(out, {"ok": False, "error": "not_found"})

    def test_revoked_consent_hides_old_alerts_and_blocks_marking(self):
        a1 = next(a for a in self.alerts()["alerts"] if a["seatId"] == SEAT_A1)
        org_api.save_consent({**org_api.list_consents(seat_id=SEAT_A1)[0], "status": "revoked"})
        self.assertNotIn(SEAT_A1, {a["seatId"] for a in self.alerts()["alerts"]})
        out = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": a1["alertId"], "result": "correct"}, loaders=self.loaders)
        self.assertEqual(out, {"ok": False, "error": "not_found"})


class MarkTests(AlertsBase):
    def test_marks_are_append_only_and_latest_wins(self):
        alert = self.alerts()["alerts"][0]
        first = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": alert["alertId"], "result": "watching", "remark": "先觀察"}, loaders=self.loaders)
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["alert"]["status"], "watching")
        second = org_alerts.org_alert_mark_response(auth(ADMIN_A), {
            "alertId": alert["alertId"], "result": "correct", "isReal": "是", "worthNotifying": "yes", "remark": "  打電話確認了  "},
            loaders=self.loaders)
        self.assertEqual(second["alert"]["status"], "correct")
        self.assertEqual(second["alert"]["statusLabel"], "正確")
        self.assertEqual(len(second["alert"]["markHistory"]), 2)
        self.assertEqual(second["alert"]["lastMark"]["remark"], "打電話確認了")
        self.assertEqual(second["alert"]["lastMark"]["isReal"], "yes")
        self.assertEqual(second["alert"]["lastMark"]["markedBy"], "A 主任")
        marked = [e for e in self.audit if e["eventType"] == org_alerts.EVENT_MARKED]
        self.assertEqual(len(marked), 2)
        self.assertEqual(marked[-1]["actorUserId"], ADMIN_A)
        self.assertEqual(marked[-1]["details"]["result"], "correct")
        listing = self.alerts()
        self.assertEqual(next(a for a in listing["alerts"] if a["alertId"] == alert["alertId"])["status"], "correct")
        self.assertEqual(listing["accuracy"]["correct"], 1)
        self.assertEqual(listing["accuracy"]["judged"], 1)

    def test_bad_result_and_long_remark(self):
        alert = self.alerts()["alerts"][0]
        bad = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": alert["alertId"], "result": "maybe"}, loaders=self.loaders)
        self.assertEqual(bad["error"], "result_invalid")
        out = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": alert["alertId"], "result": "false_alarm", "remark": "字" * 500}, loaders=self.loaders)
        self.assertEqual(len(out["alert"]["lastMark"]["remark"]), org_alerts.REMARK_MAX)

    def test_mark_is_refused_when_it_cannot_be_recorded(self):
        alert = self.alerts()["alerts"][0]
        def boom(_event):
            raise RuntimeError("audit store down")
        org_api.set_audit_sink(boom)
        out = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": alert["alertId"], "result": "correct"}, loaders=self.loaders)
        self.assertEqual(out, {"ok": False, "error": "mark_not_recorded"})

    def test_marks_from_another_org_never_count(self):
        """紀錄是用機構過濾撈的；就算撈錯混進別家的判定（同一個編號），也不能改到這家的狀態。"""
        alert = self.alerts()["alerts"][0]
        self.audit.append({"eventType": org_alerts.EVENT_MARKED, "details": {
            "clientId": W.ORG_B, "alertId": alert["alertId"], "result": "false_alarm", "markedAt": "2099-01-01T00:00:00Z"}})
        again = next(a for a in self.alerts()["alerts"] if a["alertId"] == alert["alertId"])
        self.assertEqual(again["status"], "unmarked")

    def test_unknown_alert_is_not_found(self):
        out = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": "ALR-20260101-ABCDEF", "result": "correct"}, loaders=self.loaders)
        self.assertEqual(out, {"ok": False, "error": "not_found"})

    def test_status_filter_and_accuracy_math(self):
        alerts = self.alerts()["alerts"]
        org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": alerts[0]["alertId"], "result": "correct"}, loaders=self.loaders)
        org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": alerts[1]["alertId"], "result": "false_alarm"}, loaders=self.loaders)
        out = self.alerts()
        self.assertEqual(out["accuracy"]["rate"], 0.5)
        self.assertEqual(self.alerts(status="unmarked")["count"], len(alerts) - 2)
        self.assertEqual(self.alerts(status="false_alarm")["count"], 1)


class AuditAndExportTests(AlertsBase):
    def test_audit_view_is_admin_only_and_shows_marks(self):
        alert = self.alerts()["alerts"][0]
        org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": alert["alertId"], "result": "correct"}, loaders=self.loaders)
        out = org_alerts.org_audit_response(auth(ADMIN_A))
        self.assertTrue(out["ok"])
        self.assertIn("判定了一筆提醒", [i["action"] for i in out["items"]])
        self.assertEqual(org_alerts.org_audit_response(auth(CASE_A)), {"ok": False, "error": "not_found"})
        self.assertEqual(org_alerts.org_audit_response(auth(HR_ESG)), {"ok": False, "error": "not_found"})

    def test_export_columns_and_drill_ids(self):
        seats = json.load(open(os.environ["MUNEA_ENTERPRISE_SEATS_PATH"], encoding="utf-8"))
        for s in seats:
            if s["id"] == SEAT_A1:
                s["memberName"] = "M01"
        write("MUNEA_ENTERPRISE_SEATS_PATH", seats)
        alert = next(a for a in self.alerts()["alerts"] if a["seatId"] == SEAT_A1)
        org_alerts.org_alert_mark_response(auth(CASE_A), {"alertId": alert["alertId"], "result": "correct", "isReal": "yes", "worthNotifying": "no"}, loaders=self.loaders)
        out = org_alerts.admin_alerts_export_response({"clientId": ORG_A})
        self.assertTrue(out["ok"])
        self.assertEqual(out["columns"][:4], ["事件編號", "演練編號", "來源", "規則"])
        row = next(r for r in out["rows"] if r["事件編號"] == alert["alertId"])
        self.assertEqual(list(row.keys()), out["columns"])
        self.assertEqual((row["演練編號"], row["來源"], row["系統有沒有通知"]), ("M01", "演練", "是"))
        self.assertEqual((row["事情是真的嗎"], row["值得通知嗎"], row["判定結果"]), ("是", "否", "正確"))
        self.assertEqual((row["判定者"], row["職稱"]), ("A 社工", "社工／個管"))
        a2 = next(r for r in out["rows"] if r["規則"] == "no_contact")
        self.assertEqual((a2["演練編號"], a2["來源"], a2["判定結果"]), ("", "試辦", ""))
        # 真名冊稱呼（不是 M01 這種演練編號）不能被當成演練編號匯出去
        seats = json.load(open(os.environ["MUNEA_ENTERPRISE_SEATS_PATH"], encoding="utf-8"))
        for s in seats:
            if s["id"] == SEAT_A2:
                s["memberName"] = "王小明"
        write("MUNEA_ENTERPRISE_SEATS_PATH", seats)
        again = org_alerts.admin_alerts_export_response({"clientId": ORG_A})
        a2 = next(r for r in again["rows"] if r["規則"] == "no_contact")
        self.assertEqual((a2["演練編號"], a2["來源"]), ("", "試辦"))
        self.assertNotIn("王小明", json.dumps(again, ensure_ascii=False))
        self.assertEqual(org_alerts.admin_alerts_export_response({"clientId": "nope"})["error"], "client_not_found")


class SettingsTests(AlertsBase):
    """機構自訂「幾天沒聯絡才提醒」（C4 演練 C05／C06／C10 要用）。"""

    def setUp(self):
        super().setUp()
        # A1：4 天前最後一通、心情正常 → 預設 3 天會亮「沒聯絡」，設成 5 天就不該亮
        self.loaders = fake_loaders(signals={PER_A1: [sig(PER_A1, 4, 4, "平常")]}, summaries={PER_A1: [call(PER_A1, 4)]})

    def kinds_for_a1(self):
        return {a["type"] for a in self.alerts()["alerts"] if a["seatId"] == SEAT_A1}

    def test_default_is_three_days(self):
        self.assertEqual(org_alerts.client_settings(ORG_A)["noContactDays"], 3)
        self.assertIn("no_contact", self.kinds_for_a1())

    def test_admin_can_raise_threshold_and_it_changes_alerts(self):
        out = org_alerts.org_settings_save_response(auth(ADMIN_A), {"noContactDays": 5})
        self.assertTrue(out["ok"], out)
        self.assertEqual(org_alerts.client_settings(ORG_A)["noContactDays"], 5)
        self.assertNotIn("no_contact", self.kinds_for_a1())
        self.assertEqual(org_alerts.org_settings_response(auth(CASE_A))["settings"]["noContactDays"], 5)
        elders = org_api.org_elders_response(auth(ADMIN_A), loaders=self.loaders)
        a1 = next(e for e in elders["elders"] if e["seatId"] == SEAT_A1)
        self.assertNotIn("no_contact", a1["anomalyTypes"])          # 名單也照機構設定
        saved = [e for e in self.audit if e["eventType"] == org_alerts.EVENT_SETTINGS]
        self.assertEqual((saved[-1]["actorUserId"], saved[-1]["details"]["noContactDays"]), (ADMIN_A, 5))

    def test_latest_setting_wins_and_range_is_enforced(self):
        org_alerts.org_settings_save_response(auth(ADMIN_A), {"noContactDays": 5})
        org_alerts.org_settings_save_response(auth(ADMIN_A), {"noContactDays": 1})
        self.assertEqual(org_alerts.client_settings(ORG_A)["noContactDays"], 1)
        for bad in (0, 31, "abc", None):
            self.assertEqual(org_alerts.org_settings_save_response(auth(ADMIN_A), {"noContactDays": bad})["error"], "no_contact_days_invalid")

    def test_only_org_admin_can_change(self):
        self.assertEqual(org_alerts.org_settings_save_response(auth(CASE_A), {"noContactDays": 5}), {"ok": False, "error": "not_found"})
        self.assertEqual(org_alerts.org_settings_save_response(auth(HR_ESG), {"noContactDays": 5}), {"ok": False, "error": "not_found"})
        self.assertEqual(org_alerts.org_settings_response(auth(WORKER_A)), {"ok": False, "error": "not_found"})

    def test_other_org_setting_never_applies(self):
        self.audit.append({"eventType": org_alerts.EVENT_SETTINGS, "details": {"clientId": W.ORG_B, "noContactDays": 30,
                                                                              "savedAt": "2099-01-01T00:00:00Z"}})
        self.assertEqual(org_alerts.client_settings(ORG_A)["noContactDays"], 3)


class LowMoodWordingTests(unittest.TestCase):
    """「連續 3 天」要跟日期對得上：中間有空檔就說「連續 3 次有紀錄」（C4 演練 M08，11/18）。"""

    def test_consecutive_days_keep_the_old_sentence(self):
        import care_week
        self.assertEqual(care_week._low_streak_fact(["2026-11-15", "2026-11-16", "2026-11-17"], 2),
                         "心情連續 3 天在 2 級以下（2026-11-15、2026-11-16、2026-11-17）。")

    def test_gapped_days_say_records_not_days(self):
        import care_week
        text = care_week._low_streak_fact(["2026-11-12", "2026-11-15", "2026-11-18"], 2)
        self.assertNotIn("連續 3 天", text)
        self.assertIn("連續 3 次有紀錄", text)
        self.assertIn("中間幾天沒有紀錄", text)


class RefreshAllTests(AlertsBase):
    """給之後排程用：沒人打開提醒匣也照樣發出；只算照護機構；重跑不重發。"""

    def test_refresh_all_raises_once_for_care_clients_only(self):
        first = org_alerts.admin_alerts_refresh_all_response({}, loaders=self.loaders)
        self.assertTrue(first["ok"], first)
        by_client = {c["clientId"]: c for c in first["clients"]}
        self.assertIn(ORG_A, by_client)
        self.assertNotIn(W.ORG_ESG, by_client)                    # 企業不算
        self.assertGreater(by_client[ORG_A]["newAlerts"], 0)
        second = org_alerts.admin_alerts_refresh_all_response({}, loaders=self.loaders)
        self.assertEqual(second["newAlerts"], 0)                  # 重跑不重發
        listed = self.alerts()["alerts"]                          # 照護人員打開時看到的就是排程發出的那幾筆
        self.assertEqual(len(self.raised_events()), first["newAlerts"])
        self.assertTrue(listed)

    def test_one_client_failing_does_not_stop_others(self):
        real = org_alerts.refresh_alerts
        def flaky(client, loaders=None, today=None, **kw):
            if client["id"] == ORG_A:
                raise RuntimeError("down")
            return real(client, loaders, today, **kw)
        with patch.object(org_alerts, "refresh_alerts", side_effect=flaky):
            out = org_alerts.admin_alerts_refresh_all_response({}, loaders=self.loaders)
        self.assertFalse(out["ok"])
        self.assertEqual({c["clientId"]: c["ok"] for c in out["clients"]}[ORG_A], False)
        self.assertTrue(any(c["ok"] for c in out["clients"] if c["clientId"] != ORG_A))


class ServerWiringTests(unittest.TestCase):
    def test_routes_and_loader_are_wired(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), encoding="utf-8").read()
        for path in ("/org/alerts", "/org/alert/mark", "/org/audit", "/org/settings", "/org/settings/save",
                     "/admin/enterprise/alerts/export", "/admin/enterprise/alerts/refresh"):
            self.assertIn(f'self.path == "{path}"', src)
        self.assertIn("org_alerts.set_event_loader(load_org_audit_events)", src)
        self.assertIn('"/admin/enterprise/alerts/export",', src)


if __name__ == "__main__":
    unittest.main()
