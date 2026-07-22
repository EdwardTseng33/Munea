# -*- coding: utf-8 -*-
"""免費帳號 60 天未上線自動清理 · 護欄測試（2026-07-22）

守的線：
1. /admin/retention/run 走管理鑰匙門（定時鬧鐘進得來、會員門擋不到），
   但處理端必須自己再驗管理鑰匙（不是開放門）。
2. 預設乾跑——dryRun 沒明講 false，絕不動資料。
3. 參數護欄——閒置天數下限 30（防手滑打 1 天）、單輪刪除上限 200、
   warningLeadDays=0 是合法值（不能被預設 7 吃掉）。
4. 遷移檔 024 政策本體：五道排除、security definer、只給 service_role、
   dry-run 預設 true、審計先落地再刪。

跑法：python engine/test_retention_policy.py
"""
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "retention-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def enabled(self):
        return True

    def run_free_account_retention(self, **kw):
        self.calls.append(kw)
        return {"ok": True, "deletedCount": 0, "warnedCount": 0,
                "authCleanup": {"attempted": 0, "deleted": 0, "failed": []},
                "cleanupRequired": False}


def main():
    root = os.path.dirname(os.path.abspath(__file__))

    # 1) 門的位置：管理鑰匙門、不是會員門、也不是開放門
    check("/admin/retention/run 走管理鑰匙門", "/admin/retention/run" in server.ADMIN_POST_PATHS)
    check("/admin/retention/run 不需會員登入證", server.auth_required_for_path("/admin/retention/run") is False)
    src = open(os.path.join(root, "server.py"), encoding="utf-8").read()
    idx = src.rindex('"/admin/retention/run"')
    check("處理端有驗管理鑰匙", "admin_authorized(self.headers)" in src[idx:idx + 400])

    # 2) + 3) 參數護欄（用假 adapter 收參數、不碰真雲端）
    fake = FakeAdapter()
    original_make_adapter = server.supabase_adapter.make_adapter
    server.supabase_adapter.make_adapter = lambda env=None, identity=None: fake
    try:
        out = server.admin_retention_run({})
        check("沒帶參數＝乾跑", out.get("ok") is True and fake.calls[-1]["dry_run"] is True)
        check("預設 60 天／警示 7 天／上限 20",
              fake.calls[-1]["inactive_days"] == 60
              and fake.calls[-1]["warning_lead_days"] == 7
              and fake.calls[-1]["max_deletions"] == 20)

        server.admin_retention_run({"dryRun": False})
        check("明講 dryRun=false 才真跑", fake.calls[-1]["dry_run"] is False)

        server.admin_retention_run({"inactiveDays": 1, "maxDeletions": 999})
        check("閒置天數下限 30（打 1 天被拉回）", fake.calls[-1]["inactive_days"] == 30)
        check("單輪刪除上限 200（打 999 被壓回）", fake.calls[-1]["max_deletions"] == 200)

        server.admin_retention_run({"warningLeadDays": 0})
        check("warningLeadDays=0 是合法值、不被預設吃掉",
              fake.calls[-1]["warning_lead_days"] == 0)
    finally:
        server.supabase_adapter.make_adapter = original_make_adapter

    # 開機蓋上線章有接（bootstrap 成功路徑）
    check("bootstrap 成功路徑蓋上線章", "touch_account_last_seen" in src)

    # 4) 遷移檔 024 政策本體
    sql_path = os.path.join(root, "..", "supabase", "sql", "024_inactive_free_account_retention.sql")
    check("遷移檔 024 存在", os.path.exists(sql_path))
    sql = open(sql_path, encoding="utf-8").read()
    check("排除 A：測試帳號", "is_test_account = false" in sql and "@munea.net" in sql)
    check("排除 B：付費會員（活訂閱）", "'trial', 'active', 'grace_period'" in sql)
    check("排除 C：購買點數餘額", "wallet_type = 'purchased'" in sql and "balance > 0" in sql)
    check("排除 D：企業席次", "enterprise_seats" in sql)
    check("排除 E：別人家庭圈成員", "elsewhere" in sql)
    check("dry-run 預設 true", "p_dry_run boolean default true" in sql)
    check("security definer + 只給 service_role",
          "security definer" in sql
          and "grant execute on function public.munea_run_free_account_retention" in sql
          and "to service_role" in sql
          and "from authenticated" in sql)
    check("審計先落地再刪（證據不隨帳號消失）",
          sql.index("insert into public.audit_events") < sql.index("delete from public.accounts where id = rec.account_id"))
    check("多路上線訊號（不只看正式登入事件）",
          all(tok in sql for tok in ("last_seen_at", "last_sign_in_at", "push_devices", "voice_sessions", "credit_transactions")))

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 閒置清理護欄全過")


if __name__ == "__main__":
    main()
