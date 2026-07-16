# -*- coding: utf-8 -*-
"""情緒紀錄 moodKey 讀回防線（2026-07-16 · 真機情緒卡變磚事故）

守的線：`wellbeing_row_to_signal` 回給 App 的 moodKey 必須是 0-5 數字或 None，
絕不能是英文字串。事故根因：`facts.get("moodKey") or row.get("mood")` 把
moodKey=0（開心）當成沒有值、退回英文 mood 字，App 端拿字串當編號 →
重畫情緒卡時炸掉 → 按鍵綁定沒掛回 → 整張卡死掉且壞值存進手機快取。

跑法：python engine/test_wellbeing_mood_key.py（純轉換邏輯、不需網路/鑰匙）
"""
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from supabase_adapter import SupabaseAdapter  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def signal_for(facts, mood):
    return SupabaseAdapter.wellbeing_row_to_signal({"facts": facts, "mood": mood})


# 1) moodKey=0（開心）是合法值，讀回必須還是 0、不能退成英文字
check("moodKey 0 survives round-trip", signal_for({"moodKey": 0}, "happy")["moodKey"] == 0)

# 2) 一般數字照舊
check("moodKey 5 survives round-trip", signal_for({"moodKey": 5}, "irritated")["moodKey"] == 5)

# 3) facts 沒帶 moodKey：英文 mood 詞要轉成 App 的 0-5 編號、不能原字丟回
for word, key in [("happy", 0), ("pleasant", 1), ("steady", 2), ("tired", 3), ("low", 3), ("irritated", 4)]:
    check("mood word %s maps to %d" % (word, key), signal_for({}, word)["moodKey"] == key)

# 4) 對不上的 mood（mixed/unknown/怪值）回 None、讓 App 端跳過，絕不回字串
for word in ["mixed", "unknown", "whatever"]:
    got = signal_for({}, word)["moodKey"]
    check("mood word %s yields None (got %r)" % (word, got), got is None)

# 5) 整包讀回不能出現「字串 moodKey」
rows = [{"facts": {"moodKey": 0}, "mood": "happy"}, {"facts": {}, "mood": "steady"}, {"facts": {}, "mood": "unknown"}]
signals = [SupabaseAdapter.wellbeing_row_to_signal(r) for r in rows]
check("no string moodKey ever returned", all(not isinstance(s["moodKey"], str) for s in signals))

if FAILS:
    print("FAILED: %d" % len(FAILS))
    sys.exit(1)
print("wellbeing moodKey read-back contract OK")
