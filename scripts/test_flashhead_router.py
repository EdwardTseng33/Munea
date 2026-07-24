# -*- coding: utf-8 -*-
"""FlashHead 路由器端到端整合測試（2026-07-23 卡西法，合批手術階段 2）。

**不是 test:launch 的一部分**（需要 aiohttp，engine/requirements.txt 沒有
保證這個套件在每台跑測試的機器上都裝好——跟 test_flashhead_patch_apply_live.py
同一種「加分驗證、環境不滿足就優雅跳過」設計）。有裝 aiohttp 時這支會真的
起兩個假 backend stub server + 真正的 flashhead_router.py app，把請求打過
去，驗證「bytes 真的轉得過去」，不只是純邏輯層面的路由決策對不對
（那部分見 test_flashhead_router_core.py，已經接進 test:launch）。

跑法：python scripts/test_flashhead_router.py
"""
import asyncio
import base64
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    import aiohttp
    from aiohttp import web
except ImportError:
    print("test_flashhead_router (integration): SKIP (aiohttp not installed)")
    sys.exit(0)


def _make_token(payload):
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    return encoded + ".fake-signature-not-checked-by-router"


def build_fake_backend(index):
    """假 backend：只實作路由器會打到的幾個端點，回應裡帶著自己的 index，
    讓測試可以斷言「這個請求真的落在我預期的那個 process 上」。"""
    app = web.Application()

    async def health(request):
        return web.json_response({
            "ok": True, "char": "a05",
            "capacity": {"limit": 1, "active": 0, "available": True},
        })

    async def offer(request):
        body = await request.json()
        # 真的 backend（flashhead_server.py）每次 /offer 都 uuid4() 生一個
        # 全新 session id，跟 backend index 無關——這裡刻意用亂數而不是
        # "fake-session-%d" % index，確保測試真的在驗證「router 從回應內容
        # 讀出 session、記表」這條路徑，不是巧合對上 index。
        return web.json_response({"backend_index": index, "sdp_echo": body.get("sdp"),
                                   "session": uuid.uuid4().hex})

    async def switch(request):
        return web.json_response({"backend_index": index, "ok": True})

    async def demo_session(request):
        return web.json_response({"backend_index": index, "token": "demo-token-from-p%d" % index})

    async def audio_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await ws.send_str("echo-from-p%d:%s" % (index, msg.data))
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await ws.send_bytes(b"p%d:" % index + msg.data)
            else:
                break
        return ws

    app.router.add_get("/health", health)
    app.router.add_post("/offer", offer)
    app.router.add_post("/switch", switch)
    app.router.add_post("/demo/session", demo_session)
    app.router.add_get("/audio", audio_ws)
    return app


BASE_PORT = int(os.environ.get("MUNEA_FH_ROUTER_TEST_BASE_PORT", "18188"))
N_PROCS = 2
BASE_WORKER_ID = "test-box"


async def _start_site(app, port, host="127.0.0.1"):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner


async def async_main():
    os.environ["MUNEA_FH_PROCS"] = str(N_PROCS)
    os.environ["MUNEA_FACE_PORT"] = str(BASE_PORT)
    os.environ["MUNEA_WORKER_ID"] = BASE_WORKER_ID
    os.environ["MUNEA_FH_ROUTER_BACKEND_HOST"] = "127.0.0.1"

    sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))
    import flashhead_router as router  # noqa: E402  (env vars must be set before this import)

    runners = []
    try:
        for i in range(N_PROCS):
            backend_app = build_fake_backend(i)
            runners.append(await _start_site(backend_app, BASE_PORT + 1 + i))

        router_app = router.build_app()
        runners.append(await _start_site(router_app, BASE_PORT))

        async with aiohttp.ClientSession() as client:
            base = "http://127.0.0.1:%d" % BASE_PORT

            # /offer with a token whose worker_id points at process 1 -- must
            # land on backend 1, not round-robin, not backend 0.
            token_p1 = _make_token({"worker_id": "test-box-p1", "call_id": "call-1"})
            async with client.post(base + "/offer", params={"token": token_p1},
                                    json={"sdp": "fake-sdp", "type": "offer"}) as resp:
                assert resp.status == 200, await resp.text()
                data = await resp.json()
                assert data["backend_index"] == 1, "expected /offer routed to backend 1, got %r" % data

            token_p0 = _make_token({"worker_id": "test-box-p0", "call_id": "call-2"})
            async with client.post(base + "/offer", params={"token": token_p0},
                                    json={"sdp": "fake-sdp-2", "type": "offer"}) as resp:
                data = await resp.json()
                assert data["backend_index"] == 0, "expected /offer routed to backend 0, got %r" % data

            # /switch?slot=1 -- explicit slot routing, no token needed.
            async with client.post(base + "/switch", params={"slot": "1", "char": "a06"}) as resp:
                data = await resp.json()
                assert data["backend_index"] == 1, "expected /switch slot=1 -> backend 1, got %r" % data

            # /demo/session -- must always land on backend 0.
            async with client.post(base + "/demo/session", json={"password": "x"}) as resp:
                data = await resp.json()
                assert data["backend_index"] == 0, "expected /demo/session -> backend 0, got %r" % data

            # /health -- aggregated across both fake backends.
            async with client.get(base + "/health") as resp:
                data = await resp.json()
                assert data["ok"] is True
                assert data["capacity"]["limit"] == N_PROCS
                assert len(data["slots"]) == N_PROCS
                assert {s["worker_id"] for s in data["slots"]} == {"test-box-p0", "test-box-p1"}

            # /audio websocket proxying -- full round trip through the router.
            token_ws_p1 = _make_token({"worker_id": "test-box-p1", "call_id": "call-3"})
            async with client.ws_connect(base + "/audio", params={"token": token_ws_p1}) as ws:
                await ws.send_str("hello")
                msg = await ws.receive(timeout=5)
                assert msg.type == aiohttp.WSMsgType.TEXT
                assert msg.data == "echo-from-p1:hello", "expected WS reply from backend 1, got %r" % msg.data
                await ws.close()

            # 2026-07-24 熱修的正面回歸測試（真的走 HTTP + WS，不只是純邏輯）：
            # key= 萬用鑰匙情境（完全不帶 token）下，兩通 /offer 被 round
            # robin 分到不同 backend，router 從「真正的 HTTP 回應內容」讀出
            # session id 記表；之後交錯打 /audio?session=... 必須每次都精準
            # 落回各自的 home，不能被 round robin 繼續往前轉打散
            # （這正是正式線 403 事故的真實重現路徑）。
            async with client.post(base + "/offer",
                                    json={"sdp": "no-token-sdp-1", "type": "offer"}) as resp:
                data = await resp.json()
                session_x = data["session"]
                home_x = data["backend_index"]
            async with client.post(base + "/offer",
                                    json={"sdp": "no-token-sdp-2", "type": "offer"}) as resp:
                data = await resp.json()
                session_y = data["session"]
                home_y = data["backend_index"]
            assert home_x != home_y, (
                "round robin 的頭兩次分派必須落在不同 backend 才重現得出原本的 bug 場景 "
                "(got home_x=%r home_y=%r)" % (home_x, home_y)
            )

            call_order = [(session_x, home_x), (session_y, home_y), (session_y, home_y),
                          (session_x, home_x), (session_x, home_x), (session_y, home_y)]
            for sid, expected_home in call_order:
                async with client.ws_connect(base + "/audio", params={"session": sid}) as ws:
                    await ws.send_str("ping")
                    msg = await ws.receive(timeout=5)
                    assert msg.type == aiohttp.WSMsgType.TEXT
                    expected = "echo-from-p%d:ping" % expected_home
                    assert msg.data == expected, (
                        "session %s must route home to backend %d, got %r (expected %r) "
                        "-- session stickiness regressed" % (sid, expected_home, msg.data, expected)
                    )
                    await ws.close()

        print("test_offer_routes_by_token_worker_id: PASS")
        print("test_switch_routes_by_explicit_slot: PASS")
        print("test_demo_session_routes_to_backend_zero: PASS")
        print("test_health_aggregates_all_backends: PASS")
        print("test_audio_websocket_proxies_end_to_end: PASS")
        print("test_two_sessions_interleaved_no_token_stick_to_their_home_backend: PASS "
              "(session_x always -> p%d, session_y always -> p%d)" % (home_x, home_y))
        print("FlashHead router integration test: ALL PASS")
    finally:
        for r in runners:
            await r.cleanup()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
