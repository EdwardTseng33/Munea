# -*- coding: utf-8 -*-
"""AI 端點限流 · 護欄測試（2026-07-16 · 上線前後端完善度）

守的線：聊天/語音/記憶/感知這些每一下都燒 AI 費用的入口，同一個人對同一條端點
每分鐘有上限；超額回 429 + Retry-After，不碰資料櫃、不碰 LLM。
App key 全 App 共用、CORS 擋不住非瀏覽器客戶端——這道閘是帳單的最後防線。

跑法：python engine/test_ai_rate_limit.py
"""
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "ai-rate-limit-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def reset(limit=None, enabled=None):
    server._AI_RATE_HITS.clear()
    if limit is None:
        os.environ.pop("MUNEA_AI_RATE_LIMIT_PER_MINUTE", None)
    else:
        os.environ["MUNEA_AI_RATE_LIMIT_PER_MINUTE"] = str(limit)
    if enabled is None:
        os.environ.pop("MUNEA_AI_RATE_LIMIT_ENABLED", None)
    else:
        os.environ["MUNEA_AI_RATE_LIMIT_ENABLED"] = enabled


def main():
    # 情境 1：上限內一律放行
    reset(limit=3)
    results = [server.ai_rate_limited("user-a", "/chat", now=100.0 + i) for i in range(3)]
    check("上限內放行", all(r == (False, 0) for r in results))

    # 情境 2：超額被擋、且給出合理的等待秒數
    limited, retry_after = server.ai_rate_limited("user-a", "/chat", now=104.0)
    check("超額被擋", limited is True)
    check("等待秒數合理(1~61)", 1 <= retry_after <= 61)

    # 情境 3：視窗滑過（60 秒後）自動恢復
    limited, _ = server.ai_rate_limited("user-a", "/chat", now=100.0 + server.AI_RATE_WINDOW + 1)
    check("視窗滑過→恢復", limited is False)

    # 情境 4：不同人互不影響
    reset(limit=1)
    server.ai_rate_limited("user-a", "/chat", now=200.0)
    limited_b, _ = server.ai_rate_limited("user-b", "/chat", now=200.0)
    check("不同人各算各的", limited_b is False)

    # 情境 5：同一人、不同端點互不影響
    reset(limit=1)
    server.ai_rate_limited("user-a", "/chat", now=300.0)
    limited_other, _ = server.ai_rate_limited("user-a", "/memory/extract", now=300.0)
    check("不同端點各算各的", limited_other is False)

    # 情境 6：關掉開關＝不啟用（本機/開發不受影響）
    reset(limit=1, enabled="0")
    server.ai_rate_limited("user-a", "/chat", now=400.0)
    limited, _ = server.ai_rate_limited("user-a", "/chat", now=400.0)
    check("開關關閉→不限", limited is False)

    # 情境 7：沒有身分鍵（極端狀況）不誤鎖
    reset(limit=1)
    check("空身分鍵→放行", server.ai_rate_limited("", "/chat") == (False, 0))

    # 情境 8：環境變數亂填不會炸、退回預設值
    reset()
    os.environ["MUNEA_AI_RATE_LIMIT_PER_MINUTE"] = "not-a-number"
    check("亂填上限→退回預設", server.ai_rate_limit_per_minute() == server.AI_RATE_DEFAULT_LIMIT)
    reset()

    # 契約 1：燒錢端點都在受管清單裡（防有人改路由忘了帶閘）
    expected = {
        "/open", "/chat", "/voice-note", "/persona/context",
        "/memory/extract", "/memory/retrieve", "/conversation-summary",
        "/butler/post-turn", "/guardian/evaluate",
        "/perception/topic-plan", "/perception/snapshot", "/proactive/opening",
    }
    check("燒錢端點全數受管", expected <= server.AI_RATE_LIMITED_PATHS)

    # 契約 2：入口真的接了閘（防有人刪掉 do_POST 那段）
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    srv = open(os.path.join(root, "engine", "server.py"), encoding="utf-8").read()
    check("入口有接限流閘", "ai_rate_limited(_actor, request_path)" in srv)
    check("超額回 429+Retry-After", '"rate_limited"' in srv and '"Retry-After"' in srv)
    check("已驗證用戶以 authUserId 計", 'auth_gate.get("auth") or {}).get("authUserId")' in srv)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ AI 端點限流護欄全過")


if __name__ == "__main__":
    main()
