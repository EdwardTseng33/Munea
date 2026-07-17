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
import base64
import hashlib
import hmac
import os
import time

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from call_control_store import CallControlError, SupabaseCallStore, issue_call_token
from gateway_core import Gateway, VoicePool

app = FastAPI(title="munea-chat-gateway")
_CORS_ORIGINS = [x.strip() for x in os.environ.get(
    "MUNEA_GATEWAY_CORS_ORIGINS",
    "capacitor://localhost,ionic://localhost,http://localhost,https://localhost",
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Munea-Admin-Token"],
)

# 語音池上限：首波先用保守值頂著，等 6.3 節純語音壓測結果回填真數字
# （環境變數可覆蓋，不必改程式碼重部署）。
_VOICE_LIMIT = int(os.environ.get("MUNEA_GATEWAY_VOICE_LIMIT", "5"))
_QUEUE_MAX_DEPTH = int(os.environ.get("MUNEA_GATEWAY_QUEUE_MAX_DEPTH", "30"))
GW = Gateway(voice=VoicePool(limit=_VOICE_LIMIT))
GW.queue.max_depth = _QUEUE_MAX_DEPTH

_PRIMARY_URL = os.environ.get("MUNEA_PRIMARY_AVATAR_URL", "").rstrip("/")
if _PRIMARY_URL:
    GW.workers.register(
        os.environ.get("MUNEA_PRIMARY_WORKER_ID", "glows-primary"),
        _PRIMARY_URL,
        slots=int(os.environ.get("MUNEA_PRIMARY_AVATAR_SLOTS", "2")),
        region=os.environ.get("MUNEA_PRIMARY_AVATAR_REGION", "TW"),
        kind="glows",
    )

_GATE = os.environ.get("MUNEA_GATEWAY_KEY", "").strip()
_ADMIN_GATE = os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", "").strip()
_CALL_TOKEN_SECRET = os.environ.get("MUNEA_CALL_TOKEN_SECRET", "").strip()
_TURN_SECRET = os.environ.get("MUNEA_TURN_SECRET", "").strip()
_TURN_URLS = [x.strip() for x in os.environ.get("MUNEA_TURN_URLS", "").split(",") if x.strip()]
_REQUIRE_DURABLE = os.environ.get("MUNEA_GATEWAY_REQUIRE_DURABLE", "0") == "1"
DURABLE = SupabaseCallStore.from_env()


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


class CallRequestV2Body(BaseModel):
    character_id: str
    idempotency_key: str
    person_id: str | None = None


class CallLeaseV2Body(BaseModel):
    lease_version: int
    event_id: str
    reason: str = "completed"


class CallClaimV2Body(BaseModel):
    lease_version: int


class CallHeartbeatV2Body(BaseModel):
    lease_version: int
    event_id: str
    component: str = "app"


class CallReadyV2Body(BaseModel):
    call_id: str
    lease_version: int
    event_id: str
    component: str


class DurableWorkerBody(BaseModel):
    worker_id: str
    url: str
    provider: str
    region: str
    capacity: int
    status: str = "ready"
    provider_instance_id: str | None = None
    profile_id: str | None = None
    hourly_cost: float | None = None
    active_leases: int | None = None


class DurableWorkerHealthBody(BaseModel):
    healthy: bool = True
    active: int | None = None


class DurableWorkerStateBody(BaseModel):
    status: str


class DurableVoiceShardBody(BaseModel):
    shard_id: str
    url: str
    provider: str = "gemini-live"
    region: str = "asia-east1"
    capacity: int
    status: str = "ready"


def _bearer(authorization: str) -> str:
    prefix = "bearer "
    if not authorization or not authorization.lower().startswith(prefix):
        raise HTTPException(status_code=401, detail="bearer token required")
    token = authorization[len(prefix):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="bearer token required")
    return token


def _optional_bearer(authorization: str) -> str:
    prefix = "bearer "
    if not authorization or not authorization.lower().startswith(prefix):
        return ""
    return authorization[len(prefix):].strip()


def _durable() -> SupabaseCallStore:
    if DURABLE is None:
        raise HTTPException(status_code=503, detail="durable call control is not configured")
    return DURABLE


def _admin_bearer(authorization: str, x_munea_admin_token: str) -> None:
    supplied = ""
    if authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    supplied = supplied or x_munea_admin_token.strip()
    if not _ADMIN_GATE or supplied != _ADMIN_GATE:
        raise HTTPException(status_code=403, detail="admin token required")


def _decorate_connect(result: dict, user_id: str) -> dict:
    if result.get("status") != "connect":
        return result
    worker = result.get("worker") or {}
    if not _CALL_TOKEN_SECRET:
        raise HTTPException(status_code=503, detail="call token signer is not configured")
    token_payload = {
        "call_id": str(result.get("call_id") or ""),
        "user_id": user_id,
        "worker_id": str(worker.get("worker_id") or ""),
        "voice_shard_id": str((result.get("voice") or {}).get("shard_id") or ""),
        "slot_id": int(result.get("slot_id") or 0),
        "lease_version": int(result.get("lease_version") or 0),
    }
    if _TURN_SECRET and _TURN_URLS:
        turn_username = str(int(time.time()) + 120) + ":" + user_id
        turn_credential = base64.b64encode(
            hmac.new(_TURN_SECRET.encode("utf-8"), turn_username.encode("utf-8"), hashlib.sha1).digest()
        ).decode("ascii")
        token_payload.update({
            "turn_urls": _TURN_URLS,
            "turn_username": turn_username,
            "turn_credential": turn_credential,
        })
        result["ice_servers"] = [{
            "urls": _TURN_URLS, "username": turn_username, "credential": turn_credential,
        }]
    result["call_token"] = issue_call_token(token_payload, _CALL_TOKEN_SECRET, ttl_seconds=90)
    result["token_expires_in"] = 90
    return result


@app.get("/health")
def health(key: str = "", authorization: str = Header(default="")):
    supplied_bearer = _optional_bearer(authorization)
    admin_ok = bool(_ADMIN_GATE) and bool(supplied_bearer) and hmac.compare_digest(
        supplied_bearer, _ADMIN_GATE
    )
    user_ok = False
    if supplied_bearer and not admin_ok and DURABLE is not None:
        try:
            DURABLE.authenticate(supplied_bearer)
            user_ok = True
        except CallControlError:
            pass
    if not (_client_ok(key) or admin_ok or user_ok):
        raise HTTPException(status_code=401, detail="valid bearer token or client key required")
    durable_snapshot = None
    durable_error = ""
    if DURABLE is not None:
        try:
            durable_snapshot = DURABLE.snapshot()
        except CallControlError as exc:
            durable_error = str(exc)
    durable_ready = DURABLE is not None and durable_snapshot is not None
    client_gate_ok = bool(key) and _client_ok(key)
    if user_ok and not admin_ok and not client_gate_ok:
        # A normal user's JWT is enough to prove the durable Gateway is ready
        # for their call, but it must never expose fleet topology or capacity.
        return {
            "ok": durable_ready,
            "durable_ready": durable_ready,
        }
    return {
        "ok": durable_ready if _REQUIRE_DURABLE else True,
        "engine": "munea-chat-gateway",
        "mode": "durable" if DURABLE is not None else "legacy-memory",
        "durable_ready": durable_ready,
        "durable_error": durable_error,
        "snapshot": durable_snapshot if durable_snapshot is not None else GW.snapshot(),
    }


@app.get("/metrics", response_class=Response)
def metrics(authorization: str = Header(default=""),
            x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    try:
        snapshot = _durable().snapshot()
    except Exception:
        snapshot = GW.snapshot()
    values = {
        "munea_calls_active": snapshot.get("active_calls", 0),
        "munea_calls_connecting": snapshot.get("connecting_calls", 0),
        "munea_call_queue_depth": snapshot.get("queue_depth", 0),
        "munea_avatar_capacity": snapshot.get("avatar_capacity", 0),
        "munea_avatar_active": snapshot.get("avatar_active", 0),
        "munea_voice_capacity": snapshot.get("voice_capacity", 0),
        "munea_voice_active": snapshot.get("voice_active", 0),
    }
    body = "\n".join(f"{name} {float(value or 0):g}" for name, value in values.items()) + "\n"
    return Response(body, media_type="text/plain; version=0.0.4")


# ---------------------------------------------------------------------------
# Durable v2 Call Control. Client authentication is the user's Supabase JWT;
# provider/admin credentials never ship inside the App.
# ---------------------------------------------------------------------------
@app.post("/v1/calls")
def calls_v2(body: CallRequestV2Body, authorization: str = Header(default="")):
    store = _durable()
    try:
        user = store.authenticate(_bearer(authorization))
        result = store.request_call(
            user_id=user.user_id,
            person_id=body.person_id,
            character_id=body.character_id,
            idempotency_key=body.idempotency_key,
            queue_max=_QUEUE_MAX_DEPTH,
        )
        return _decorate_connect(result, user.user_id)
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/calls/{call_id}/heartbeat")
def call_heartbeat_v2(call_id: str, body: CallHeartbeatV2Body,
                      authorization: str = Header(default="")):
    store = _durable()
    try:
        user = store.authenticate(_bearer(authorization))
        return store.heartbeat(
            call_id=call_id, lease_version=body.lease_version, component="app",
            event_id=body.event_id, user_id=user.user_id,
        )
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/calls/{call_id}/release")
def call_release_v2(call_id: str, body: CallLeaseV2Body,
                    authorization: str = Header(default="")):
    store = _durable()
    try:
        user = store.authenticate(_bearer(authorization))
        return store.release(
            call_id=call_id, lease_version=body.lease_version,
            event_id=body.event_id, reason=body.reason, user_id=user.user_id,
        )
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/calls/{call_id}/cancel")
def call_cancel_v2(call_id: str, authorization: str = Header(default="")):
    store = _durable()
    try:
        user = store.authenticate(_bearer(authorization))
        return store.cancel(call_id=call_id, user_id=user.user_id)
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/calls/{call_id}/token")
def call_token_v2(call_id: str, body: CallClaimV2Body,
                  authorization: str = Header(default="")):
    store = _durable()
    try:
        user = store.authenticate(_bearer(authorization))
        result = store.claim(
            call_id=call_id, lease_version=body.lease_version, user_id=user.user_id,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail=str(result.get("reason") or "stale lease"))
        return _decorate_connect(result, user.user_id)
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/internal/calls/ready")
def call_ready_v2(body: CallReadyV2Body, authorization: str = Header(default=""),
                  x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    try:
        return _durable().ready(
            call_id=body.call_id, lease_version=body.lease_version,
            component=body.component, event_id=body.event_id,
        )
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/internal/calls/{call_id}/release")
def call_internal_release_v2(call_id: str, body: CallLeaseV2Body,
                             authorization: str = Header(default=""),
                             x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    try:
        return _durable().release(
            call_id=call_id, lease_version=body.lease_version,
            event_id=body.event_id, reason=body.reason, user_id=None,
        )
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/internal/reap")
def call_reap_v2(authorization: str = Header(default=""),
                 x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    try:
        return {"ok": True, "reaped": _durable().reap()}
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/internal/workers")
def durable_worker_upsert(body: DurableWorkerBody, authorization: str = Header(default=""),
                          x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    row = body.dict(exclude_none=True)
    row["last_heartbeat_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if row.get("status") == "ready":
        row["ready_at"] = row["last_heartbeat_at"]
    try:
        return {"ok": True, "worker": _durable().upsert_worker(row)}
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/internal/workers/{worker_id}/health")
def durable_worker_health(worker_id: str, body: DurableWorkerHealthBody,
                          authorization: str = Header(default=""),
                          x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    values = {
        "status": "ready" if body.healthy else "unhealthy",
        "last_heartbeat_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # active_leases is the durable admission ledger. A worker heartbeat reports
    # physical media sessions, which can legitimately lag reservations while a
    # call is connecting. Never let telemetry erase reserved capacity.
    try:
        return {"ok": True, "worker": _durable().update_worker(worker_id, values)}
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/internal/workers/{worker_id}/state")
def durable_worker_state(worker_id: str, body: DurableWorkerStateBody,
                         authorization: str = Header(default=""),
                         x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    if body.status not in ("ready", "draining", "unhealthy", "terminated"):
        raise HTTPException(status_code=422, detail="invalid worker status")
    try:
        return {"ok": True, "worker": _durable().update_worker(worker_id, {
            "status": body.status,
            "last_heartbeat_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })}
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/internal/voice-shards")
def durable_voice_upsert(body: DurableVoiceShardBody, authorization: str = Header(default=""),
                         x_munea_admin_token: str = Header(default="")):
    _admin_bearer(authorization, x_munea_admin_token)
    row = body.dict(exclude_none=True)
    row["last_heartbeat_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        return {"ok": True, "voice_shard": _durable().upsert_voice_shard(row)}
    except CallControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
