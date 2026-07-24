# -*- coding: utf-8 -*-
"""聊聊分流閘道 · worker 健康回報防呆測試（2026-07-24 卡西法）。

驗 deploy/gateway/gateway_server.py 的 `/v1/internal/workers/{id}/health` 端點：一旦
機器被標成終止態（terminated / stopped / exited / disabled），任何 healthy 心跳都不能
再把它改回上線——避免 RunPod 備援控制器每 ~15s 一次的心跳，把剛移除的機器復活，
逼操作員靠賽跑重試才移得掉。

跟 scripts/test_gateway_http.py 一樣走 FastAPI TestClient（需本機裝 fastapi/httpx，
CPU-only、pip 幾秒；沒裝就跳過不算失敗）。跑法：python scripts/test_gateway_worker_health.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "deploy" / "gateway"


class FakeWorkerStore:
    """只實作 health 端點會用到的兩支：get_worker（讀目前列）+ update_worker（PATCH 合併）。

    語意刻意貼齊 SupabaseCallStore：get_worker 回目前整列或 None；update_worker 把 values
    併進該列後回傳。這樣端點的防呆判斷跑在真實資料流上，不是空測。
    """

    def __init__(self, workers):
        self.workers = {wid: dict(row) for wid, row in workers.items()}

    def get_worker(self, worker_id):
        row = self.workers.get(worker_id)
        return dict(row) if row is not None else None

    def update_worker(self, worker_id, values):
        row = self.workers.get(worker_id)
        if row is None:
            return {}
        row.update(values)
        return dict(row)


def main():
    if importlib.util.find_spec("fastapi") is None:
        print("fastapi not installed locally -- skipping worker-health guard test. SKIP")
        return

    sys.path.insert(0, str(GATEWAY_DIR))
    import gateway_server as gs  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402

    client = TestClient(gs.app)
    admin_headers = {"X-Munea-Admin-Token": "private-admin-key"}

    original_admin_gate = gs._ADMIN_GATE
    original_durable = gs.DURABLE
    try:
        gs._ADMIN_GATE = "private-admin-key"

        # 1) 每一種終止態機器 + 一次 healthy 心跳 → status 必須維持終止態、不被復活。
        for terminal_status in ("terminated", "stopped", "exited", "disabled"):
            store = FakeWorkerStore({
                "w-term": {
                    "worker_id": "w-term",
                    "status": terminal_status,
                    "last_heartbeat_at": "2026-07-24T00:00:00Z",
                },
            })
            gs.DURABLE = store

            resp = client.post(
                "/v1/internal/workers/w-term/health",
                headers=admin_headers, json={"healthy": True})
            assert resp.status_code == 200, (terminal_status, resp.status_code, resp.text)
            assert resp.json()["ok"] is True

            # 核心斷言：終止態黏得住，healthy 心跳沒把它改回 ready。
            assert store.workers["w-term"]["status"] == terminal_status, (
                terminal_status, store.workers["w-term"]["status"])
            # 心跳時鐘仍有刷新（記錄機器還在跳），只是不動 status。
            assert store.workers["w-term"]["last_heartbeat_at"] != "2026-07-24T00:00:00Z"

        # 2) 終止態機器收到 unhealthy 心跳 → 一樣不動 status（不會被降級蓋掉停機事實）。
        store = FakeWorkerStore({
            "w-term": {"worker_id": "w-term", "status": "terminated",
                       "last_heartbeat_at": "2026-07-24T00:00:00Z"},
        })
        gs.DURABLE = store
        resp = client.post(
            "/v1/internal/workers/w-term/health",
            headers=admin_headers, json={"healthy": False})
        assert resp.status_code == 200 and resp.json()["ok"] is True
        assert store.workers["w-term"]["status"] == "terminated"

        # 3) 回歸：非終止態機器（unhealthy）收到 healthy 心跳 → 照常復原成 ready。
        #    確認防呆沒有把正常的健康復原一起擋掉。
        store = FakeWorkerStore({
            "w-live": {"worker_id": "w-live", "status": "unhealthy",
                       "last_heartbeat_at": "2026-07-24T00:00:00Z"},
        })
        gs.DURABLE = store
        resp = client.post(
            "/v1/internal/workers/w-live/health",
            headers=admin_headers, json={"healthy": True})
        assert resp.status_code == 200 and resp.json()["ok"] is True
        assert store.workers["w-live"]["status"] == "ready", store.workers["w-live"]["status"]

        # 4) 門禁維持：沒有 admin token 一律 403（心跳端點不對外開放）。
        gs.DURABLE = FakeWorkerStore({
            "w-term": {"worker_id": "w-term", "status": "terminated"}})
        denied = client.post("/v1/internal/workers/w-term/health", json={"healthy": True})
        assert denied.status_code == 403, denied.status_code
    finally:
        gs._ADMIN_GATE = original_admin_gate
        gs.DURABLE = original_durable

    print("Gateway worker-health terminal-guard test: ALL PASS")


if __name__ == "__main__":
    main()
