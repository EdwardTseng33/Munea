# -*- coding: utf-8 -*-
"""就診摘要 endpoint · 接線與認人防線（M1 · PR-4b · 配 visit_summary.py）

`visit_summary.py` 的純函式已由 `test_visit_summary.py` 測過「組得對不對」。
這支測的是接線之後才會出現的三件事，每一件都是出過事或會出人命的：

一、**認錯人**（沿用 test_health_visibility 同一條線）
    健康資料把 A 的講給 B 聽，比不講嚴重得多。所以：
    · 認不出身分 → 什麼都不給（不退預設身分、不猜）
    · payload 裡塞別人的 personId → 一律不採信（那可以偽造）
    · 別人的記憶不得混進我的摘要

二、**部分資料讀不到要說出來**
    一份少了血壓的摘要，看起來就像「他這段期間都沒量」——醫師會據此判斷。
    悄悄少一塊比整份失敗更危險。任何一路撈失敗都必須回報在 partial 裡。

三、**期間參數不可被亂塞**
    前端傳壞值不該炸、也不該默默給一個誰也不知道多長的期間。

跑法：python engine/test_visit_summary_endpoint.py（純本子模式、不需網路/鑰匙）
"""
import datetime
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"   # 走引擎本子、測接線本身

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402
import visit_summary  # noqa: E402

FAILS = []

ME = "person-me"
SOMEONE_ELSE = "person-other"
FAM = "fam-visit-test"


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def as_person(person_id, family_group_id=FAM):
    return server.REQUEST_DATA_IDENTITY.set({
        "accountId": "acct-test", "personId": person_id,
        "familyGroupId": family_group_id, "authUserId": "auth-test",
    })


def day(offset):
    return (datetime.date.today() - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")


def memory_for(person_id, content, offset=2):
    return {
        "type": "health_context", "content": content, "confidence": 0.9,
        "personId": person_id, "createdAt": day(offset) + "T09:00:00Z",
    }


# ---- 一、認人防線 ----
def test_no_identity_no_summary():
    token = server.REQUEST_DATA_IDENTITY.set({})
    try:
        out = server.visit_summary_response({"periodDays": 14})
        check("認不出身分 → 不給摘要（不退預設身分、不猜）",
              out.get("ok") is False and out.get("error") == "identity_required")
        check("認不出身分 → 連空摘要都不給（免得畫面照樣印出一頁）", "summary" not in out)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)


def test_payload_person_id_is_ignored():
    """payload 想指定別人 → 一律不採信，只認已驗證身分。"""
    server.save_memory_items([
        memory_for(ME, "我的膝蓋痠"),
        memory_for(SOMEONE_ELSE, "別人的胸口悶"),
    ])
    token = as_person(ME)
    try:
        out = server.visit_summary_response({"periodDays": 14, "personId": SOMEONE_ELSE})
        texts = "".join(e.get("text", "") for e in out["summary"]["timeline"])
        check("payload 塞別人的 personId → 不採信，仍是我自己的摘要", "膝蓋痠" in texts)
        check("payload 塞別人的 personId → 拿不到別人的症狀", "胸口悶" not in texts)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)


def test_other_person_memories_never_mix_in():
    server.save_memory_items([
        memory_for(ME, "我自己的頭暈"),
        memory_for(SOMEONE_ELSE, "另一位長輩的心悸"),
        memory_for(SOMEONE_ELSE, "另一位長輩的背痛"),
    ])
    token = as_person(ME)
    try:
        out = server.visit_summary_response({"periodDays": 14})
        texts = "".join(e.get("text", "") for e in out["summary"]["timeline"])
        check("別人的症狀不得混進我的摘要（心悸）", "心悸" not in texts)
        check("別人的症狀不得混進我的摘要（背痛）", "背痛" not in texts)
        check("我自己的症狀要在", "頭暈" in texts)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)


# ---- 二、部分資料讀不到要說出來 ----
def test_partial_sources_are_reported():
    server.save_memory_items([memory_for(ME, "膝蓋痠")])
    original = server.load_medication_doses
    server.load_medication_doses = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    token = as_person(ME)
    try:
        out = server.visit_summary_response({"periodDays": 14})
        check("用藥撈失敗 → 摘要仍生得出來（不整份 500）", out.get("ok") is True)
        check("用藥撈失敗 → partial 要誠實回報，不可悄悄少一塊",
              "medication" in (out["summary"].get("partial") or []))
    finally:
        server.load_medication_doses = original
        server.REQUEST_DATA_IDENTITY.reset(token)


def test_healthy_path_reports_no_partial():
    server.save_memory_items([memory_for(ME, "膝蓋痠")])
    token = as_person(ME)
    try:
        out = server.visit_summary_response({"periodDays": 14})
        check("三路都讀到 → partial 應為空（不可無故亮警示）",
              out["summary"].get("partial") == [])
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)


# ---- 三、期間參數 ----
def test_period_values():
    server.save_memory_items([])
    token = as_person(ME)
    try:
        for period in visit_summary.PERIOD_DAYS:
            out = server.visit_summary_response({"periodDays": period})
            check(f"期間 {period} 天 → 照收", out["summary"]["periodDays"] == period)
        for bogus in ("abc", -1, 0, 9999, None, {"x": 1}):
            out = server.visit_summary_response({"periodDays": bogus})
            check(f"壞期間 {bogus!r} → 退回預設、不炸",
                  out["summary"]["periodDays"] == visit_summary.DEFAULT_PERIOD)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)


# ---- 四、接線本身 ----
def test_registered_in_contracts():
    source = open(os.path.join(HERE, "server.py"), encoding="utf-8").read()
    check("路由有接上 /visit-summary", 'self.path == "/visit-summary"' in source)
    check("契約清單有列 visit-summary", '"visit-summary"' in source)


def main():
    test_no_identity_no_summary()
    test_payload_person_id_is_ignored()
    test_other_person_memories_never_mix_in()
    test_partial_sources_are_reported()
    test_healthy_path_reports_no_partial()
    test_period_values()
    test_registered_in_contracts()
    print()
    if FAILS:
        print("FAILED: " + "; ".join(FAILS))
        sys.exit(1)
    print("✅ 就診摘要 endpoint：認人防線＋部分資料揭露＋期間參數 全過")


if __name__ == "__main__":
    main()
