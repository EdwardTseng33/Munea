# -*- coding: utf-8 -*-
"""沐寧 · 營運通知與功能告警（Slack）

兩條線、兩個頻道（各自一個接訊息接口網址、放環境變數，沒設＝安靜不動）：
  MUNEA_SLACK_OPS_WEBHOOK    → #沐寧-營運（會員註冊、訂閱購買、點數購買…好消息線）
  MUNEA_SLACK_ALERT_WEBHOOK  → #沐寧-告警（哪裡壞了：聊聊/狀態/資料/付款，附錯誤摘要…壞消息線）

設計原則：
  - 絕不影響主流程：送不出去就默默記一行日誌，功能照常
  - 絕不外洩內容：只送「事件種類＋去識別摘要」，不送對話內容、不送個資
  - 告警防洪：同一種告警 10 分鐘內只送一次（防雪崩洗版）
"""
import os, json, time, threading, urllib.request

_OPS = os.environ.get("MUNEA_SLACK_OPS_WEBHOOK") or ""
_ALERT = os.environ.get("MUNEA_SLACK_ALERT_WEBHOOK") or ""
_ENV = os.environ.get("MUNEA_ENV_NAME") or ("cloud" if os.environ.get("K_SERVICE") else "local")
_last_alert = {}  # kind -> ts（防洪）

def _post(url, text):
    if not url:
        return
    def _send():
        try:
            req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=6).read()
        except Exception as e:
            print(f"[notify] 送 Slack 失敗（不影響功能）: {e}", flush=True)
    threading.Thread(target=_send, daemon=True).start()  # 背景送、不擋回應

def ops(event_name, summary=""):
    """營運好消息：會員註冊/訂閱/點數…（event_name 用埋點事件名）"""
    icon = {"subscription_purchased": "💎", "points_purchased": "🪙",
            "onboarding_completed": "🌱", "auth_sign_in_started": "👋",
            "health_connected": "❤️"}.get(event_name, "📈")
    _post(_OPS, f"{icon} [{_ENV}] {event_name}" + (f" · {summary}" if summary else ""))

# 2026-07-29：告警原本只有一級——半夜「有人打不進來」跟「某一筆資料沒寫進雲端」
# 在頻道裡長得一模一樣，結果就是兩種都不會叫醒人。分兩級：
#   critical＝使用者現在打不通／叫不到人／付不了錢（人在等、會出事）→ @channel 穿透手機免打擾
#   warning ＝有東西壞了但服務還活著（單筆寫入失敗、單台機器異常）→ 安靜進頻道、早上看
# 只有真的會咬人的才 @channel；狼來了幾次以後就沒人理了，那比不發還糟。
CRITICAL_KINDS = ("call_down", "gpu_down", "auth_down", "billing_down")
_CRITICAL_THROTTLE_S = 300     # critical 節流短一點（5 分鐘），壞消息要跟得上現場
_WARNING_THROTTLE_S = 600


def alert(kind, where, detail="", critical=None):
    """功能告警：kind=chat|voice|data|billing|engine|call_down|gpu_down…；
    where=哪個口；detail=去識別的錯誤摘要；critical 不指定時照 CRITICAL_KINDS 自動判。"""
    is_critical = (kind in CRITICAL_KINDS) if critical is None else bool(critical)
    now = time.time()
    window = _CRITICAL_THROTTLE_S if is_critical else _WARNING_THROTTLE_S
    if now - _last_alert.get(kind + where, 0) < window:
        return
    _last_alert[kind + where] = now
    if is_critical:
        _post(_ALERT, f"<!channel> 🚨 [{_ENV}] 服務中斷 · {kind} · {where}\n"
                      f"{(detail or '')[:300]}\n（使用者現在受影響，需要立刻看）")
    else:
        _post(_ALERT, f"🔴 [{_ENV}] 功能告警 · {kind} · {where}\n{(detail or '')[:300]}")
