# -*- coding: utf-8 -*-
"""機構端專區 `/org/*` 守門測試（第 2 段 · PR-a · 2026-10-29）。

盯死設計書第 1.2 節三條鐵線＋第 2.3 節權限矩陣：
  一、沒同意的長輩在名單裡**根本不存在**（不是遮名字）；撤回後下一眼就不見；拿沒同意的席次查摘要跟查不存在的席次回同一句。
  二、A 機構的人翻不到 B 機構；社工只看自己分點；照服員拿不到摘要內文；企業（esg）客戶永遠只有彙總。
  三、摘要內文沒有原句、沒有對話摘要、沒有身分鍵；每次讀寫一筆稽核，稽核寫不進去就不給。
加上 App 端同意開關（只能動自己帳號的席次）、後台開人員（驗證＋防重複）與 server.py 接線。

跑法：python engine/test_org_api.py（純本子模式、不需網路／鑰匙）
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

TMP = tempfile.mkdtemp(prefix="munea-org-api-test-")
os.environ.setdefault("GEMINI_API_KEY", "org-api-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
for key, name in (
    ("MUNEA_ORG_STAFF_PATH", "org_staff.json"), ("MUNEA_ORG_CONSENTS_PATH", "org_consents.json"),
    ("MUNEA_ENTERPRISE_CLIENTS_PATH", "clients.json"), ("MUNEA_ENTERPRISE_SEATS_PATH", "seats.json"),
    ("MUNEA_ENTERPRISE_SEAT_EVENTS_PATH", "seat_events.json"), ("MUNEA_ENTERPRISE_LOCAL_GRANTS_PATH", "grants.json"),
    ("MUNEA_ENTERPRISE_INVOICES_PATH", "invoices.json"), ("MUNEA_WELLBEING_PATH", "wellbeing.json"),
    ("MUNEA_CONVERSATION_SUMMARIES_PATH", "summaries.json"), ("MUNEA_PRODUCT_EVENTS_PATH", "events.json"),
    ("MUNEA_MEDICATION_DOSES_PATH", "doses.json"), ("MUNEA_AUDIT_EVENTS_STORE_PATH", "audit.json"),
):
    os.environ[key] = os.path.join(TMP, name)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import care_week  # noqa: E402
import enterprise_seats  # noqa: E402
import org_api  # noqa: E402

ORG_A = str(uuid.uuid4())
ORG_B = str(uuid.uuid4())
ORG_ESG = str(uuid.uuid4())
SEAT_A1, SEAT_A2, SEAT_A3, SEAT_B1 = (str(uuid.uuid4()) for _ in range(4))
ACC_A1, ACC_A2, ACC_A3, ACC_B1 = (str(uuid.uuid4()) for _ in range(4))
PER_A1, PER_A2, PER_A3, PER_B1 = (str(uuid.uuid4()) for _ in range(4))
ADMIN_A, CASE_A, WORKER_A, ADMIN_B, HR_ESG = (str(uuid.uuid4()) for _ in range(5))
TODAY = datetime.date.today()


def day(offset):
    return (TODAY - datetime.timedelta(days=offset)).isoformat()


def write(path_env, data):
    with open(os.environ[path_env], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def seed_world():
    write("MUNEA_ENTERPRISE_CLIENTS_PATH", [
        {"id": ORG_A, "name": "青松護理之家", "planTier": "plus", "seatQuota": 10, "status": "active", "createdAt": "2026-10-01T00:00:00Z"},
        {"id": ORG_B, "name": "清福養老院", "planTier": "pro", "seatQuota": 20, "status": "active", "createdAt": "2026-10-01T00:00:00Z"},
        {"id": ORG_ESG, "name": "某科技公司", "planTier": "plus", "seatQuota": 50, "status": "active", "clientKind": "esg", "createdAt": "2026-10-01T00:00:00Z"},
    ])
    write("MUNEA_ENTERPRISE_SEATS_PATH", [
        {"id": SEAT_A1, "enterpriseClientId": ORG_A, "inviteEmail": "a1@example.org", "accountId": ACC_A1, "status": "active", "siteLabel": "北院", "createdAt": "2026-10-02T00:00:00Z"},
        {"id": SEAT_A2, "enterpriseClientId": ORG_A, "inviteEmail": "a2@example.org", "accountId": ACC_A2, "status": "active", "siteLabel": "南院", "createdAt": "2026-10-03T00:00:00Z"},
        {"id": SEAT_A3, "enterpriseClientId": ORG_A, "inviteEmail": "a3@example.org", "accountId": ACC_A3, "status": "active", "siteLabel": "北院", "createdAt": "2026-10-04T00:00:00Z"},
        {"id": SEAT_B1, "enterpriseClientId": ORG_B, "inviteEmail": "b1@example.org", "accountId": ACC_B1, "status": "active", "createdAt": "2026-10-02T00:00:00Z"},
    ])
    write("MUNEA_ORG_STAFF_PATH", [
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "email": "admin@a.org", "authUserId": ADMIN_A, "displayName": "A 主任", "role": "org_admin", "status": "active"},
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "email": "case@a.org", "authUserId": CASE_A, "displayName": "A 社工", "role": "case_manager", "siteLabel": "北院", "status": "active"},
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "email": "worker@a.org", "authUserId": WORKER_A, "displayName": "A 照服員", "role": "care_worker", "siteLabel": "北院", "status": "active"},
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "email": "invited@a.org", "displayName": "A 新人", "role": "case_manager", "status": "invited"},
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "email": "gone@a.org", "authUserId": str(uuid.uuid4()), "displayName": "A 離職", "role": "org_admin", "status": "disabled"},
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_B, "email": "admin@b.org", "authUserId": ADMIN_B, "displayName": "B 主任", "role": "org_admin", "status": "active"},
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_ESG, "email": "hr@esg.com", "authUserId": HR_ESG, "displayName": "HR", "role": "org_admin", "status": "active"},
    ])
    write("MUNEA_ORG_CONSENTS_PATH", [
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "seatId": SEAT_A1, "accountId": ACC_A1, "status": "granted", "grantedByRole": "family", "grantedAt": "2026-10-20T00:00:00Z"},
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "seatId": SEAT_A2, "accountId": ACC_A2, "status": "granted", "grantedByRole": "self", "grantedAt": "2026-10-20T00:00:00Z"},
        # SEAT_A3：沒同意（沒有列）
        {"id": str(uuid.uuid4()), "enterpriseClientId": ORG_B, "seatId": SEAT_B1, "accountId": ACC_B1, "status": "granted", "grantedByRole": "family", "grantedAt": "2026-10-20T00:00:00Z"},
    ])
    for env in ("MUNEA_WELLBEING_PATH", "MUNEA_CONVERSATION_SUMMARIES_PATH"):
        write(env, [])
    write("MUNEA_PRODUCT_EVENTS_PATH", {"events": []})
    write("MUNEA_MEDICATION_DOSES_PATH", [])


def auth(uid, email="x@example.org"):
    return {"authUserId": uid, "email": email}


PERSONS = {
    ACC_A1: {"personId": PER_A1, "nickname": "阿嬤", "profileName": "王秀英"},
    ACC_A2: {"personId": PER_A2, "nickname": "", "profileName": "李大同"},
    ACC_A3: {"personId": PER_A3, "nickname": "阿公", "profileName": ""},
    ACC_B1: {"personId": PER_B1, "nickname": "B 阿嬤", "profileName": ""},
}


def fake_loaders(signals=None, summaries=None, events=None):
    signals = signals or {}
    summaries = summaries or {}
    events = events or []
    return {
        "persons": lambda ids: {a: PERSONS[a] for a in ids if a in PERSONS},
        "signals": lambda account_id, person_id: list(signals.get(person_id, [])),
        "summaries": lambda account_id, person_id: list(summaries.get(person_id, [])),
        "guardianEvents": lambda ids, since: [e for e in events if e.get("accountId") in set(ids)],
    }


def sig(person_id, offset, level, said, concerns=()):
    return {"personId": person_id, "date": day(offset), "level": level, "mood": "低落" if level <= 2 else "平穩",
            "wordObs": said, "concerns": list(concerns), "positives": ["孫子來看他"], "createdAt": day(offset) + "T09:00:00Z"}


def call(person_id, offset):
    return {"id": f"cs-{person_id}-{offset}", "personId": person_id, "summary": "這是對話摘要正文，不可外流",
            "createdAt": day(offset) + "T10:00:00Z", "deletedAt": None}


def guardian(account_id, person_id, offset, level):
    return {"accountId": account_id, "personId": person_id, "eventTime": day(offset) + "T11:00:00Z",
            "riskLevel": level, "categories": ["medical_emergency_signal"]}


def walk_keys(obj, out=None):
    out = out if out is not None else set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(str(k).lower())
            walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_keys(v, out)
    return out


def walk_strings(obj, out=None):
    out = out if out is not None else []
    if isinstance(obj, dict):
        for v in obj.values():
            walk_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_strings(v, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        seed_world()
        self.audit = []
        org_api.set_audit_sink(self.audit.append)
        self._today = patch.object(org_api, "_today", return_value=None)
        self._today.start()

    def tearDown(self):
        self._today.stop()
        org_api.set_audit_sink(None)


class IdentityTests(Base):
    def test_unknown_login_is_not_found(self):
        self.assertEqual(org_api.org_me_response(auth(str(uuid.uuid4()))), {"ok": False, "error": "not_found"})

    def test_active_staff_sees_own_org_only(self):
        me = org_api.org_me_response(auth(ADMIN_A))
        self.assertTrue(me["ok"])
        self.assertEqual(me["org"]["name"], "青松護理之家")
        self.assertEqual(me["staff"]["role"], "org_admin")
        self.assertTrue(me["capabilities"]["careWeek"])

    def test_first_login_binds_invited_email_and_audits(self):
        new_uid = str(uuid.uuid4())
        me = org_api.org_me_response(auth(new_uid, email="Invited@A.org"))
        self.assertTrue(me["ok"], me)
        self.assertEqual(me["staff"]["displayName"], "A 新人")
        bound = org_api.list_staff(auth_user_id=new_uid)
        self.assertEqual(len(bound), 1)
        self.assertEqual(bound[0]["status"], "active")
        self.assertIn("org_staff_activated", [e["eventType"] for e in self.audit])

    def test_disabled_staff_is_refused_even_with_matching_email(self):
        gone = org_api.list_staff(email="gone@a.org")[0]
        self.assertEqual(org_api.org_me_response(auth(gone["authUserId"], email="gone@a.org")), {"ok": False, "error": "not_found"})

    def test_email_match_never_overrides_an_already_bound_account(self):
        """別人的 email 對上了也沒用：已綁 auth_user_id 的人員只認那個登入身分。"""
        stranger = str(uuid.uuid4())
        self.assertEqual(org_api.org_me_response(auth(stranger, email="admin@a.org")), {"ok": False, "error": "not_found"})


class ConsentHardGateTests(Base):
    def test_elders_only_lists_consented_seats(self):
        out = org_api.org_elders_response(auth(ADMIN_A), loaders=fake_loaders())
        self.assertTrue(out["ok"])
        self.assertEqual({e["seatId"] for e in out["elders"]}, {SEAT_A1, SEAT_A2})
        self.assertNotIn(SEAT_A3, json.dumps(out))
        self.assertNotIn("阿公", json.dumps(out, ensure_ascii=False))

    def test_revoked_consent_disappears_immediately(self):
        org_api.save_consent({**org_api.list_consents(seat_id=SEAT_A1)[0], "status": "revoked", "revokedAt": "2026-10-29T00:00:00Z"})
        out = org_api.org_elders_response(auth(ADMIN_A), loaders=fake_loaders())
        self.assertEqual({e["seatId"] for e in out["elders"]}, {SEAT_A2})

    def test_care_week_for_unconsented_seat_matches_unknown_seat(self):
        unconsented = org_api.org_elder_care_week_response(auth(ADMIN_A), {"seatId": SEAT_A3}, loaders=fake_loaders())
        unknown = org_api.org_elder_care_week_response(auth(ADMIN_A), {"seatId": str(uuid.uuid4())}, loaders=fake_loaders())
        other_org = org_api.org_elder_care_week_response(auth(ADMIN_A), {"seatId": SEAT_B1}, loaders=fake_loaders())
        self.assertEqual(unconsented, {"ok": False, "error": "not_found"})
        self.assertEqual(unconsented, unknown)
        self.assertEqual(unconsented, other_org)
        self.assertFalse(self.audit, "被擋下的查詢不該留下「看過」的紀錄")


class RoleAndScopeTests(Base):
    def test_org_b_admin_cannot_see_org_a(self):
        out = org_api.org_elders_response(auth(ADMIN_B), loaders=fake_loaders())
        self.assertEqual({e["seatId"] for e in out["elders"]}, {SEAT_B1})
        summary = org_api.org_summary_response(auth(ADMIN_B))
        self.assertEqual(summary["org"]["name"], "清福養老院")

    def test_case_manager_limited_to_own_site(self):
        out = org_api.org_elders_response(auth(CASE_A), loaders=fake_loaders())
        self.assertEqual({e["seatId"] for e in out["elders"]}, {SEAT_A1})  # A2 是南院、A3 沒同意
        self.assertEqual(out["scope"], {"siteLabel": "北院", "siteScoped": True, "level": "L2"})
        south = org_api.org_elder_care_week_response(auth(CASE_A), {"seatId": SEAT_A2}, loaders=fake_loaders())
        self.assertEqual(south, {"ok": False, "error": "not_found"})

    def test_care_worker_gets_flags_but_no_care_week(self):
        out = org_api.org_elders_response(auth(WORKER_A), loaders=fake_loaders())
        self.assertTrue(out["ok"])
        self.assertEqual(out["scope"]["level"], "L1")
        week = org_api.org_elder_care_week_response(auth(WORKER_A), {"seatId": SEAT_A1}, loaders=fake_loaders())
        self.assertEqual(week, {"ok": False, "error": "not_found"})
        self.assertFalse(org_api.org_reports_response(auth(WORKER_A))["ok"])

    def test_esg_client_stays_at_aggregate_level(self):
        me = org_api.org_me_response(auth(HR_ESG))
        self.assertEqual(me["capabilities"]["level"], "L0")
        self.assertFalse(me["capabilities"]["elders"])
        self.assertEqual(org_api.org_elders_response(auth(HR_ESG), loaders=fake_loaders()), {"ok": False, "error": "not_found"})
        self.assertTrue(org_api.org_summary_response(auth(HR_ESG))["ok"])

    def test_summary_is_site_scoped_and_personal_data_free(self):
        out = org_api.org_summary_response(auth(CASE_A))
        self.assertTrue(out["ok"])
        self.assertEqual(out["seats"]["active"], 2)  # 北院兩席（A1、A3）
        self.assertEqual(out["scope"]["siteLabel"], "北院")
        self.assertFalse(walk_keys(out) & {"email", "accountid", "personid", "inviteemail"})


class PrivacyTests(Base):
    def setUp(self):
        super().setUp()
        self.loaders = fake_loaders(
            signals={PER_A1: [sig(PER_A1, 3, 2, "想老伴，不想吃飯", ["膝蓋痠"]), sig(PER_A1, 2, 1, "很累", ["睡不好"]), sig(PER_A1, 1, 2, "沒力氣", [])]},
            summaries={PER_A1: [call(PER_A1, 3), call(PER_A1, 1)]},
            events=[guardian(ACC_A1, PER_A1, 2, "high")],
        )

    def test_care_week_has_trend_and_categories_but_no_sentences(self):
        out = org_api.org_elder_care_week_response(auth(CASE_A), {"seatId": SEAT_A1}, loaders=self.loaders)
        self.assertTrue(out["ok"], out)
        keys = walk_keys(out)
        for banned in ("said", "lastsaid", "wordobs", "summary", "positives", "accountid", "personid", "email", "memorytags"):
            self.assertNotIn(banned, keys, banned)
        text = "\n".join(walk_strings(out))
        self.assertNotIn("想老伴", text)
        self.assertNotIn("對話摘要正文", text)
        self.assertNotIn("孫子來看他", text)
        self.assertEqual(out["week"]["contact"]["calls"], 2)
        self.assertEqual(out["week"]["safety"]["highOrCritical"], 1)
        cats = out["week"]["spokenHealth"]["categories"]
        self.assertEqual(cats, [{"key": "sleep", "label": "睡不好", "count": 1}, {"key": "body", "label": "身體不舒服", "count": 1}])
        for phrase in ("膝蓋痠", "睡不好的事", "很累", "沒力氣"):
            self.assertNotIn(phrase, text, phrase)
        guardian_note = next(a for a in out["anomalies"] if a["type"] == "guardian")
        self.assertNotIn("原句與處理紀錄", guardian_note["suggestion"])
        self.assertIn("看不到通話原句", guardian_note["suggestion"])
        # 最後一通是昨天、沒到 3 天門檻，所以不該亮 no_contact
        self.assertEqual({a["type"] for a in out["anomalies"]}, {"mood_drop", "guardian"})
        self.assertEqual(out["label"], "阿嬤")

    def test_elder_flags_are_computed(self):
        out = org_api.org_elders_response(auth(ADMIN_A), loaders=self.loaders)
        by_seat = {e["seatId"]: e for e in out["elders"]}
        a1 = by_seat[SEAT_A1]
        self.assertEqual(a1["flags"], {"noInteractionToday": True, "lowMood": True, "guardianLit": True})
        self.assertEqual(a1["lastInteractionDate"], day(1))
        a2 = by_seat[SEAT_A2]
        self.assertEqual(a2["flags"]["lowMood"], False)
        self.assertEqual(a2["label"], "李大同")
        self.assertEqual(out["elders"][0]["seatId"], SEAT_A1, "旗標多的排前面")
        self.assertFalse(walk_keys(out) & {"said", "summary", "accountid", "personid", "email"})

    def test_forbidden_key_in_payload_raises_instead_of_leaking(self):
        with self.assertRaises(org_api.OrgPrivacyError):
            org_api.assert_no_forbidden({"ok": True, "elders": [{"label": "x", "email": "a@b"}]})


class SpokenCategoryTests(unittest.TestCase):
    """機構端的掛心事只給「哪一類、幾次」（2026-11-17）。"""

    def test_private_matters_only_show_as_a_count(self):
        cats = org_api._spoken_categories(["想念過世的先生", "跟兒子吵架", "膝蓋痠", "晚上睡不著", "沒胃口", ""])
        self.assertEqual(cats, [
            {"key": "appetite", "label": "吃不下", "count": 1},
            {"key": "sleep", "label": "睡不好", "count": 1},
            {"key": "body", "label": "身體不舒服", "count": 1},
            {"key": "other", "label": "心情或生活上的掛心事", "count": 2},
        ])
        flat = json.dumps(cats, ensure_ascii=False)
        for private in ("先生", "兒子", "吵架", "膝蓋", "想念"):
            self.assertNotIn(private, flat, private)

    def test_output_only_uses_fixed_labels(self):
        allowed = {label for _k, label, _w in org_api.SPOKEN_CATEGORY_RULES} | {org_api.SPOKEN_CATEGORY_OTHER[1]}
        cats = org_api._spoken_categories(["血壓高高的", "隔壁太吵", "擔心錢不夠", "頭暈", "半夜醒來三次"])
        self.assertTrue(cats)
        for c in cats:
            self.assertEqual(set(c), {"key", "label", "count"})
            self.assertIn(c["label"], allowed)
            self.assertIsInstance(c["count"], int)

    def test_feelings_that_sound_like_symptoms_are_not_counted_as_body(self):
        cats = org_api._spoken_categories(["怕給孩子添麻煩", "想到就心酸", "想到他就心痛", "整天悶悶不樂", "要去廟裡燒香", "股票跌很多", "找人吐苦水"])
        self.assertEqual(cats, [{"key": "other", "label": "心情或生活上的掛心事", "count": 7}])
        real = org_api._spoken_categories(["胸悶", "膝蓋痛", "手麻", "昨天跌倒", "一直吐"])
        self.assertEqual(real, [{"key": "body", "label": "身體不舒服", "count": 5}])

    def test_empty_stays_empty(self):
        self.assertEqual(org_api._spoken_categories([]), [])
        self.assertEqual(org_api._spoken_categories(None), [])


class ConsentSafetyTests(Base):
    def test_missing_or_unknown_status_means_not_consented(self):
        self.assertEqual(org_api.normalize_consent({"seatId": SEAT_A3})["status"], "revoked")
        self.assertEqual(org_api.normalize_consent({"seatId": SEAT_A3, "status": "whatever"})["status"], "revoked")
        self.assertEqual(org_api.normalize_consent({"seatId": SEAT_A3, "status": "granted"})["status"], "granted")

    def test_broken_consent_row_does_not_expose_the_elder(self):
        rows = json.load(open(os.environ["MUNEA_ORG_CONSENTS_PATH"], encoding="utf-8"))
        rows.append({"id": str(uuid.uuid4()), "enterpriseClientId": ORG_A, "seatId": SEAT_A3, "accountId": ACC_A3})
        write("MUNEA_ORG_CONSENTS_PATH", rows)
        out = org_api.org_elders_response(auth(ADMIN_A), loaders=fake_loaders())
        self.assertNotIn(SEAT_A3, {e["seatId"] for e in out["elders"]})

    def _add_esg_seat(self):
        seat_id, account_id = str(uuid.uuid4()), str(uuid.uuid4())
        seats = json.load(open(os.environ["MUNEA_ENTERPRISE_SEATS_PATH"], encoding="utf-8"))
        seats.append({"id": seat_id, "enterpriseClientId": ORG_ESG, "inviteEmail": "e1@example.org", "accountId": account_id,
                      "status": "active", "createdAt": "2026-10-05T00:00:00Z"})
        write("MUNEA_ENTERPRISE_SEATS_PATH", seats)
        return seat_id, {"accountId": account_id, "authUserId": str(uuid.uuid4())}

    def test_company_seat_cannot_be_switched_on_but_can_always_be_switched_off(self):
        seat_id, ident = self._add_esg_seat()
        self.assertEqual(org_api.org_consent_set_response(ident, {"seatId": seat_id, "granted": True}),
                         {"ok": False, "error": "consent_not_applicable"})
        self.assertEqual(org_api.list_consents(seat_id=seat_id), [])
        off = org_api.org_consent_set_response(ident, {"seatId": seat_id, "granted": False})
        self.assertTrue(off["ok"])

    def test_grant_without_audit_trail_never_takes_effect(self):
        def boom(_event):
            raise RuntimeError("audit store down")
        org_api.set_audit_sink(boom)
        ident = {"accountId": ACC_A3, "personId": PER_A3, "authUserId": str(uuid.uuid4())}
        out = org_api.org_consent_set_response(ident, {"seatId": SEAT_A3, "granted": True})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "consent_not_recorded")
        self.assertEqual(out["seat"]["consent"]["status"], "none")
        self.assertEqual(org_api.list_consents(seat_id=SEAT_A3), [])
        org_api.set_audit_sink(self.audit.append)
        self.assertNotIn(SEAT_A3, {e["seatId"] for e in org_api.org_elders_response(auth(ADMIN_A), loaders=fake_loaders())["elders"]})

    def test_when_audit_and_storage_are_both_down_consent_is_never_written(self):
        """資料庫整個掛掉：稽核寫不進去、同意表也寫不進去。同意不能停在「已同意」。"""
        def boom(_event):
            raise RuntimeError("audit store down")
        org_api.set_audit_sink(boom)
        ident = {"accountId": ACC_A3, "personId": PER_A3, "authUserId": str(uuid.uuid4())}
        with patch.object(org_api, "save_consent", side_effect=RuntimeError("consent store down")) as save:
            out = org_api.org_consent_set_response(ident, {"seatId": SEAT_A3, "granted": True})
        self.assertEqual(out["error"], "consent_not_recorded")
        save.assert_not_called()
        self.assertEqual(org_api.list_consents(seat_id=SEAT_A3), [])

    def test_already_granted_stays_granted_when_audit_is_down(self):
        def boom(_event):
            raise RuntimeError("audit store down")
        org_api.set_audit_sink(boom)
        ident = {"accountId": ACC_A1, "personId": PER_A1, "authUserId": str(uuid.uuid4())}
        out = org_api.org_consent_set_response(ident, {"seatId": SEAT_A1, "granted": True})
        self.assertEqual(out["error"], "consent_not_recorded")
        self.assertEqual(org_api.list_consents(seat_id=SEAT_A1)[0]["status"], "granted")

    def test_grant_audit_is_written_before_the_consent(self):
        order = []
        org_api.set_audit_sink(lambda e: order.append("audit"))
        real_save = org_api.save_consent
        ident = {"accountId": ACC_A3, "personId": PER_A3, "authUserId": str(uuid.uuid4())}
        with patch.object(org_api, "save_consent", side_effect=lambda item: (order.append("save"), real_save(item))[1]):
            out = org_api.org_consent_set_response(ident, {"seatId": SEAT_A3, "granted": True})
        self.assertTrue(out["ok"])
        self.assertEqual(order, ["audit", "save"])

    def test_consent_does_not_carry_over_when_the_seat_changes_hands(self):
        seats = json.load(open(os.environ["MUNEA_ENTERPRISE_SEATS_PATH"], encoding="utf-8"))
        for s in seats:
            if s["id"] == SEAT_A1:
                s["accountId"] = str(uuid.uuid4())   # 後台把這個席次換綁給另一個人
        write("MUNEA_ENTERPRISE_SEATS_PATH", seats)
        out = org_api.org_elders_response(auth(ADMIN_A), loaders=fake_loaders())
        self.assertNotIn(SEAT_A1, {e["seatId"] for e in out["elders"]})
        # 「已同意人數」也不能把換了人的席次算進去：原本 A1、A2 兩位，現在只剩 A2
        self.assertEqual(org_api.org_summary_response(auth(ADMIN_A))["consent"]["grantedSeats"], 1)

    def test_revoke_still_works_when_audit_is_down(self):
        def boom(_event):
            raise RuntimeError("audit store down")
        org_api.set_audit_sink(boom)
        ident = {"accountId": ACC_A1, "personId": PER_A1, "authUserId": str(uuid.uuid4())}
        out = org_api.org_consent_set_response(ident, {"seatId": SEAT_A1, "granted": False})
        self.assertTrue(out["ok"])
        self.assertEqual(org_api.list_consents(seat_id=SEAT_A1)[0]["status"], "revoked")

    def test_what_org_sees_text_matches_what_is_sent(self):
        ident = {"accountId": ACC_A3, "personId": PER_A3, "authUserId": str(uuid.uuid4())}
        view = org_api.org_consent_status_response(ident)["seats"][0]
        self.assertIn("類別與次數", "".join(view["whatOrgSees"]))
        self.assertNotIn("症狀類別", "".join(view["whatOrgSees"]))
        self.assertIn("短語", "".join(view["whatOrgNeverSees"]))


class PoisonPillTests(Base):
    """把一個獨特字串塞進每一個可能夾帶文字的地方，機構端整份回應都不能出現它。"""

    PILL = "毒餌字串XQ7"

    def test_no_free_text_reaches_the_org(self):
        s1 = sig(PER_A1, 3, 1, self.PILL + "原句", [self.PILL + "掛心事", "膝蓋痠"])
        s1["chatObs"] = self.PILL + "聊天觀察"
        s1["positives"] = [self.PILL + "開心事"]
        s2 = sig(PER_A1, 2, 1, self.PILL + "又一句", [self.PILL + "睡不好"])
        s3 = sig(PER_A1, 1, 1, self.PILL, [])
        g = guardian(ACC_A1, PER_A1, 2, "high")
        g.setdefault("properties", {})["categories"] = [self.PILL + "類別"]
        fake_level = guardian(ACC_A1, PER_A1, 1, self.PILL + "等級")
        loaders = fake_loaders(signals={PER_A1: [s1, s2, s3]}, summaries={PER_A1: [call(PER_A1, 3)]}, events=[g, fake_level])
        week = org_api.org_elder_care_week_response(auth(CASE_A), {"seatId": SEAT_A1}, loaders=loaders)
        elders = org_api.org_elders_response(auth(ADMIN_A), loaders=loaders)
        self.assertTrue(week["ok"] and elders["ok"])
        for name, payload in (("care-week", week), ("elders", elders)):
            self.assertNotIn(self.PILL, json.dumps(payload, ensure_ascii=False), name)
        # 塞進去的短語有被算進次數（證明不是整段沒讀到）
        cats = {c["key"]: c["count"] for c in week["week"]["spokenHealth"]["categories"]}
        self.assertEqual(cats, {"sleep": 1, "body": 1, "other": 1})


class AuditTests(Base):
    def test_care_week_read_is_audited_with_staff_identity(self):
        out = org_api.org_elder_care_week_response(auth(CASE_A), {"seatId": SEAT_A1}, loaders=fake_loaders())
        self.assertTrue(out["ok"])
        reads = [e for e in self.audit if e["eventType"] == "org_care_week_read"]
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]["actorUserId"], CASE_A)
        self.assertEqual(reads[0]["accountId"], ACC_A1)
        self.assertEqual(reads[0]["targetId"], SEAT_A1)
        self.assertEqual(reads[0]["details"]["clientId"], ORG_A)
        self.assertEqual(reads[0]["details"]["role"], "case_manager")

    def test_care_week_is_refused_when_audit_cannot_be_written(self):
        def boom(_event):
            raise RuntimeError("audit store down")
        org_api.set_audit_sink(boom)
        out = org_api.org_elder_care_week_response(auth(CASE_A), {"seatId": SEAT_A1}, loaders=fake_loaders())
        self.assertEqual(out, {"ok": False, "error": "audit_unavailable"})

    def test_care_week_is_refused_when_no_audit_sink_configured(self):
        org_api.set_audit_sink(None)
        out = org_api.org_elder_care_week_response(auth(CASE_A), {"seatId": SEAT_A1}, loaders=fake_loaders())
        self.assertEqual(out, {"ok": False, "error": "audit_unavailable"})


class FamilyConsentTests(Base):
    def test_requires_account_identity(self):
        self.assertEqual(org_api.org_consent_status_response({}), {"ok": False, "error": "identity_required"})
        self.assertEqual(org_api.org_consent_set_response({}, {"seatId": SEAT_A3, "granted": True}), {"ok": False, "error": "identity_required"})

    def test_family_can_grant_and_revoke_own_seat(self):
        ident = {"accountId": ACC_A3, "personId": PER_A3, "authUserId": str(uuid.uuid4())}
        status = org_api.org_consent_status_response(ident)
        self.assertEqual(status["count"], 1)
        self.assertEqual(status["seats"][0]["consent"]["status"], "none")
        self.assertEqual(status["seats"][0]["org"]["name"], "青松護理之家")
        granted = org_api.org_consent_set_response(ident, {"seatId": SEAT_A3, "granted": True})
        self.assertTrue(granted["ok"] and granted["changed"])
        self.assertEqual(granted["seat"]["consent"]["status"], "granted")
        self.assertIn(SEAT_A3, {e["seatId"] for e in org_api.org_elders_response(auth(ADMIN_A), loaders=fake_loaders())["elders"]})
        revoked = org_api.org_consent_set_response(ident, {"seatId": SEAT_A3, "granted": False})
        self.assertEqual(revoked["seat"]["consent"]["status"], "revoked")
        self.assertNotIn(SEAT_A3, {e["seatId"] for e in org_api.org_elders_response(auth(ADMIN_A), loaders=fake_loaders())["elders"]})
        self.assertEqual([e["eventType"] for e in self.audit], ["org_consent_granted", "org_consent_revoked"])

    def test_cannot_touch_someone_elses_seat(self):
        ident = {"accountId": ACC_A3, "personId": PER_A3, "authUserId": str(uuid.uuid4())}
        self.assertEqual(org_api.org_consent_set_response(ident, {"seatId": SEAT_A1, "granted": False}), {"ok": False, "error": "not_found"})
        self.assertEqual(org_api.list_consents(seat_id=SEAT_A1)[0]["status"], "granted")


class AdminTests(Base):
    def test_invite_validates_and_creates_invited_staff(self):
        self.assertEqual(org_api.admin_org_staff_invite_response({})["error"], "client_id_required")
        self.assertEqual(org_api.admin_org_staff_invite_response({"clientId": ORG_A, "email": "nope"})["error"], "email_invalid")
        self.assertEqual(org_api.admin_org_staff_invite_response({"clientId": ORG_A, "email": "x@a.org", "role": "god"})["error"], "role_invalid")
        self.assertEqual(org_api.admin_org_staff_invite_response({"clientId": str(uuid.uuid4()), "email": "x@a.org"})["error"], "client_not_found")
        self.assertEqual(org_api.admin_org_staff_invite_response({"clientId": ORG_A, "email": "ADMIN@a.org"})["error"], "staff_exists")
        out = org_api.admin_org_staff_invite_response({"clientId": ORG_A, "email": "New@A.org", "displayName": "新主任", "siteLabel": "南院"}, actor="sophie")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["staff"]["status"], "invited")
        self.assertEqual(out["staff"]["role"], "org_admin")
        self.assertEqual(out["staff"]["email"], "new@a.org")
        self.assertEqual(out["staff"]["invitedBy"], "sophie")
        self.assertEqual(self.audit[-1]["eventType"], "org_staff_invited")

    def test_consent_status_lists_every_seat(self):
        out = org_api.admin_org_consent_status_response({"clientId": ORG_A})
        self.assertTrue(out["ok"])
        self.assertEqual(out["counts"], {"granted": 2, "revoked": 0, "none": 1})
        self.assertEqual(len(out["seats"]), 3)
        self.assertEqual(len(out["staff"]), 5)
        self.assertEqual(org_api.admin_org_consent_status_response({"clientId": "nope"})["error"], "client_not_found")


class ServerWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server

    def test_admin_paths_registered_and_org_paths_require_login(self):
        s = self.server
        for path in ("/admin/enterprise/staff/invite", "/admin/enterprise/consent/status"):
            self.assertIn(path, s.ADMIN_POST_PATHS)
        for path in ("/org/me", "/org/summary", "/org/elders", "/org/elder/care-week", "/org/reports", "/org-consent", "/org-consent/set"):
            self.assertNotIn(path, s.PUBLIC_POST_PATHS)
            self.assertNotIn(path, s.ADMIN_POST_PATHS)

    def test_org_routes_always_verify_identity_and_allow_missing_account(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), encoding="utf-8").read()
        self.assertIn('or request_path.startswith("/org/"):', src)
        self.assertIn('or request_path.startswith("/org/")),', src)
        for path in ("/org/me", "/org/summary", "/org/elders", "/org/elder/care-week", "/org/reports", "/org-consent", "/org-consent/set"):
            self.assertIn(f'self.path == "{path}"', src)

    def test_audit_sink_is_wired_to_server_audit_events(self):
        # 2026-11-18：機構端稽核走嚴格寫入口（帳號欄空值、不綁請求身分、寫不進就丟錯）
        self.assertIs(self.server.org_api.AUDIT_SINK, self.server.append_org_audit_event_strict)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
