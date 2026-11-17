# -*- coding: utf-8 -*-
"""機構端稽核「嚴格寫入口」與寫入不准假成功（#713 信任關卡 · 2026-11-18）。

一、機構紀錄的帳號欄一律空值：audit_events 的讀取規則讓家人讀得到自己帳號底下的紀錄，
    判定、備註、誰看過誰都不能掛在長輩家或照護人員自己家底下——就算這次請求綁的是照護人員自己的 App 帳號。
二、雲端開著卻寫失敗：往外丟，不退本機暫存檔假裝成功；所以「判定寫不進就不算數」真的成立。
三、同意、人員的寫入在雲端「連不上」時不准退本機檔；只有雲端沒設定或表還沒建才可以。
四、撤回同意存不進去 → 如實回 consent_not_saved（App 顯示沒有改到）。
五、備註遮電話與身分證、去角括號；匯出防公式、留紀錄。
六、席次換給別人：前一位的提醒與判定不掛到新的人名下。
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_org_api as W  # noqa: E402  先載入：測試本子路徑與假世界
from test_org_api import ADMIN_A, ORG_A, SEAT_A1, auth, call, fake_loaders, sig  # noqa: E402
import org_alerts  # noqa: E402
import org_api  # noqa: E402
import server  # noqa: E402
import supabase_adapter  # noqa: E402

NEW_ACC = "99999999-9999-9999-9999-999999999999"


class FakeAdapter:
    """假雲端：記下送出去的那一列；fail=True 時模擬寫失敗。"""

    def __init__(self, fail=False):
        self.fail, self.rows = fail, []

    def enabled(self):
        return True

    def append_org_audit_event(self, event):
        if self.fail:
            raise supabase_adapter.SupabaseRequestError("timed out", error_kind="unreachable")
        row = {"id": str(len(self.rows)), "account_id": None, "actor_user_id": event.get("actorUserId"),
               "event_type": event["eventType"], "target_table": event.get("targetTable"), "target_id": None,
               "details": event.get("details") or {}, "created_at": "2026-11-18T00:00:00Z"}
        self.rows.append(row)
        return supabase_adapter.SupabaseAdapter.audit_row_to_event(row)


def _loader_over(rows):
    def load(client_id, since_iso, types):
        return [{"eventType": r["event_type"], "details": r["details"], "createdAt": f"{r['created_at']}#{i:06d}"}
                for i, r in enumerate(rows) if r["event_type"] in types]
    return load


class StrictWriterTests(unittest.TestCase):
    def test_account_column_is_always_empty_even_for_identity_bound_requests(self):
        adapter = supabase_adapter.SupabaseAdapter.__new__(supabase_adapter.SupabaseAdapter)
        captured = {}
        adapter.enabled = lambda: True

        def fake_request(method, table, query=None, payload=None, prefer=None):
            captured.update(payload=payload, table=table)
            return [{"id": "1", **payload, "created_at": "2026-11-18T00:00:00Z"}]

        adapter._request = fake_request
        adapter.account_id, adapter.request_scoped = "11111111-1111-1111-1111-111111111111", True   # 照護人員自己的 App 帳號
        adapter.append_org_audit_event({"eventType": "org_alert_marked", "accountId": "22222222-2222-2222-2222-222222222222",
                                        "details": {"clientId": "c", "remark": "疑似家屬疏忽"}})
        self.assertEqual(captured["table"], "audit_events")
        self.assertIsNone(captured["payload"]["account_id"])

    def test_cloud_failure_raises_instead_of_pretending(self):
        with patch.object(server, "_org_audit_backend", return_value=FakeAdapter(fail=True)):
            with self.assertRaises(supabase_adapter.SupabaseRequestError):
                server.append_org_audit_event_strict({"eventType": "org_alert_marked", "details": {"clientId": "c"}})

    def test_strict_writer_does_not_use_the_request_identity(self):
        calls = []

        def make(identity=None, **kw):
            calls.append(identity)
            return FakeAdapter()

        with patch.object(server.supabase_adapter, "make_adapter", side_effect=make):
            server._org_audit_backend()
        self.assertEqual(calls, [None])

    def test_org_sink_is_the_strict_writer(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), encoding="utf-8").read()
        sinks = [line.strip() for line in src.splitlines() if line.startswith("org_api.set_audit_sink(")]
        self.assertEqual(sinks[-1], "org_api.set_audit_sink(append_org_audit_event_strict)")


class MarkThroughRealSinkTests(W.Base):
    """接上真的嚴格寫入口：雲端開著但寫失敗 → /org/alert/mark 回 mark_not_recorded（以前會假成功）。"""

    def setUp(self):
        super().setUp()
        self.loaders = fake_loaders(signals={W.PER_A1: [sig(W.PER_A1, 3, 2, "x"), sig(W.PER_A1, 2, 1, "x"), sig(W.PER_A1, 1, 2, "x")]},
                                    summaries={W.PER_A1: [call(W.PER_A1, 1)]})
        self.fake = FakeAdapter()
        org_api.set_audit_sink(server.append_org_audit_event_strict)
        org_alerts.set_event_loader(_loader_over(self.fake.rows))
        self._p = patch.object(server, "_org_audit_backend", return_value=self.fake)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        org_alerts.set_event_loader(None)
        super().tearDown()

    def test_mark_is_refused_when_the_cloud_write_fails(self):
        alerts = org_alerts.org_alerts_response(auth(ADMIN_A), {}, loaders=self.loaders)
        self.assertTrue(alerts["ok"], alerts)
        a1 = next(a for a in alerts["alerts"] if a["seatId"] == SEAT_A1)
        self.fake.fail = True
        out = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": a1["alertId"], "result": "correct"}, loaders=self.loaders)
        self.assertEqual(out, {"ok": False, "error": "mark_not_recorded"})
        self.fake.fail = False
        again = next(a for a in org_alerts.org_alerts_response(auth(ADMIN_A), {}, loaders=self.loaders)["alerts"]
                     if a["alertId"] == a1["alertId"])
        self.assertEqual(again["status"], "unmarked")

    def test_written_rows_never_carry_a_family_account(self):
        org_alerts.org_alerts_response(auth(ADMIN_A), {}, loaders=self.loaders)
        self.assertTrue(self.fake.rows)
        self.assertTrue(all(r["account_id"] is None for r in self.fake.rows))


class NoFakeSuccessOnWritesTests(W.Base):
    def test_consent_revoke_does_not_fake_success_when_cloud_unreachable(self):
        class Unreachable:
            def enabled(self):
                return True

            def upsert_org_care_consent(self, record):
                raise supabase_adapter.SupabaseRequestError("timed out", error_kind="unreachable")

            def load_org_care_consents(self, **kw):
                return None

        ident = {"accountId": W.ACC_A1, "personId": W.PER_A1, "authUserId": "u-a1"}
        with patch.object(org_api, "_backend", return_value=Unreachable()):
            out = org_api.org_consent_set_response(ident, {"seatId": SEAT_A1, "granted": False})
        self.assertEqual(out["error"], "consent_not_saved")
        self.assertEqual(out["seat"]["consent"]["status"], "granted")                       # 畫面上仍顯示「開著」
        self.assertEqual(org_api.list_consents(seat_id=SEAT_A1)[0]["status"], "granted")   # 本機檔也沒被偷偷改

    def test_only_missing_setup_may_fall_back_locally(self):
        self.assertTrue(org_api._local_write_ok(supabase_adapter.SupabaseRequestError("x", error_kind="missing_table")))
        self.assertTrue(org_api._local_write_ok(supabase_adapter.SupabaseRequestError("x", error_kind="configuration")))
        self.assertFalse(org_api._local_write_ok(supabase_adapter.SupabaseRequestError("x", error_kind="unreachable")))


class RemarkAndExportHygieneTests(W.Base):
    def test_remark_masks_phone_and_id_and_strips_brackets(self):
        cleaned = org_alerts._clean_remark("<b>家屬</b> 0912-345-678 打過，身分證 A123456789，市話 02-23651098")
        self.assertNotIn("0912", cleaned)
        self.assertNotIn("A123456789", cleaned)
        self.assertNotIn("23651098", cleaned)
        self.assertNotIn("<", cleaned)
        self.assertIn("〔已遮〕", cleaned)

    def test_export_neutralises_formulas_and_leaves_a_record(self):
        self.assertEqual(org_alerts._cell("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(org_alerts._cell("正常"), "正常")
        org_alerts.set_event_loader(lambda cid, since, types: [])
        try:
            out = org_alerts.admin_alerts_export_response({"clientId": ORG_A})
        finally:
            org_alerts.set_event_loader(None)
        self.assertTrue(out["ok"], out)
        self.assertIn("第一次出現在提醒匣的時間", out["columns"])
        self.assertIn("org_alerts_exported", [e["eventType"] for e in self.audit])

    def test_export_refused_when_record_cannot_be_written(self):
        def boom(_e):
            raise RuntimeError("down")
        org_api.set_audit_sink(boom)
        org_alerts.set_event_loader(lambda cid, since, types: [])
        try:
            out = org_alerts.admin_alerts_export_response({"clientId": ORG_A})
        finally:
            org_alerts.set_event_loader(None)
        self.assertEqual(out, {"ok": False, "error": "audit_unavailable"})


class SeatChangesHandsTests(W.Base):
    def setUp(self):
        super().setUp()

        def load(client_id, since_iso, types):
            out = []
            for i, e in enumerate(self.audit):
                if e.get("eventType") in types:
                    d = e.get("details") or {}
                    out.append({"eventType": e["eventType"], "details": d,
                                "createdAt": f"{d.get('raisedAt') or d.get('markedAt') or ''}#{i:06d}"})
            return out

        org_alerts.set_event_loader(load)

    def tearDown(self):
        W.PERSONS.pop(NEW_ACC, None)
        org_alerts.set_event_loader(None)
        super().tearDown()

    def test_old_alerts_do_not_follow_the_seat_to_a_new_person(self):
        loaders = fake_loaders()                     # 沒有任何通話 → 會亮「沒聯絡」（從沒通過話）
        first = org_alerts.org_alerts_response(auth(ADMIN_A), {}, loaders=loaders)
        old = next(a for a in first["alerts"] if a["seatId"] == SEAT_A1)
        org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": old["alertId"], "result": "correct", "remark": "前一位的備註"},
                                           loaders=loaders)
        seats = json.load(open(os.environ["MUNEA_ENTERPRISE_SEATS_PATH"], encoding="utf-8"))
        for s in seats:
            if s["id"] == SEAT_A1:
                s["accountId"] = NEW_ACC
        W.write("MUNEA_ENTERPRISE_SEATS_PATH", seats)
        org_api.save_consent({**org_api.list_consents(seat_id=SEAT_A1)[0], "accountId": NEW_ACC})   # 新的人自己同意
        W.PERSONS[NEW_ACC] = {"personId": "per-new", "nickname": "新長輩", "profileName": ""}
        after = org_alerts.org_alerts_response(auth(ADMIN_A), {}, loaders=loaders)
        a1 = [a for a in after["alerts"] if a["seatId"] == SEAT_A1]
        self.assertNotIn(old["alertId"], [a["alertId"] for a in a1])           # 前一位那筆不列
        self.assertTrue(a1)                                                    # 新的人自己的「沒聯絡」是新的一件
        self.assertTrue(all(a["status"] == "unmarked" for a in a1))            # 沒有沿用前一位的判定
        self.assertNotIn("前一位的備註", json.dumps(after, ensure_ascii=False))
        out = org_alerts.org_alert_mark_response(auth(ADMIN_A), {"alertId": old["alertId"], "result": "false_alarm"}, loaders=loaders)
        self.assertEqual(out, {"ok": False, "error": "not_found"})


if __name__ == "__main__":
    unittest.main()
