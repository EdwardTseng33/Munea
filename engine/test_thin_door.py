# -*- coding: utf-8 -*-
"""薄門通行碼 · 安全閘測試（2026-07-09 · 上線前補洞 P0-3）

守的線：雲端大門開了之後，只有帶對通行碼（X-Munea-Key / ?key=）的 App 進得來；
陌生流量吃閉門羹。沒設 key＝不啟用（本機/區網開發不受影響）。

測的是「比對契約」（三情境），不需真起服務。
跑法：python engine/test_thin_door.py
"""
import sys

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def gate(env_key, presented_key):
    """複刻 server.py do_POST / live_voice_server.py handle 的薄門判定：
    設了 env_key 就要 presented 相符；沒設＝放行。回 True=放行、False=擋。"""
    door = (env_key or "").strip()
    if door and (presented_key or "").strip() != door:
        return False
    return True


def main():
    KEY = "mnk_testkey_abc123"

    # 情境 1：門開著（有 env key）、帶對碼 → 放行
    check("帶對碼→放行", gate(KEY, KEY) is True)
    # 情境 2：門開著、不帶碼 → 擋
    check("不帶碼→擋", gate(KEY, "") is False)
    # 情境 2b：門開著、帶錯碼 → 擋
    check("帶錯碼→擋", gate(KEY, "wrong") is False)
    # 情境 3：門沒開（env 沒設 key）→ 一律放行（本機/開發不受影響）
    check("沒設門→放行(不帶碼)", gate("", "") is True)
    check("沒設門→放行(亂帶碼)", gate("", "whatever") is True)

    # 對照真程式：確認兩個服務都有這道判定（防有人刪掉）
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    srv = open(os.path.join(root, "engine", "server.py"), encoding="utf-8").read()
    voice = open(os.path.join(root, "engine", "live_voice_server.py"), encoding="utf-8").read()
    check("管家腦有薄門(X-Munea-Key)", "X-Munea-Key" in srv and "MUNEA_APP_KEY" in srv)
    check("語音橋有薄門(?key=)", 'MUNEA_APP_KEY' in voice and '_gate' in voice)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 薄門通行碼安全閘全過")


if __name__ == "__main__":
    main()
