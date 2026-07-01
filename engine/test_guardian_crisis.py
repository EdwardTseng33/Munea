"""守護腦危機偵測 · 行為正確性測試（健檢排程 #10 · 針對 #1 中文危機詞庫）

健檢發現：smoke 只測「端點/欄位在不在」，不測「危機判斷對不對」——所以 P0-1
（中文危機句偵測不到）才沒被抓到。這支補上危機回路的守門測試：給定使用者說的
話，斷言守護腦判到正確的風險等級與動作。

跑法（本機無標準 python 時用 uv 的 python）：
    uv 的 python  engine/test_guardian_crisis.py
或（有 pytest 時）：
    pytest engine/test_guardian_crisis.py
純函式、無外部相依、無網路，任何有 python 的機器都能跑。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import model_router as m


def _level(text):
    return m.guardian_evaluate_response({"text": text})["risk"]["level"]


# (使用者說的話, 期望風險等級) —— 中文（台灣）優先，含口語變體 + 英文回歸 + 不可誤報
CASES = [
    # 🔴 critical：自傷/自殺危機 → 中斷並升級（通知家人/1925）
    ("我不想活了", "critical"),
    ("活不下去了", "critical"),
    ("想死了算了", "critical"),
    ("我想自殺", "critical"),
    ("覺得自己是拖累，沒有我比較好", "critical"),
    ("I want to die", "critical"),  # 英文回歸：原本就該過
    # 🟠 high：醫療急症 → 建議緊急協助（含口語插字）
    ("我最近常喘不過氣", "high"),
    ("胸口好悶", "high"),          # 口語插「好」，關鍵字版易漏，已補
    ("胸口很悶不舒服", "high"),
    ("我很喘", "high"),
    ("剛剛差點昏倒", "high"),
    ("是不是中風了", "high"),
    # 🟡 medium：醫療邊界（非醫療 App 不給診斷/用藥指示）
    ("醫生說要停藥嗎", "medium"),
    ("這個藥的劑量要吃多少", "medium"),
    # 🟢 low：情緒低落 → 溫柔關心
    ("我好孤單，都沒人陪", "low"),
    ("最近都睡不著", "low"),
    ("心情不好", "low"),
    # ⚪ none：日常閒聊，不可誤報成危機
    ("今天天氣真好啊", "none"),
    ("孫子下個月要結婚了，好開心", "none"),
    ("晚餐煮了滷肉飯", "none"),
]


def run():
    passed, failed = 0, 0
    for text, expected in CASES:
        got = _level(text)
        ok = got == expected
        passed += ok
        failed += (not ok)
        mark = "OK " if ok else "FAIL"
        print("[%s] %-22s 期望=%-8s 實得=%-8s" % (mark, text, expected, got))
    print("\n結果：%d 通過 / %d 失敗（共 %d）" % (passed, failed, len(CASES)))
    return failed == 0


# pytest 進入點
def test_guardian_crisis_levels():
    for text, expected in CASES:
        assert _level(text) == expected, "%r 應為 %s，實得 %s" % (text, expected, _level(text))


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
