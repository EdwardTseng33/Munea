# -*- coding: utf-8 -*-
"""沐寧 · 每週費用哨兵（發到 Slack #munea-營運）

跑法（城堡定時任務 · 每週一 09:20）：python tools/billing-sentinel.py
做什麼：
  ① Google 雲端（伺服器＋Gemini AI 同一本帳）：報月預算與警戒設定（50/90/100% 自動寄信）
  ② Modal 雲端顯卡（會動的臉）：預付額度，官方沒有查餘額的接口 → 每週提醒 30 秒人工看一眼，低於門檻就充值
  ③ 接訊息接口網址只從 Google 保險箱現拿現用，不落地、不進任何檔案
"""
import subprocess, json, urllib.request, os, datetime

GCLOUD = os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd")
PROJECT = "gen-lang-client-0229303523"   # Google 專案「Munea」
MODAL_LOW_USD = 10                        # Modal 餘額低於這個數＝要充值
GCP_BUDGET_NTD = 500                      # 月預算（警戒 50/90/100% 已設、寄信給 Edward）

def sh(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return ""

def webhook():
    return sh([GCLOUD, "secrets", "versions", "access", "latest",
               "--secret=munea-slack-ops-webhook", f"--project={PROJECT}"])

def budget_line():
    ba = sh([GCLOUD, "billing", "accounts", "list", "--format=value(name)"]).splitlines()
    ba = ba[0].strip() if ba else ""
    if not ba:
        return f"月預算 NT${GCP_BUDGET_NTD}（警戒信 50/90/100% 已設）"
    raw = sh([GCLOUD, "billing", "budgets", "list", f"--billing-account={ba}", "--format=json"])
    try:
        budgets = json.loads(raw) if raw else []
        if budgets:
            b = budgets[0]
            units = ((b.get("amount") or {}).get("specifiedAmount") or {}).get("units", GCP_BUDGET_NTD)
            ths = [str(int(float(t.get("thresholdPercent", 0)) * 100)) + "%" for t in (b.get("thresholdRules") or [])]
            return f"月預算 NT${units}、警戒 {('/'.join(ths)) or '50%/90%/100%'} 自動寄信給 Edward"
    except Exception:
        pass
    return f"月預算 NT${GCP_BUDGET_NTD}（警戒信 50/90/100% 已設）"

def main():
    today = datetime.date.today().strftime("%m/%d")
    text = (
        f"💰 *每週費用哨兵*（{today}）\n"
        f"① *Google 雲端*（伺服器＋Gemini AI 同一本帳）：{budget_line()}；帳單頁 <https://console.cloud.google.com/billing|點這看本月花費>\n"
        f"② *Modal 雲端顯卡*（會動的臉）：預付額度—<https://modal.com/settings/usage|點這看餘額>，*低於 US${MODAL_LOW_USD} 就充值*（官方沒有自動查餘額的口，先每週提醒 30 秒看一眼）\n"
        f"③ 蘋果開發者年費下次續約 2027/7；資料櫃（Supabase）目前免費層夠用\n"
        f"（超標或異常時 Google 會另外寄信；這則是每週一的固定巡帳）"
    )
    url = webhook()
    if not url.startswith("http"):
        print("拿不到接訊息接口網址（保險箱讀取失敗），這次不發")
        return 1
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()
    print("費用哨兵已發 #munea-營運")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
