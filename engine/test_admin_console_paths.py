# -*- coding: utf-8 -*-
"""營運後台讀取接口通行 · 連動護欄（2026-07-21）

守的線：後台前端 admin.js 的 EP_LIST 每加一支讀取接口，後端 ADMIN_POST_PATHS
必須同步登記——漏登記的話請求會被「會員登入門」擋在處理程式之前，
後台那一頁永遠是空的，而且錯誤訊息（auth_token_missing）看起來像登入壞了、
不像少登記，非常難查。

真踩過：2026-07-21「成長與黏著」頁 /admin/growth-metrics 漏登記，
測試機實測回 auth_token_missing，前端拿不到任何資料。

這支測試把兩邊釘成連動：EP_LIST ⊆ ADMIN_POST_PATHS，且都不需會員登入證。

跑法：python engine/test_admin_console_paths.py
"""
import os
import re
import sys

os.environ.setdefault("GEMINI_API_KEY", "admin-console-paths-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def console_paths():
    """撈出 web/src/admin.js 會打的所有 /admin/* 路徑。

    刻意掃整份檔案、不只掃 EP_LIST——企業席次那幾頁是各頁進場才現查、
    不掛在 EP_LIST 裡（見 admin.js 註解），只掃 EP_LIST 會漏守它們。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "web", "src", "admin.js"), encoding="utf-8").read()
    return sorted(set(re.findall(r'"(/admin/[a-z0-9][a-z0-9/-]*)"', src)))


def main():
    paths = console_paths()
    check("admin.js 撈得到接口（不是 0 支）", len(paths) > 0)
    print(f"  （後台前端共會打 {len(paths)} 支 /admin 接口）")

    for path in paths:
        check(f"{path} 已登記在管理鑰匙通行清單", path in server.ADMIN_POST_PATHS)
        check(f"{path} 不需會員登入證", server.auth_required_for_path(path) is False)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        print("   修法：把缺的路徑加進 engine/server.py 的 ADMIN_POST_PATHS。")
        sys.exit(1)
    print("✅ 後台讀取接口通行護欄全過")


if __name__ == "__main__":
    main()
