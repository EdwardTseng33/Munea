"""清晨定時任務入口：做「今日簡報」功課（真天氣＋空品 → 一句人話 → 存感知抽屜）。

掛法（任一即可、預設 06:30 台灣時間）：
- Windows 工作排程器：.venv\\Scripts\\python.exe engine\\run_daily_briefing.py
- Linux/雲端排程：python engine/run_daily_briefing.py
- 或打端點：POST /admin/daily-briefing（帶管理通行碼）

需要 engine/.env.local 的 GEMINI 等環境（本檔會自己載）。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load_env_local():
    path = os.path.join(HERE, ".env.local")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    _load_env_local()
    import server
    result = server.refresh_daily_briefing(os.environ.get("MUNEA_REGION"))
    if result.get("ok"):
        b = result["briefing"]
        print(f"[daily-briefing] {b['date']} {b['region']}：{b.get('briefingLine') or '(無資料、不瞎編)'}")
        for h in b.get("careHints") or []:
            print(f"[daily-briefing] 關心提示：{h}")
        return 0
    print(f"[daily-briefing] 失敗：{result.get('error')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
