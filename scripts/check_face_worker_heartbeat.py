#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""常駐臉卡心跳點名（2026-08-18 · 8/14 餘額燒完卡被收走、三天沒人發現後補）。

管家（munea-runpod-controller）只看 RunPod 爆發卡；GLOWS 常駐卡誰都沒看。
這支對總機資料庫 gpu_workers 點名：常駐臉卡心跳斷超過門檻＝喊人。
不自帶排程（Edward 拍板「定時任務全刪、不自動重建」）——手動跑、或
Edward 點頭後由任何排程器呼叫；exit code 就是判定（0 活著／2 斷線／3 查不到）。

跑法：
  SUPABASE_SERVICE_ROLE_KEY=... python scripts/check_face_worker_heartbeat.py
  （鑰匙也可自動從 gcloud secret munea-supabase-service-staging 取——
    名字帶 staging、值是正式鑰匙，見 memory 8/13）

判定門檻 --stale-seconds 預設 600（臉機每 20-30 秒跳一次、10 分鐘斷＝真出事）。
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fespbkdwafueyonppzwq.supabase.co")
WORKER_ID = os.environ.get("MUNEA_FACE_WORKER_ID", "glows-tw06-resident")


def service_key():
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if key:
        return key
    # Windows 下 gcloud 是 .cmd；shell=False 直呼會 WinError 2
    cmd = ["cmd", "/c", "gcloud.cmd"] if os.name == "nt" else ["gcloud"]
    out = subprocess.run(
        cmd + ["secrets", "versions", "access", "latest",
               "--secret", "munea-supabase-service-staging"],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SystemExit("拿不到鑰匙：環境變數沒給、gcloud 也失敗\n" + out.stderr[-300:])
    return out.stdout.strip()


def fetch_worker(key):
    url = (SUPABASE_URL + "/rest/v1/gpu_workers"
           + "?select=worker_id,status,last_heartbeat_at"
           + "&worker_id=eq." + urllib.parse.quote(WORKER_ID))
    req = urllib.request.Request(url, headers={"apikey": key})
    # 舊式 JWT（eyJ 開頭）要 Bearer；新式 sb_secret_ 只帶 apikey
    if not key.startswith("sb_secret_"):
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-seconds", type=int, default=600)
    args = ap.parse_args()

    rows = fetch_worker(service_key())
    if not rows:
        print("🔴 總機名單裡查不到 " + WORKER_ID + "＝掛號掉了（跟斷線同級）")
        return 3
    row = rows[0]
    hb = row.get("last_heartbeat_at")
    if not hb:
        print("🔴 " + WORKER_ID + " 從未有心跳記錄")
        return 3
    t = datetime.datetime.fromisoformat(hb.replace("Z", "+00:00"))
    age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    status = row.get("status")
    if age > args.stale_seconds:
        print("🔴 常駐臉卡心跳斷了 " + str(round(age / 60, 1)) + " 分鐘"
              + "（狀態欄還寫著 " + str(status) + "——欄位會說謊、心跳不會）。"
              + "先查 GLOWS 餘額、再照重生 SOP（看板 8/17 條目）。")
        return 2
    print("🟢 " + WORKER_ID + " 活著：心跳 " + str(round(age)) + " 秒前、狀態 "
          + str(status) + "（門檻 " + str(args.stale_seconds) + " 秒）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
