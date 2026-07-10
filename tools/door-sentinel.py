# -*- coding: utf-8 -*-
"""沐寧 · 門口哨兵（門一鎖上就發 Slack #munea-營運）

由來：2026-07-09 一次部署把語音橋/管家腦的「公開大門」鎖上（--no-allow-unauthenticated），
      App 全被 403 擋→退回本機罐頭句「我聽見了」，卻是 Edward 手機測到才發現、繞了半天。
      這隻哨兵＝以後門一壞（被鎖 / 掛掉）就自動在營運頻道叫我，附一鍵解法，不必等用戶回報。

做什麼（跑法：python tools/door-sentinel.py）：
  ① 用「App 那樣的匿名連線」戳語音橋 + 管家腦的正門，看回不回得了 200
     （403 = 大門被鎖、App 進不來；其他非 200 = 掛了）
  ② 任一道門不通 → 發 Slack 警報，附「這是什麼壞了 + 一鍵開門指令」
  ③ 全通 → 只印一行 OK、不洗頻（無事不吵）
  ④ 每道門retry 2 次，避免冷啟動瞬斷誤報
說明：
  - 只戳雲端伺服器兩道門（便宜、本就縮到零）；不頻繁戳「會動的臉」顯卡（那台一戳就醒、燒錢）。
  - Slack 接口網址只從 Google 保險箱現拿現用，不落地。
"""
import subprocess, json, urllib.request, urllib.error, os, datetime, time, ssl

GCLOUD = os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd")
PROJECT = "gen-lang-client-0229303523"
REGION = "asia-east1"

# 要顧的兩道門（名稱 / 正門網址 / Cloud Run 服務名）
DOORS = [
    ("語音橋（聊聊）", "https://munea-voice-staging-491603544409.asia-east1.run.app/", "munea-voice-staging"),
    ("管家腦（家人連線·健康趨勢）", "https://munea-brain-staging-491603544409.asia-east1.run.app/", "munea-brain-staging"),
]

# 雲端臉（Modal·亞洲）：健康門要帶通行碼；每天早上摸一下＝順手暖機，
# 讓當天第一個開聊聊的用戶拿到熱的臉（熱身永遠我們吞、不給用戶吞 · Edward 2026-07-10）
FACE_URL = "https://edwardt0303--munea-nening-avatar-nening-web.modal.run/health"
_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deploy", ".munea-app-key")


def sh(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return ""


def webhook():
    return sh([GCLOUD, "secrets", "versions", "access", "latest",
               "--secret=munea-slack-ops-webhook", f"--project={PROJECT}"])


def probe(url):
    """回傳 HTTP 狀態碼；連不上回 0。重試 2 次濾冷啟動瞬斷。"""
    ctx = ssl.create_default_context()
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                return r.getcode()
        except urllib.error.HTTPError as e:
            return e.code                      # 403/500… 明確狀態、不用重試
        except Exception:
            if attempt == 0:
                time.sleep(3)
                continue
            return 0                           # 兩次都連不上＝當掉
    return 0


def diagnose(code, svc):
    if code == 403:
        return (f"🔒 大門被鎖了（403）——App 匿名連進不來，會退回本機罐頭句。\n"
                f"     一鍵開門：`gcloud run services add-iam-policy-binding {svc} "
                f"--region {REGION} --member=allUsers --role=roles/run.invoker`")
    if code == 0:
        return "💥 完全連不上（可能掛了或網路異常）——先看 Cloud Run 主控台這台服務的狀態與記錄。"
    return f"⚠️ 回了非預期狀態 {code}——進主控台看這台服務的記錄。"


def main():
    today = datetime.datetime.now().strftime("%m/%d %H:%M")
    bad = []
    lines = []
    for name, url, svc in DOORS:
        code = probe(url)
        ok = (code == 200)
        lines.append(f"{'✅' if ok else '🔴'} {name}：{code if code else '連不上'}")
        if not ok:
            bad.append(f"🔴 *{name}* → {diagnose(code, svc)}")

    # 雲端臉：帶通行碼探健康＋順手暖機（睡著要 8-10 秒醒、剛上新版可能要 1-2 分鐘熱身→給足時間、別誤報）
    try:
        _key = open(_KEY_FILE, encoding="utf-8").read().strip()
        _req = urllib.request.Request(FACE_URL + "?key=" + urllib.parse.quote(_key), method="GET")
        with urllib.request.urlopen(_req, timeout=150, context=ssl.create_default_context()) as r:
            _body = r.read(200).decode("utf-8", "ignore")
            _face_ok = (r.getcode() == 200 and '"ok": true' in _body.replace('&quot;', '"').replace('ok":true', 'ok": true'))
    except Exception:
        _face_ok = False
    lines.append(f"{'✅' if _face_ok else '🔴'} 會動的臉（聊聊·亞洲）：{'醒了、暖好' if _face_ok else '叫不醒'}")
    if not _face_ok:
        bad.append("🔴 *會動的臉* → 💥 健康探測失敗——聊聊會只有聲音沒有臉。"
                   "看 Modal 主控台 munea-nening-avatar；必要時重新上線：deploy/modal-avatar 下 `modal deploy -m nening_modal`")

    if not bad:
        print(f"門口哨兵 {today}：三道門都通 ✅  " + " / ".join(lines))
        return 0

    text = (
        f"🚨 *門口哨兵警報*（{today}）\n"
        f"雲端的門有問題、App 現在可能連不上：\n"
        + "\n".join(lines) + "\n\n"
        + "\n".join(bad) + "\n\n"
        f"（正常時這隻不吵；會叫＝真的要處理。修好後 App 那包不用重打包、開門即通）"
    )
    url = webhook()
    if not url.startswith("http"):
        print("拿不到 Slack 接口網址、這次改用印的：\n" + text)
        return 1
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
        print("門口哨兵警報已發 #munea-營運")
    except Exception as e:
        print(f"警報發送失敗（{e}）、內容：\n{text}")
        return 1
    return 2   # 2 = 有門壞了（給排程系統/人看的非零碼）


if __name__ == "__main__":
    raise SystemExit(main())
