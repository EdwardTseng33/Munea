# -*- coding: utf-8 -*-
"""週關懷摘要 endpoint（/care-week）· 接線與認人防線（補助案 C2 · 2026-10-13）

care_week.py 的純函式由 test_care_week.py 測「組得對不對」。這支測接線之後才會出現的事，
每一件都是出過事或會出人命的（規矩照抄 test_visit_summary_endpoint）：

一、認錯人：認不出身分 → 什麼都不給；payload 塞別人的 personId → 不採信；別人的心情、別人的守護腦事件不得混進來。
二、部分資料讀不到要說出來：守護腦那段撈失敗，摘要仍生得出來、但 partial 要寫 safety——
    悄悄少一段看起來就像「這週很平安」。
三、期間與設定參數不可被亂塞：壞值不炸、退預設。

跑法：python engine/test_care_week_endpoint.py（純本子模式、不需網路／鑰匙）
"""
import datetime
import os
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402

FAILS = []
ME = "person-me"
SOMEONE_ELSE = "person-other"
FAM = "fam-care-week-test"


def check(name, cond, detail=None):
    print(("  OK  " if cond else " FAIL ") + name + ("" if cond or detail is None else "  → %r" % (detail,)))
    if not cond:
        FAILS.append(name)


def as_person(person_id, family_group_id=FAM):
    return server.REQUEST_DATA_IDENTITY.set({
        "accountId": "acct-test", "personId": person_id,
        "familyGroupId": family_group_id, "authUserId": "auth-test",
    })


def day(offset):
    return (datetime.date.today() - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")


def signal(person_id, offset, level, said, concerns=None):
    return {"id": "wb-%s-%d" % (person_id, offset), "personId": person_id, "date": day(offset), "level": level,
            "mood": "低落" if level <= 2 else "平穩", "wordObs": said, "concerns": concerns or [],
            "positives": [], "createdAt": day(offset) + "T09:00:00Z"}


def summary(person_id, offset):
    return {"id": "cs-%s-%d" % (person_id, offset), "personId": person_id, "summary": "通話摘要",
            "memoryTags": [], "safetyRelevant": False, "createdAt": day(offset) + "T10:00:00Z", "deletedAt": None}


def guardian_event(person_id, offset, level, cats):
    return {"eventName": "guardian_risk_evaluated", "personId": person_id, "familyGroupId": FAM,
            "eventTime": day(offset) + "T11:00:00Z",
            "properties": {"riskLevel": level, "categories": cats, "analyticsExcluded": True}}


class Store:
    """三份本子都換成暫存檔，測完刪掉——不碰 engine/ 裡真的 json。"""

    def __enter__(self):
        self.files = []
        self.patches = []
        for attr, initial in (("WELLBEING_PATH", "[]"), ("CONVERSATION_SUMMARIES_PATH", "[]"),
                              ("PRODUCT_EVENTS_PATH", '{"events": []}')):
            handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
            handle.write(initial.encode("utf-8"))
            handle.close()
            self.files.append(handle.name)
            p = patch.object(server, attr, handle.name)
            p.start()
            self.patches.append(p)
        return self

    def __exit__(self, *a):
        for p in self.patches:
            p.stop()
        for f in self.files:
            try:
                os.unlink(f)
            except OSError:
                pass

    @staticmethod
    def seed(signals=(), summaries=(), events=()):
        server.write_json_file(server.WELLBEING_PATH, list(signals))
        server.write_json_file(server.CONVERSATION_SUMMARIES_PATH, list(summaries))
        for ev in events:
            server.append_product_event(ev)


# ---- 一、認人防線 ----
def test_no_identity_no_week():
    with Store():
        token = server.REQUEST_DATA_IDENTITY.set({})
        try:
            out = server.care_week_response({"days": 7})
            check("認不出身分 → 不給摘要", out.get("ok") is False and out.get("error") == "identity_required")
            check("認不出身分 → 連空摘要、文字都不給", "week" not in out and "text" not in out)
        finally:
            server.REQUEST_DATA_IDENTITY.reset(token)


def test_payload_person_id_is_ignored_and_others_never_mix_in():
    with Store() as s:
        s.seed(
            signals=[signal(ME, 1, 2, "想老伴", ["膝蓋痠"]), signal(SOMEONE_ELSE, 1, 1, "別人的話", ["心悸"])],
            summaries=[summary(ME, 1), summary(SOMEONE_ELSE, 0)],
            events=[guardian_event(ME, 2, "high", ["medical_emergency_signal"]),
                    guardian_event(SOMEONE_ELSE, 1, "critical", ["self_harm_crisis"])],
        )
        token = as_person(ME)
        try:
            out = server.care_week_response({"days": 7, "personId": SOMEONE_ELSE})
            check("payload 塞別人的 personId → 不採信，仍是我的摘要", out.get("ok") and out["week"]["personId"] == ME)
            check("我的口述症狀要在", "膝蓋痠" in out["text"])
            check("別人的症狀不得混進來", "心悸" not in out["text"] and "別人的話" not in out["text"])
            check("別人的守護腦事件不得混進來（我只有 1 次 high）",
                  out["week"]["safety"]["counts"] == {"high": 1})
            check("別人的通話不算我的（我只有 1 通）", out["week"]["contact"]["calls"] == 1)
        finally:
            server.REQUEST_DATA_IDENTITY.reset(token)


# ---- 二、部分資料讀不到要說出來 ----
def test_partial_is_reported():
    with Store() as s:
        s.seed(signals=[signal(ME, 1, 3, "今天澆花")], summaries=[summary(ME, 1)])
        original = server.load_product_events
        server.load_product_events = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        token = as_person(ME)
        try:
            out = server.care_week_response({"days": 7})
            check("守護腦撈失敗 → 摘要仍生得出來", out.get("ok") is True)
            check("守護腦撈失敗 → partial 要寫 safety，不可悄悄少一段", "safety" in (out.get("partial") or []))
            check("partial 也要寫在 week 裡（畫面會畫）", "safety" in (out["week"].get("partial") or []))
        finally:
            server.load_product_events = original
            server.REQUEST_DATA_IDENTITY.reset(token)


def test_healthy_path_no_partial_and_anomalies_wired():
    with Store() as s:
        s.seed(
            signals=[signal(ME, 3, 1, "沒什麼意思"), signal(ME, 2, 2, "不想動"), signal(ME, 1, 1, "累")],
            summaries=[summary(ME, 5)],
            events=[guardian_event(ME, 2, "critical", ["self_harm_crisis"])],
        )
        token = as_person(ME)
        try:
            out = server.care_week_response({"days": 7, "noContactDays": 3})
            check("正常路徑 partial 為空", out.get("ok") and out.get("partial") == [])
            types = sorted(a["type"] for a in out["anomalies"])
            check("三條規則都接上（連續低落、沒聯絡、守護腦）", types == ["guardian", "mood_drop", "no_contact"], types)
            check("文字版帶【要看一下】", "要看一下" in out["text"])
            for bad in ("可能因為", "導致", "分數", "診斷"):
                check("文字版沒有判定用語：" + bad, bad not in out["text"])
        finally:
            server.REQUEST_DATA_IDENTITY.reset(token)


# ---- 三、參數不可被亂塞 ----
def test_bad_params_fall_back():
    with Store():
        token = as_person(ME)
        try:
            out = server.care_week_response({"days": "abc", "noContactDays": "xyz"})
            check("days 壞值 → 退預設 7", out.get("ok") and out["week"]["period"]["days"] == 7)
            out = server.care_week_response({"days": 999})
            check("days 太大 → 封頂 31", out["week"]["period"]["days"] == 31)
        finally:
            server.REQUEST_DATA_IDENTITY.reset(token)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print("\n結果：%d 項失敗" % len(FAILS) if FAILS else "\n結果：全部通過")
    sys.exit(1 if FAILS else 0)
