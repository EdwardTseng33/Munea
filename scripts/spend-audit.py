#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每天問一次「錢正在花在哪」——問帳單，不是問「有沒有在跑」。

為什麼要有這支（2026-08-10 Edward 追究後建立）：
  8/7 Edward 說「備用會暫停，為什麼會一直消耗」。我照他那句話去修「不要亂開卡」，
  修完回報「修好了」。但真正在燒錢的是**刪掉機器之後留下來的硬碟**——那部分我
  完全沒碰到，也沒去看過帳。錢繼續漏，漏到餘額歸零、RunPod 把機器全刪。
  8/10 我打開帳號查那一下花不到 30 秒：0 台機器、4 顆硬碟共 440GB 還在計費，
  其中 3 顆沒有任何機器在用。

所以這支的規格只有兩條，其餘都是細節：

  1. **列「正在被收錢的每一項」，不是列「正在跑的東西」。**
     停掉的機器、沒人用的硬碟、沒人打也常駐的服務——這些都不會出現在「在跑嗎」
     的答案裡，但每一項都在帳單上。

  2. **查不到就大聲說查不到，絕不當成 0。**
     2026-08-06 踩過：GLOWS 認證失敗回的是 HTTP 200 加一個錯誤碼，程式把它讀成
     「一張卡都沒有」——「通行碼壞了」跟「真的沒有卡」長得一模一樣（PR #532）。
     這支寧可整份報告標紅「這一區查不到」，也不會安靜地少報一項。

跑法：
    python scripts/spend-audit.py              # 印報告
    python scripts/spend-audit.py --json       # 給程式吃
    python scripts/spend-audit.py --slack      # 順便貼到頻道

離開碼：0＝沒有可疑支出；1＝有錢在燒但沒人用；2＝有帳查不到（比 1 更嚴重，
因為「查不到」意味著這份報告本身不可信）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# RunPod 的硬碟費率。來源＝2026-08-10 Edward 的開卡畫面截圖：120GB 的資料硬碟
# 標 $0.011/hour → 每 GB 每小時 $0.0000917。不寫死總額、寫單價，容量變了自動跟著算。
RUNPOD_STORAGE_USD_PER_GB_HOUR = 0.011 / 120
HOURS_PER_MONTH = 24 * 30
USD_TO_TWD = 32  # 概數，只為了讓 Edward 一眼有感；精確金額以帳單為準

# 離開碼。「查不到」故意排在「有浪費」後面（數字更大）：報告不完整比報告難看更嚴重，
# 因為不完整的報告會讓人以為已經在管了。
EXIT_OK = 0
EXIT_WASTE = 1
EXIT_UNAVAILABLE = 2


def _classify_volumes_idle(pods):
    """一台機器都沒有時，硬碟必定沒人在用。

    RunPod 的機器物件不會直接回它掛了哪顆硬碟，所以只能做這個確定的判斷；
    有機器在的時候一律保守地不標成閒置，寧可少報也不要冤枉正在用的東西。
    """
    return not pods


class SourceUnavailable(Exception):
    """這個帳查不到。**不可以**被上層吞掉當成「沒有東西」。"""


# ---------------------------------------------------------------------------
# 各家帳
# ---------------------------------------------------------------------------

def _from_secret_manager(secret_name):
    """從 Google 的保險箱拿鑰匙。自動跑的東西不能靠本機檔案——本機檔案不在版控裡，
    換一台機器、換一份工作副本就消失（2026-08-10 第一次跑就踩到）。"""
    try:
        out = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest", "--secret=" + secret_name],
            capture_output=True, text=True, timeout=90, shell=(os.name == "nt"),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (out.stdout or "").strip() if out.returncode == 0 else ""


def _find_keys(env_var, secret_name, env_files):
    """收集所有可能的鑰匙，全部回傳讓呼叫端一把一把試。

    為什麼不「找到第一把就用」：2026-08-10 第一次跑就踩到——保險箱裡那把 RunPod
    鑰匙是舊的（403），本機那把才是活的。只取第一把的話，整份報告會因為一把過期
    的鑰匙變成「查不到」，而其實我們手上有能用的。
    """
    out, seen = [], set()

    def add(value, where):
        value = (value or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append((value, where))

    add(os.environ.get(env_var, ""), "環境變數")
    if secret_name:
        add(_from_secret_manager(secret_name), "保險箱 " + secret_name)
    for path in env_files:
        try:
            # utf-8-sig：Windows 上編輯過的設定檔開頭常有一個看不見的記號（BOM），
            # 用一般 utf-8 讀會變成 "﻿RUNPOD_API_KEY"，名稱對不上、鑰匙就這樣被
            # 漏掉（2026-08-10 第一次跑踩到，症狀是「明明有鑰匙卻說找不到」）。
            with open(path, encoding="utf-8-sig") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[len("export "):]
                    if line.startswith(env_var + "="):
                        add(line.split("=", 1)[1].strip().strip('"').strip("'"), path)
        except OSError:
            continue
    return out


def _env_candidates(*parts):
    """同一份設定可能在這份工作副本、也可能在主資料夾——兩邊都找。"""
    seen, out = set(), []
    for root in (REPO, os.environ.get("MUNEA_REPO_ROOT", ""), r"E:\Claude\Munea"):
        if not root or root in seen:
            continue
        seen.add(root)
        out.append(os.path.join(root, *parts))
    return out


def _runpod_keys():
    keys = _find_keys("RUNPOD_API_KEY", "munea-runpod-api-key",
                      _env_candidates("deploy", "runpod-avatar", ".env"))
    if not keys:
        raise SourceUnavailable(
            "找不到 RunPod 的鑰匙（環境變數 RUNPOD_API_KEY、保險箱 munea-runpod-api-key、本機檔都沒有）")
    return keys


def audit_runpod():
    """RunPod：機器、硬碟、餘額。硬碟才是「沒人用也一直收錢」的大宗。"""
    query = ("query { myself { clientBalance "
             "pods { id name desiredStatus costPerHr volumeInGb containerDiskInGb } "
             "networkVolumes { id name size dataCenterId } } }")
    me, tried = None, []
    for key, where in _runpod_keys():
        req = urllib.request.Request(
            "https://api.runpod.io/graphql?api_key=" + key,
            data=json.dumps({"query": query}).encode("utf-8"),
            # 一定要帶 User-Agent：RunPod 會用 403 擋掉沒有身分標示的程式，
            # 而那個 403 跟「鑰匙壞了」長得一模一樣（2026-08-10 查了兩輪才分出來）。
            headers={"Content-Type": "application/json",
                     "User-Agent": "munea-spend-audit/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                body = json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            tried.append("%s → %s" % (where, str(e)[:60]))
            continue
        if body.get("errors"):
            tried.append("%s → %s" % (where, str(body["errors"])[:60]))
            continue
        me = (body.get("data") or {}).get("myself")
        if me is None:
            tried.append("%s → 回的資料裡沒有帳號區塊" % where)
            continue
        break
    if me is None:
        raise SourceUnavailable("RunPod 每一把鑰匙都問不到：" + "；".join(tried))

    pods = me.get("pods") or []
    volumes = me.get("networkVolumes") or []
    # 哪些硬碟真的有機器掛著？RunPod 的機器物件不直接回 volume id，
    # 所以這裡只能用「完全沒有機器」這個確定判斷；有機器時保守地不標成閒置。
    items = []
    for p in pods:
        stopped = (p.get("desiredStatus") or "").upper() != "RUNNING"
        items.append({
            "kind": "機器",
            "name": p.get("name") or p.get("id"),
            "detail": "停著（硬碟仍計費）" if stopped else "執行中",
            "usd_per_month": round(float(p.get("costPerHr") or 0) * HOURS_PER_MONTH, 2),
            "wasteful": stopped,
        })
    for v in volumes:
        size = int(v.get("size") or 0)
        usd = round(size * RUNPOD_STORAGE_USD_PER_GB_HOUR * HOURS_PER_MONTH, 2)
        items.append({
            "kind": "硬碟",
            "name": "%s（%s）" % (v.get("name") or v.get("id"), v.get("id")),
            "detail": "%d GB · %s" % (size, v.get("dataCenterId") or "?"),
            "usd_per_month": usd,
            # 一台機器都沒有 → 這些硬碟必定沒人在用。這就是 8/10 漏掉的那一類。
            "wasteful": _classify_volumes_idle(pods),
        })
    return {
        "source": "RunPod",
        "balance_usd": round(float(me.get("clientBalance") or 0), 2),
        "items": items,
        "note": ("帳上一台機器都沒有——所有硬碟都是空櫃子" if volumes and not pods else ""),
    }


def audit_glows():
    """GLOWS：正式線那張常駐顯卡就在這裡，開著就是整天在收錢。"""
    tokens = _find_keys("GLOWS_SDK_TOKEN", "munea-glows-sdk-token",
                        _env_candidates("deploy", "glows", ".env"))
    if not tokens:
        raise SourceUnavailable(
            "找不到 GLOWS 的通行碼（環境變數 GLOWS_SDK_TOKEN、保險箱 munea-glows-sdk-token、本機檔都沒有）")
    body, tried = None, []
    for token, where in tokens:
        req = urllib.request.Request(
            "https://a.glows.ai/sdk/v1/instance/list?page=1&per_page=50",
            headers={"Authorization": "Bearer " + token},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                got = json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            tried.append("%s → %s" % (where, str(e)[:60]))
            continue
        # 2026-08-06 的坑：認證失敗是 HTTP 200 + code=176，不是 401。
        # 這裡一定要當成「查不到」，不可以讓它變成一份「0 張卡」的乾淨報告。
        if isinstance(got.get("code"), int) and got["code"] != 0:
            tried.append("%s → code=%s %s" % (where, got.get("code"), got.get("msg")))
            continue
        body = got
        break
    if body is None:
        raise SourceUnavailable(
            "GLOWS 每一把通行碼都問不到（通行碼過期不等於沒有卡）：" + "；".join(tried))
    rows = body.get("instances") or body.get("data") or []
    items = []
    for it in rows:
        items.append({
            "kind": "顯示卡",
            "name": it.get("name") or it.get("id") or "?",
            "detail": "%s · %s" % (it.get("status") or "?", it.get("region") or "?"),
            "usd_per_month": None,   # GLOWS 用點數計價，不換算成美金免得誤導
            "wasteful": False,       # 常駐卡是刻意開著的，不當成浪費
        })
    return {"source": "GLOWS", "balance_usd": None, "items": items, "note": ""}


def audit_cloud_run():
    """Google：沒人打也維持常駐的服務——那是每天 24 小時的固定支出。"""
    services = ["munea-brain", "munea-voice", "munea-call-control",
                "munea-runpod-controller", "munea-gateway-monitor",
                "munea-brain-staging", "munea-voice-staging"]
    gcloud = "gcloud"
    items, failed = [], []
    for svc in services:
        try:
            out = subprocess.run(
                [gcloud, "run", "services", "describe", svc, "--region=asia-east1",
                 "--format=value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])"],
                capture_output=True, text=True, timeout=90, shell=(os.name == "nt"),
            )
        except (OSError, subprocess.SubprocessError) as e:
            failed.append("%s（%s）" % (svc, str(e)[:60]))
            continue
        if out.returncode != 0:
            # 服務不存在跟查不到要分開；查不到就記下來，不要安靜跳過。
            if "NOT_FOUND" in (out.stderr or "") or "not found" in (out.stderr or "").lower():
                continue
            failed.append("%s（%s）" % (svc, (out.stderr or "").strip()[:60]))
            continue
        raw = (out.stdout or "").strip()
        min_scale = int(raw) if raw.isdigit() else 0
        if min_scale > 0:
            items.append({
                "kind": "常駐服務",
                "name": svc,
                "detail": "沒人用也維持 %d 台" % min_scale,
                "usd_per_month": None,
                "wasteful": False,   # 這是刻意設的（怕冷啟動），列出來讓人知道有這筆
            })
    if failed:
        raise SourceUnavailable("Google 這幾項查不到：" + "、".join(failed))
    return {"source": "Google Cloud", "balance_usd": None, "items": items, "note": ""}


# ---------------------------------------------------------------------------
# 報告
# ---------------------------------------------------------------------------

def collect():
    reports, unavailable = [], []
    for fn in (audit_runpod, audit_glows, audit_cloud_run):
        try:
            reports.append(fn())
        except SourceUnavailable as e:
            unavailable.append(str(e))
    return reports, unavailable


def render(reports, unavailable):
    lines = []
    waste_usd = 0.0
    waste_rows = []
    for rep in reports:
        head = rep["source"]
        if rep.get("balance_usd") is not None:
            head += "（餘額 $%.2f）" % rep["balance_usd"]
        lines.append("【%s】" % head)
        if not rep["items"]:
            lines.append("  帳上沒有任何計費項目")
        for it in rep["items"]:
            money = "" if it["usd_per_month"] is None else "　約 $%.2f/月" % it["usd_per_month"]
            mark = "🔴 沒人用" if it["wasteful"] else "　"
            lines.append("  %s %s｜%s｜%s%s" % (mark, it["kind"], it["name"], it["detail"], money))
            if it["wasteful"]:
                waste_usd += it["usd_per_month"] or 0.0
                waste_rows.append(it)
        if rep.get("note"):
            lines.append("  ↳ %s" % rep["note"])
        lines.append("")

    if unavailable:
        lines.append("⚠️ 這幾個帳今天查不到——**這份報告不完整，不要當成沒事**：")
        for u in unavailable:
            lines.append("  · %s" % u)
        lines.append("")

    if waste_rows:
        lines.append("🔴 有 %d 項在收錢但沒人用，約 **$%.2f 美金/月（NT$%d）**"
                     % (len(waste_rows), waste_usd, round(waste_usd * USD_TO_TWD)))
    elif not unavailable:
        lines.append("✅ 沒有查到「在收錢但沒人用」的項目")
    return "\n".join(lines), waste_usd, waste_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="輸出機器可讀格式")
    ap.add_argument("--slack", action="store_true", help="順便貼到 Slack")
    args = ap.parse_args()

    reports, unavailable = collect()
    text, waste_usd, waste_rows = render(reports, unavailable)

    if args.json:
        print(json.dumps({"reports": reports, "unavailable": unavailable,
                          "waste_usd_per_month": round(waste_usd, 2)},
                         ensure_ascii=False, indent=2))
    else:
        print("═══ 錢花在哪 · %s ═══\n" % os.environ.get("SPEND_AUDIT_DATE", "今天"))
        print(text)

    if args.slack:
        post = os.path.expanduser("~/.claude/scripts/sophie-post.py")
        if os.path.exists(post):
            subprocess.run([sys.executable, post, "--channel", "C0BG7PEMR7E",
                            "--text", "☁️ 每日錢花在哪\n```\n%s\n```" % text],
                           timeout=90)
        else:
            print("（找不到 Slack 發文工具，只印在這裡）", file=sys.stderr)

    # 查不到比「有浪費」更嚴重：報告本身不可信。
    if unavailable:
        return EXIT_UNAVAILABLE
    return EXIT_WASTE if waste_rows else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
