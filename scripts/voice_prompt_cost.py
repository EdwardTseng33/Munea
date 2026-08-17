#!/usr/bin/env python3
"""說明書的真實成本盤（2026-08-10）：她每講一句話之前要重讀的那份，到底多貴。

為什麼要這支：**字數會騙人**。
2026-08-10 實測（gemini-2.5-flash 的計價單位）：
  - 中文段落 ≈ 每個字 0.75 個計價單位
  - 英文段落 ≈ 每個字 0.20 個計價單位
所以那塊 665 個字的英文「講話中途換語言」規則，其實只值 131 個計價單位——
是整份說明書裡**最便宜**的一塊。照字數瘦身，會叫我們去砍最便宜的那塊、
留下真正貴的中文段落。要瘦身之前先跑這支，看清楚錢花在哪一段。

跑法（需要 GEMINI_API_KEY，engine/.env.local 或環境變數都行）：
    python scripts/voice_prompt_cost.py              # 中文正式線
    python scripts/voice_prompt_cost.py --locale ja  # 換一國的書
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "engine")
sys.path.insert(0, ENGINE)
os.environ.setdefault("MUNEA_DATABASE_PROVIDER", "json")
os.environ.setdefault("MUNEA_VOICE_LIVE_LOOKUP", "1")
# 「今日簡報」是當天的資料、不是規則：量成本時排掉，不然數字會跟著今天爬到什麼而跳。
os.environ.setdefault("MUNEA_PERCEPTION_SNAPSHOTS_PATH",
                      os.path.join(ENGINE, "__no_such_briefing__.json"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ENGINE, ".env.local"))
except Exception:
    pass

SECTION_RE = re.compile(r"(?m)^(\[[^\]\n]{1,40}\])")


def split_sections(prompt):
    """依方括號標題切段；開頭那段沒有標題（核心＋安全紅線＋口語風格三本書）。"""
    parts = SECTION_RE.split(prompt)
    rows = [("（核心＋安全紅線＋口語風格）", parts[0])]
    for i in range(1, len(parts), 2):
        body = parts[i + 1] if i + 1 < len(parts) else ""
        rows.append((parts[i], parts[i] + body))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locale", default="zh-TW", help="用哪一國的書（zh-TW／en／ja／es）")
    ap.add_argument("--model", default="gemini-2.5-flash", help="用哪個模型的計價單位換算")
    args = ap.parse_args()

    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("需要 GEMINI_API_KEY（engine/.env.local 或環境變數）")
        return 2

    import live_voice_server
    from google import genai

    client = genai.Client(api_key=key)

    def cost(text):
        return client.models.count_tokens(model=args.model, contents=text).total_tokens

    prompt = live_voice_server.system_instruction(
        locale_profile={"sessionLocale": args.locale} if args.locale != "zh-TW" else None)
    total_chars, total_cost = len(prompt), cost(prompt)
    print(f"整份說明書（{args.locale}）：{total_chars} 字 → {total_cost} 個計價單位")
    print("她每講一句話之前都要重讀一次這份（這條線沒有快取）。\n")
    print("   字數   計價單位   每字   佔比   段落")
    for name, body in sorted(split_sections(prompt), key=lambda r: -len(r[1])):
        n = cost(body)
        print(f"{len(body):7d} {n:9d}   {n / max(1, len(body)):.2f}  {n * 100 / total_cost:5.1f}%   {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
