# -*- coding: utf-8 -*-
"""維護入口通行 · 護欄測試（2026-07-17 · 晨料鬧鐘接線）

守的線：晨料備製／記憶整理三個維護入口要讓「拿管理鑰匙的定時鬧鐘」進得來
（不被會員登入門擋下），同時處理端必須各自再驗管理鑰匙（不是開放門）。

跑法：python engine/test_admin_maintenance_paths.py
"""
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "admin-paths-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main():
    maintenance = ("/admin/daily-briefing", "/admin/memory-consolidate", "/admin/memory-living-profile")

    # 三個維護入口在「管理鑰匙通行」清單裡（漏列＝定時鬧鐘永遠被會員門擋下、7/17 實測 401）
    for path in maintenance:
        check(f"{path} 走管理鑰匙門", path in server.ADMIN_POST_PATHS)
        check(f"{path} 不需會員登入證", server.auth_required_for_path(path) is False)

    # 但不是開放門：處理端必須各自再驗管理鑰匙
    root = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(root, "server.py"), encoding="utf-8").read()
    for marker in ('"/admin/daily-briefing"', '"/admin/memory-consolidate"', '"/admin/memory-living-profile"'):
        idx = src.rindex(marker)
        window = src[idx:idx + 400]
        check(f"{marker} 處理端有驗管理鑰匙", "admin_authorized(self.headers)" in window)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 維護入口通行護欄全過")


if __name__ == "__main__":
    main()
