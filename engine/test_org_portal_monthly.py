# -*- coding: utf-8 -*-
"""機構專區月度彙總的守門（2026-10-26 · B2B2C 評估拍板方案 C：擴充免密碼專屬連結）。

盯死四件事：
  ① 個資保險真的會炸——故意把 email／mood／守護分類／月報本體塞進彙總，必須丟例外
  ② 小樣本抑制——啟用人數未滿 5 人，比率與守護件數一律 null＋smallSampleSuppressed
  ③ 憑證過期、簽章改一個字，都進不來
  ④ 月報下載路由：沒憑證 401、別家的月報 404、自己的才給

另外守兩件工程上的事：資料是「一次撈整組帳號」不是每戶一查；本機 JSON 備援也跑得動。

跑法：python -m pytest engine/test_org_portal_monthly.py
"""

import datetime
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "org-portal-monthly-test-key")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import enterprise_billing  # noqa: E402
import org_portal  # noqa: E402
import server  # noqa: E402
import supabase_adapter  # noqa: E402

SECRET = {"MUNEA_ORG_PORTAL_SECRET": "test-secret-do-not-use-in-prod"}
TODAY = datetime.date(2026, 10, 26)

CLIENT = {
    "id": "cli-a",
    "name": "青松健康護理之家",
    "planTier": "plus",
    "seatQuota": 20,
    "contractStart": "2026-10-01",
    "contractEnd": "2027-09-30",
    "contactEmail": "director@example.org",
    "notes": "內部備註不該外流",
}


def seats(n_active, n_pending=1):
    rows = [
        {"id": f"s{i}", "status": "active", "accountId": f"acc-{i}", "inviteEmail": f"p{i}@example.org"}
        for i in range(1, n_active + 1)
    ]
    rows += [{"id": f"p{i}", "status": "pending", "inviteEmail": f"wait{i}@example.org"} for i in range(n_pending)]
    rows.append({"id": "r1", "status": "released", "accountId": "acc-released"})
    return rows


def iso(days_ago):
    return (TODAY - timedelta(days=days_ago)).strftime("%Y-%m-%dT10:00:00Z")


def ev(acc, days_ago, name="voice_session_completed", props=None):
    return {"accountId": acc, "eventName": name, "eventTime": iso(days_ago), "properties": props or {}}


def dose(acc, days_ago, status):
    return {"accountId": acc, "status": status, "scheduledDate": (TODAY - timedelta(days=days_ago)).isoformat()}


def summary_for(n_active, events=(), doses=(), reports=(), client=CLIENT):
    return org_portal.build_portal_summary(
        client["id"], seats=seats(n_active), client=client,
        activity={"productEvents": list(events), "medicationDoses": list(doses)},
        reports=list(reports), today=TODAY,
    )


class UsageSectionTests(unittest.TestCase):
    def test_counts_active_retention_and_weekly_average(self):
        events = [
            ev("acc-1", 2), ev("acc-2", 5), ev("acc-3", 10), ev("acc-4", 29),   # 近 30 天：4 人
            ev("acc-1", 35), ev("acc-2", 40), ev("acc-5", 45),                   # 上一期：3 人
            ev("acc-6", 3, name="guardian_risk_evaluated", props={"riskLevel": "high"}),  # 系統事件，不算
            ev("acc-6", 4, props={"analyticsExcluded": True}),                   # 自己標不算指標
            ev("acc-other", 1),                                                   # 別家的帳號
            ev("acc-1", 70),                                                      # 兩期之外
        ]
        s = summary_for(6, events)["usage"]
        self.assertEqual(s["enabledCount"], 6)
        self.assertEqual(s["activeCount"], 4)
        self.assertEqual(s["activeRate"], round(4 / 6, 4))
        self.assertEqual(s["retentionBaseCount"], 3)
        self.assertEqual(s["retentionRate"], round(2 / 3, 4))  # acc-1、acc-2 兩期都有
        self.assertEqual(s["avgWeeklyInteractionsPerPerson"], round(4 / 6 / (30 / 7), 2))
        self.assertFalse(s["smallSampleSuppressed"])

    def test_medication_taken_counts_as_interaction(self):
        s = summary_for(6, [], [dose("acc-6", 3, "taken")])["usage"]
        self.assertEqual(s["activeCount"], 1)

    def test_no_previous_period_means_retention_is_null_not_zero(self):
        s = summary_for(6, [ev("acc-1", 2)])["usage"]
        self.assertIsNone(s["retentionRate"])
        self.assertEqual(s["retentionBaseCount"], 0)


class GuardianSectionTests(unittest.TestCase):
    def test_high_risk_counts_only_in_window_only_high_levels(self):
        events = [
            ev("acc-1", 1, "guardian_risk_evaluated", {"riskLevel": "high"}),
            ev("acc-2", 8, "guardian_risk_evaluated", {"riskLevel": "critical"}),
            ev("acc-3", 9, "guardian_risk_evaluated", {"riskLevel": "medium"}),   # 不算
            ev("acc-4", 40, "guardian_risk_evaluated", {"riskLevel": "high"}),    # 視窗外
            ev("acc-other", 2, "guardian_risk_evaluated", {"riskLevel": "high"}),  # 別家
        ]
        doses = (
            [dose("acc-1", d, "taken") for d in range(6)]
            + [dose("acc-2", 1, "missed"), dose("acc-2", 2, "missed")]
            + [dose("acc-3", 1, "skipped"), dose("acc-3", 2, "skipped")]
            + [dose("acc-4", 0, "scheduled")] * 3
            + [dose("acc-5", 45, "missed")]  # 視窗外
        )
        g = summary_for(6, events, doses)["guardian"]
        self.assertEqual(g["highRiskEventCount"], 2)
        self.assertEqual(g["medicationDecidedCount"], 10)
        self.assertEqual(g["medicationCompletionRate"], 0.6)
        self.assertFalse(g["smallSampleSuppressed"])

    def test_follow_up_is_honestly_unavailable(self):
        """系統還沒有「已處理／誤報／觀察中」標記，不准填 0 冒充「沒人跟進」。"""
        g = summary_for(6)["guardian"]
        self.assertIsNone(g["followedUpCount"])
        self.assertFalse(g["followUpTrackingAvailable"])

    def test_no_decided_doses_means_rate_is_null(self):
        g = summary_for(6, [], [dose("acc-1", 0, "scheduled")])["guardian"]
        self.assertIsNone(g["medicationCompletionRate"])


class SmallSampleTests(unittest.TestCase):
    def test_under_five_enabled_suppresses_ratios_and_guardian_counts(self):
        events = [ev("acc-1", 1), ev("acc-1", 40),
                  ev("acc-2", 2, "guardian_risk_evaluated", {"riskLevel": "high"})]
        s = summary_for(4, events, [dose("acc-1", 1, "taken")])
        usage, guardian = s["usage"], s["guardian"]
        self.assertTrue(usage["smallSampleSuppressed"])
        self.assertTrue(guardian["smallSampleSuppressed"])
        self.assertTrue(s["privacy"]["smallSampleSuppressed"])
        for key in ("activeRate", "retentionRate", "retentionBaseCount", "avgWeeklyInteractionsPerPerson"):
            self.assertIsNone(usage[key], key)
        for key in ("highRiskEventCount", "medicationCompletionRate", "medicationDecidedCount"):
            self.assertIsNone(guardian[key], key)
        # 合約層本來就知道的人數照給
        self.assertEqual(usage["enabledCount"], 4)
        self.assertEqual(usage["activeCount"], 1)

    def test_exactly_five_is_not_suppressed(self):
        s = summary_for(5, [ev("acc-1", 1)])
        self.assertFalse(s["usage"]["smallSampleSuppressed"])
        self.assertEqual(s["usage"]["activeRate"], 0.2)
        self.assertEqual(s["guardian"]["highRiskEventCount"], 0)

    def test_zero_enabled_does_not_divide_by_zero(self):
        s = org_portal.build_portal_summary(
            "cli-a", seats=[{"id": "p", "status": "pending", "inviteEmail": "x@example.org"}],
            client=CLIENT, activity={"productEvents": [], "medicationDoses": []}, reports=[], today=TODAY)
        self.assertEqual(s["usage"]["enabledCount"], 0)
        self.assertIsNone(s["usage"]["avgWeeklyInteractionsPerPerson"])


class PrivacyGuardTests(unittest.TestCase):
    def full_summary(self):
        events = [ev("acc-1", 1), ev("acc-2", 2, "guardian_risk_evaluated", {"riskLevel": "high", "categories": ["跌倒"]})]
        reports = [{"id": "rep-1", "enterpriseClientId": "cli-a", "periodStart": "2026-09-01", "periodEnd": "2026-09-30",
                    "generatedAt": "2026-10-01T01:00:00Z", "reportHtml": "<html>月報本體</html>"}]
        return summary_for(6, events, [dose("acc-1", 1, "taken")], reports)

    def test_full_summary_passes_and_leaks_nothing(self):
        s = self.full_summary()
        self.assertTrue(org_portal.assert_no_personal_data(s))
        blob = repr(s)
        for leaked in ("acc-1", "acc-2", "p1@example.org", "director@example.org", "內部備註", "跌倒", "月報本體", "riskLevel"):
            self.assertNotIn(leaked, blob)

    def test_injected_personal_fields_blow_up(self):
        base = self.full_summary()
        for bad in (
            {"usage": {"email": "x@y.z"}},
            {"guardian": {"mood": "低落"}},
            {"guardian": {"categories": ["跌倒"]}},
            {"reports": {"list": [{"id": "r", "reportHtml": "<html>"}]}},
            {"usage": {"accountIds": ["acc-1"]}},
            {"guardian": {"recent": [{"personId": "p-1"}]}},
        ):
            s = json.loads(json.dumps(base))
            for section, extra in bad.items():
                s[section].update(extra)
            with self.assertRaises(org_portal.PortalPrivacyError, msg=repr(bad)):
                org_portal.assert_no_personal_data(s)

    def test_reports_section_has_only_period_and_availability(self):
        s = self.full_summary()
        self.assertEqual(s["reports"]["count"], 1)
        item = s["reports"]["list"][0]
        self.assertEqual(item["period"], "2026年9月")
        self.assertTrue(item["available"])
        self.assertEqual(set(item.keys()), {"id", "period", "periodStart", "periodEnd", "generatedAt", "available"})


class DataLoadingTests(unittest.TestCase):
    def test_supabase_path_fetches_whole_cohort_in_one_call(self):
        calls = []

        class FakeBackend:
            def enabled(self):
                return True

            def load_org_cohort_product_events(self, account_ids, since_iso=None, limit=20000):
                calls.append(("events", list(account_ids), since_iso))
                return []

            def load_org_cohort_medication_doses(self, account_ids, since_date=None, limit=5000):
                calls.append(("doses", list(account_ids), since_date))
                return []

        result = org_portal.load_cohort_activity(["acc-2", "acc-1", "acc-2"], "2026-08-28T00:00:00Z", "2026-08-28", backend=FakeBackend())
        self.assertEqual(result["source"], "supabase")
        self.assertEqual([c[0] for c in calls], ["events", "doses"])  # 各一次，不是每戶一次
        self.assertEqual(calls[0][1], ["acc-1", "acc-2"])
        self.assertEqual(calls[1][1], ["acc-1", "acc-2"])

    def test_adapter_in_filter_only_takes_uuids(self):
        uuid_a = "11111111-1111-4111-8111-111111111111"
        uuid_b = "22222222-2222-4222-8222-222222222222"
        flt = supabase_adapter.SupabaseAdapter._cohort_in_filter([uuid_b, "local-demo-account", uuid_a, uuid_a])
        self.assertEqual(flt, f"in.({uuid_a},{uuid_b})")
        self.assertIsNone(supabase_adapter.SupabaseAdapter._cohort_in_filter(["local-demo-account"]))

    def test_local_json_backend_filters_by_cohort_and_window(self):
        class Disabled:
            def enabled(self):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            events_path = os.path.join(tmp, "product_events.json")
            doses_path = os.path.join(tmp, "medication_doses.json")
            with open(events_path, "w", encoding="utf-8") as f:
                json.dump({"events": [ev("acc-1", 1), ev("acc-9", 1), ev("acc-1", 90)]}, f)
            with open(doses_path, "w", encoding="utf-8") as f:
                json.dump([dose("acc-1", 1, "taken"), dose("acc-9", 1, "taken"), dose("acc-1", 90, "taken")], f)
            with patch.object(org_portal, "PRODUCT_EVENTS_PATH", events_path), \
                 patch.object(org_portal, "MEDICATION_DOSES_PATH", doses_path):
                result = org_portal.load_cohort_activity(["acc-1"], iso(60), (TODAY - timedelta(days=60)).isoformat(), backend=Disabled())
        self.assertEqual(result["source"], "json")
        self.assertEqual(len(result["productEvents"]), 1)
        self.assertEqual(len(result["medicationDoses"]), 1)


def _tamper(token):
    payload, sig = token.split(".", 1)
    last = "A" if sig[-1] != "A" else "B"
    return f"{payload}.{sig[:-1]}{last}"


class TokenAndEndpointTests(unittest.TestCase):
    def patched(self):
        return [
            patch.object(org_portal.enterprise_seats, "get_client", side_effect=lambda cid: CLIENT if cid == "cli-a" else None),
            patch.object(org_portal.enterprise_seats, "list_seats", side_effect=lambda client_id=None, **kw: seats(6)),
            patch.object(org_portal, "load_cohort_activity", return_value={"productEvents": [ev("acc-1", 1)], "medicationDoses": []}),
            patch.object(org_portal, "_load_reports", return_value=[]),
        ]

    @patch.dict(os.environ, SECRET, clear=False)
    def test_valid_link_returns_three_new_sections(self):
        token = org_portal.issue_portal_token("cli-a")
        patches = self.patched()
        for p in patches:
            p.start()
        try:
            result = server.org_portal_summary_response({"token": token})
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(result["ok"], result)
        for section in ("usage", "guardian", "reports", "period", "privacy"):
            self.assertIn(section, result)
        self.assertEqual(result["usage"]["enabledCount"], 6)
        self.assertNotIn("acc-1", repr(result))

    @patch.dict(os.environ, SECRET, clear=False)
    def test_expired_link_is_rejected(self):
        long_ago = datetime.datetime.now(timezone.utc) - timedelta(days=40)
        token = org_portal.issue_portal_token("cli-a", ttl_days=30, issued_at=long_ago)
        self.assertEqual(server.org_portal_summary_response({"token": token})["error"], "token_expired")
        status, ctype, body = server.org_portal_report_response(f"t={token}&id=rep-1")
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "token_expired")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_one_character_change_in_signature_is_rejected(self):
        token = _tamper(org_portal.issue_portal_token("cli-a"))
        self.assertEqual(server.org_portal_summary_response({"token": token})["error"], "invalid_token")
        status, _ctype, body = server.org_portal_report_response(f"t={token}&id=rep-1")
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "invalid_token")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_report_download_without_token_is_401(self):
        for query in ("", "id=rep-1", "t=&id=rep-1"):
            status, ctype, body = server.org_portal_report_response(query)
            self.assertEqual(status, 401, query)
            self.assertIn("application/json", ctype)
            self.assertEqual(json.loads(body)["error"], "invalid_token")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_report_download_only_serves_own_org(self):
        reports = {
            "rep-a": {"id": "rep-a", "enterpriseClientId": "cli-a", "reportHtml": "<html>A 家月報</html>"},
            "rep-b": {"id": "rep-b", "enterpriseClientId": "cli-b", "reportHtml": "<html>B 家月報</html>"},
        }
        token_a = org_portal.issue_portal_token("cli-a")
        with patch.object(enterprise_billing, "get_report", side_effect=lambda rid: reports.get(rid)):
            ok_status, ok_ctype, ok_body = server.org_portal_report_response(f"t={token_a}&id=rep-a")
            other_status, _c, other_body = server.org_portal_report_response(f"t={token_a}&id=rep-b")
            missing_status, _c2, _b2 = server.org_portal_report_response(f"t={token_a}&id=nope")
        self.assertEqual(ok_status, 200)
        self.assertIn("text/html", ok_ctype)
        self.assertIn("A 家月報", ok_body.decode("utf-8"))
        self.assertEqual(other_status, 404)
        self.assertNotIn("B 家月報", other_body.decode("utf-8"))
        self.assertEqual(missing_status, 404)

    def test_download_route_is_listed_in_api_contract_inventory(self):
        root = os.path.dirname(HERE)
        with open(os.path.join(root, "docs", "API-CONTRACT-INVENTORY.json"), encoding="utf-8") as f:
            inventory = json.load(f)
        routes = inventory.get("routes") if isinstance(inventory, dict) else inventory
        found = [r for r in routes if r.get("path") == "/enterprise/portal/report" and r.get("method") == "GET"]
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
