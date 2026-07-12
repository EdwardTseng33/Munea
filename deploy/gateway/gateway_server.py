# -*- coding: utf-8 -*-
"""Munea「聊聊」分流閘道 · HTTP 外殼（2026-07-12 卡西法）

薄薄一層 FastAPI，把 gateway_core.Gateway 的方法接成 HTTP 端點——邏輯本身不在這裡
（見 gateway_core.py，零依賴、有完整單元測試），這支只管路由/序列化/管理端門禁。

跑法（CPU-only，不需要 GPU、不需要 torch/aiortc；跟 flashhead_server.py 完全分開部署）：
  pip install fastapi "uvicorn[standard]"
  MUNEA_GATEWAY_KEY=<通行碼> python3 gateway_server.py     # 門牌 8199

Client 端串接規格：deploy/gateway/CLIENT-INTERFACE.md（給 Codex 接 app.js 用）。

**自動開關卡 API 串接目前是 stub**（register_worker / worker health 輪詢都要手動或靠
外部腳本呼叫這裡的登記端點）——要真的自動開關 RunPod/Glows 卡，需要真卡環境才能接線
測試，這輪不碰（照任務邊界：不開真卡、不花 GPU 錢）。
"""
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gateway_core import Gateway, VoicePool

app = FastAPI(title="munea-chat-gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 語音池上限：首波先用保守值頂著，等 6.3 節純語音壓測結果回填真數字
# （環境變數可覆蓋，不必改程式碼重部署）。
_VOICE_LIMIT = int(os.environ.get("MUNEA_GATEWAY_VOICE_LIMIT", "5"))
_QUEUE_MAX_DEPTH = int(os.environ.get("MUNEA_GATEWAY_QUEUE_MAX_DEPTH", "20"))
GW = Gateway(voice=VoicePool(limit=_VOICE_LIMIT))
GW.queue.max_depth = _QUEUE_MAX_DEPTH

_GATE = os.environ.get("MUNEA_GATEWAY_KEY", "").strip()
_ADMIN_GATE = os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", "").strip()


def _client_ok(key):
    return (not _GATE) or (key == _GATE)


def _admin_ok(key):
    # 管理端（登記 worker / 設語音池容量）沒設專屬鑰匙時退回共用鑰匙，
    # 兩個都沒設＝本機測試模式全開放。
    guard = _ADMIN_GATE or _GATE
    return (not guard) or (key == guard)


class RegisterWorkerBody(BaseModel):
    worker_id: str
    url: str
    slots: int = 1
    region: str = ""
    kind: str = "manual"


class WorkerHealthBody(BaseModel):
    healthy: bool = True
    active: int = None


class ReleaseCallBody(BaseModel):
    worker_id: str
    duration_s: float = None


class VoiceActiveBody(BaseModel):
    active: int


@app.get("/health")
def health(key: str = ""):
    if not _client_ok(key):
        return {"ok": False, "error": "key required"}
    return {"ok": True, "engine": "munea-chat-gateway", "snapshot": GW.snapshot()}


# ---------------------------------------------------------------------------
# Client 端接口（§5.4 決策樹）——app.js 之後照 CLIENT-INTERFACE.md 接這三支。
# ---------------------------------------------------------------------------
@app.post("/v1/call/request")
def call_request(client_id: str, key: str = ""):
    if not _client_ok(key):
        return {"error": "key required"}
    if not client_id:
        return {"error": "client_id required"}
    return GW.request_call(client_id)


@app.get("/v1/call/poll")
def call_poll(client_id: str, key: str = ""):
    if not _client_ok(key):
        return {"error": "key required"}
    if not client_id:
        return {"error": "client_id required"}
    return GW.poll(client_id)


@app.post("/v1/call/cancel")
def call_cancel(client_id: str, key: str = ""):
    if not _client_ok(key):
        return {"error": "key required"}
    if not client_id:
        return {"error": "client_id required"}
    return GW.cancel_call(client_id)


# ---------------------------------------------------------------------------
# Worker 端 webhook——flashhead_server.py（或維運腳本）通話結束時打這支釋放槽位。
# ---------------------------------------------------------------------------
@app.post("/v1/call/release")
def call_release(body: ReleaseCallBody, key: str = ""):
    if not _client_ok(key):
        return {"error": "key required"}
    advanced = GW.release_call(body.worker_id, duration_s=body.duration_s)
    return {"ok": True, "advanced": advanced}


# ---------------------------------------------------------------------------
# 管理端——登記/下線 worker、更新語音池占用（自動開關卡 API 串接的 stub 掛勾點；
# 這輪先手動/外部腳本呼叫，真的要自動化需要真卡環境才能接線測試，見檔頭說明）。
# ---------------------------------------------------------------------------
@app.post("/v1/admin/worker/register")
def admin_register_worker(body: RegisterWorkerBody, key: str = ""):
    if not _admin_ok(key):
        return {"error": "admin key required"}
    w = GW.workers.register(body.worker_id, body.url, slots=body.slots,
                             region=body.region, kind=body.kind)
    return {"ok": True, "worker": {"worker_id": w.worker_id, "url": w.url, "slots": w.slots}}


@app.post("/v1/admin/worker/{worker_id}/unregister")
def admin_unregister_worker(worker_id: str, key: str = ""):
    if not _admin_ok(key):
        return {"error": "admin key required"}
    GW.workers.unregister(worker_id)
    return {"ok": True}


@app.post("/v1/admin/worker/{worker_id}/health")
def admin_worker_health(worker_id: str, body: WorkerHealthBody, key: str = ""):
    if not _admin_ok(key):
        return {"error": "admin key required"}
    ok = GW.workers.mark_health(worker_id, healthy=body.healthy, active=body.active)
    if not ok:
        return {"error": "worker not found"}
    return {"ok": True}


@app.post("/v1/admin/worker/{worker_id}/enabled")
def admin_worker_enabled(worker_id: str, enabled: bool, key: str = ""):
    if not _admin_ok(key):
        return {"error": "admin key required"}
    ok = GW.workers.set_enabled(worker_id, enabled)
    if not ok:
        return {"error": "worker not found"}
    return {"ok": True}


@app.post("/v1/admin/voice/active")
def admin_voice_active(body: VoiceActiveBody, key: str = ""):
    if not _admin_ok(key):
        return {"error": "admin key required"}
    GW.voice.set_active(body.active)
    return {"ok": True, "voice_free": GW.voice.free()}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MUNEA_GATEWAY_PORT", "8199"))
    print("[gateway] serving on 0.0.0.0:" + str(port) + " voice_limit=" + str(_VOICE_LIMIT)
          + " queue_max_depth=" + str(_QUEUE_MAX_DEPTH), flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
