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

def alert(kind, where, detail=""):
    """功能告警：kind=chat|voice|data|billing|engine；where=哪個口；detail=去識別的錯誤摘要"""
    now = time.time()
    if now - _last_alert.get(kind + where, 0) < 600:   # 同類 10 分鐘一次
        return
    _last_alert[kind + where] = now
    _post(_ALERT, f"🔴 [{_ENV}] 功能告警 · {kind} · {where}\n{(detail or '')[:300]}")
