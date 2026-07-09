# -*- coding: utf-8 -*-
"""健康數據真同步 · 按人合併防線測試（2026-07-09 · 上線前補洞 P0-1）

守的線：兩支手機把各自 vitals 推上同一家 → 雲端/本子必須「按人合併」、
絕不整包覆蓋（否則家人看到錯的健康值）。外加雲端 23514（白名單沒 vitals）
必須安靜退引擎本子、不炸用戶。

跑法：python engine/test_vitals_sync.py（純本子模式、不需網路/鑰匙）
"""
import os
import sys
import tempfile

os.environ.setdefault("GEMINI_API_KEY", "test")
# 強制走引擎本子（不連 Supabase）——測合併邏輯本身
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main():
    # 把家庭本子指到暫存檔（不污染真檔）
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    server.FAMILY_STATE_STORE_PATH = tmp.name

    group = "fam-test-merge"
    pA, pB = "person-A", "person-B"

    # A 手機推自己的 vitals
    r1 = server.family_state_response({
        "action": "save", "familyGroupId": group, "key": "vitals",
        "personId": pA, "value": {pA: {"name": "甲", "bpSys": 120, "bpDia": 78, "day": "2026-07-09"}},
    })
    check("A 推 vitals ok", r1.get("ok") is True)

    # B 手機推自己的 vitals（同一家）
    r2 = server.family_state_response({
        "action": "save", "familyGroupId": group, "key": "vitals",
        "personId": pB, "value": {pB: {"name": "乙", "bpSys": 135, "bpDia": 88, "day": "2026-07-09"}},
    })
    check("B 推 vitals ok", r2.get("ok") is True)

    # 讀回：兩個人都要在（B 不得蓋掉 A）——這是核心防線
    loaded = server.family_state_response({"action": "load", "familyGroupId": group})
    v = (loaded.get("state") or {}).get("vitals") or {}
    check("A 的資料還在（沒被 B 蓋掉）", isinstance(v, dict) and pA in v and v[pA].get("bpSys") == 120)
    check("B 的資料也在", pB in v and v[pB].get("bpSys") == 135)

    # A 再更新一次自己（同人覆蓋自己 OK、但仍不動 B）
    server.family_state_response({
        "action": "save", "familyGroupId": group, "key": "vitals",
        "personId": pA, "value": {pA: {"name": "甲", "bpSys": 118, "bpDia": 76, "day": "2026-07-09"}},
    })
    loaded2 = server.family_state_response({"action": "load", "familyGroupId": group})
    v2 = (loaded2.get("state") or {}).get("vitals") or {}
    check("A 更新自己數值生效（118）", v2.get(pA, {}).get("bpSys") == 118)
    check("B 仍在、沒被 A 的更新波及", v2.get(pB, {}).get("bpSys") == 135)

    # vitals 有進白名單（008 對應的程式端）
    check("vitals 在允許鑰匙白名單", "vitals" in server.FAMILY_STATE_KEYS)
    check("vitals 在雲端白名單（008）", "vitals" in server.FAMILY_STATE_SUPABASE_KEYS)

    try:
        os.unlink(tmp.name)
    except Exception:
        pass

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ vitals 按人合併防線全過")


if __name__ == "__main__":
    main()
