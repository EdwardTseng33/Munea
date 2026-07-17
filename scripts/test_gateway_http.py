# -*- coding: utf-8 -*-
"""聊聊分流閘道 · HTTP 層 smoke test（2026-07-12 卡西法）。

用 FastAPI TestClient 直接打 deploy/gateway/gateway_server.py 的真實路由——驗證
「路由接得對不對」（序列化/門禁/端點路徑），跟 scripts/test_gateway.py（測邏輯本身）
互補。需要本機裝 fastapi/httpx（CPU-only 套件，不需要 GPU/torch，pip install 幾秒
就好）——沒裝的環境會直接跳過、印一行提示，不算失敗（避免擋住沒裝這兩個套件的
CI/開發機器）。

跑法：python scripts/test_gateway_http.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "deploy" / "gateway"


def main():
    if importlib.util.find_spec("fastapi") is None:
        print("fastapi not installed locally -- skipping HTTP-layer test "
              "(gateway_core logic already covered by scripts/test_gateway.py). SKIP")
        return

    sys.path.insert(0, str(GATEWAY_DIR))
    import gateway_server as gs  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402

    # 每個測試都要乾淨狀態——gateway_server 模組層級的 GW 是單例，直接重建掉
    gs.GW = gs.Gateway(voice=gs.VoicePool(limit=5))
    gs.GW.queue.max_depth = 3
    client = TestClient(gs.app)

    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True

    r = client.post("/v1/admin/worker/register", json={
        "worker_id": "w1", "url": "https://w1.example", "slots": 1})
    assert r.status_code == 200 and r.json()["ok"] is True

    r = client.post("/v1/call/request", params={"client_id": "clientA"})
    body = r.json()
    assert body["status"] == "connect" and body["worker"]["worker_id"] == "w1"

    r = client.post("/v1/call/request", params={"client_id": "clientB"})
    body = r.json()
    assert body["status"] == "queued" and body["queue"]["position"] == 1

    r = client.get("/v1/call/poll", params={"client_id": "clientB"})
    assert r.json()["status"] == "queued"

    r = client.post("/v1/call/release", json={"worker_id": "w1", "duration_s": 30.0})
    assert r.json()["ok"] is True
    assert r.json()["advanced"]["client_id"] == "clientB"

    r = client.get("/v1/call/poll", params={"client_id": "clientB"})
    assert r.json()["status"] == "connect"

    # 佇列滿載拒絕路徑（真的走 HTTP 層，不只是核心邏輯）
    gs.GW.workers.get("w1").active = 999  # 假裝滿載，逼進佇列
    for i in range(3):
        client.post("/v1/call/request", params={"client_id": "q%d" % i})
    r = client.post("/v1/call/request", params={"client_id": "overflow"})
    assert r.json()["status"] == "reject" and r.json()["reason"] == "queue_full"

    class HealthDurable:
        def __init__(self):
            self.authenticated = []

        def authenticate(self, bearer):
            self.authenticated.append(bearer)
            if bearer == "backend-error-token":
                raise gs.CallControlError("upstream auth unavailable")
            if bearer != "valid-user-token":
                raise gs.CallControlAuthError("invalid_token")
            return object()

        def snapshot(self):
            return {"active_calls": 0, "queue_depth": 0}

    original_gate = gs._GATE
    original_admin_gate = gs._ADMIN_GATE
    original_durable = gs.DURABLE
    try:
        durable = HealthDurable()
        gs._GATE = "private-legacy-key"
        gs._ADMIN_GATE = "private-admin-key"
        gs.DURABLE = durable

        denied = client.get("/health")
        assert denied.status_code == 401
        wrong_key = client.get("/health", params={"key": "public-app-key"})
        assert wrong_key.status_code == 401
        invalid_user = client.get("/health", headers={"Authorization": "Bearer invalid-user-token"})
        assert invalid_user.status_code == 401
        invalid_call = client.post("/v1/calls", headers={"Authorization": "Bearer invalid-user-token"}, json={
            "character_id": "nening", "idempotency_key": "invalid-auth-probe",
        })
        assert invalid_call.status_code == 401
        assert invalid_call.json() == {"detail": "authentication_required"}
        assert "Supabase" not in invalid_call.text and "token" not in invalid_call.text
        backend_error = client.post("/v1/calls", headers={"Authorization": "Bearer backend-error-token"}, json={
            "character_id": "nening", "idempotency_key": "auth-backend-probe",
        })
        assert backend_error.status_code == 503
        assert backend_error.json() == {"detail": "authentication_verification_unavailable"}

        user_health = client.get("/health", headers={"Authorization": "Bearer valid-user-token"})
        assert user_health.status_code == 200 and user_health.json()["durable_ready"] is True
        assert user_health.json() == {"ok": True, "durable_ready": True}
        for sensitive_key in ("snapshot", "engine", "mode", "durable_error"):
            assert sensitive_key not in user_health.json()

        user_metrics = client.get("/metrics", headers={"Authorization": "Bearer valid-user-token"})
        assert user_metrics.status_code == 403
        user_admin = client.post("/v1/internal/reap", headers={"Authorization": "Bearer valid-user-token"})
        assert user_admin.status_code == 403

        admin_health = client.get("/health", headers={"Authorization": "Bearer private-admin-key"})
        assert admin_health.status_code == 200 and admin_health.json()["ok"] is True
        assert "snapshot" in admin_health.json() and admin_health.json()["mode"] == "durable"
        client_health = client.get("/health", params={"key": "private-legacy-key"})
        assert client_health.status_code == 200 and "snapshot" in client_health.json()
        assert durable.authenticated == [
            "invalid-user-token", "invalid-user-token", "backend-error-token", "valid-user-token"
        ]
    finally:
        gs._GATE = original_gate
        gs._ADMIN_GATE = original_admin_gate
        gs.DURABLE = original_durable

    print("Gateway HTTP-layer smoke test: ALL PASS")


if __name__ == "__main__":
    main()
