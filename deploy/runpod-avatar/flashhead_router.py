# -*- coding: utf-8 -*-
"""Munea FlashHead 多程序前置分流器（2026-07-23 卡西法，合批手術階段 2）。

只在 MUNEA_FH_PROCS > 1 時才需要啟動——單程序（MUNEA_FH_PROCS 未設或 1）時
現行單一 flashhead_server.py 照舊直接綁 MUNEA_FACE_PORT，不會有這支東西，
一個位元都不變（相容性鐵律）。

背景：Glows/RunPod 一張卡目前只映射一個對外 http 埠，但今晚同卡 A/B 實測
證明「3 個獨立 process（各自 1 slot）」比「1 個 process 內 3 條 thread」快
1.6 倍（GIL 序列化才是真病灶，見階段 1 PR 說明的誠實紀錄）。這支負責把
「對外只有一個門牌」跟「後面其實有 N 台各自獨立的引擎」接起來：監聽
MUNEA_FACE_PORT（保留現行對外門牌不變），依 flashhead_router_core.py 的
路由表把請求轉給對應的 backend process（各自綁在 MUNEA_FACE_PORT+1..+N）。

路由決策本身（該轉去哪個 process）全部委給 flashhead_router_core.py 那支
零重依賴的純函式模組——這支檔案只負責「真的把 bytes 轉過去」的網路管線，
盡量薄、盡量不加邏輯，好讓決策邏輯可以離線測試、管線邏輯可以用假 backend
做端到端整合測試（見 scripts/test_flashhead_router.py）。

跑法（機器上，MUNEA_FH_PROCS>1 時由 start-vocaframe.sh 自動起）：
  MUNEA_FH_PROCS=3 MUNEA_FACE_PORT=8188 MUNEA_WORKER_ID=glows-tw06 python3 flashhead_router.py
"""
import asyncio
import os
import sys

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flashhead_router_core import (RoundRobinPicker, merge_health_snapshots,
                                    pick_backend_index, process_port)

BACKEND_HOST = os.environ.get("MUNEA_FH_ROUTER_BACKEND_HOST", "127.0.0.1")
N_PROCS = max(1, int(os.environ.get("MUNEA_FH_PROCS", "1")))
BASE_PORT = int(os.environ.get("MUNEA_FACE_PORT", "8188"))
BASE_WORKER_ID = os.environ.get("MUNEA_WORKER_ID", "").strip()
REQUEST_TIMEOUT_S = float(os.environ.get("MUNEA_FH_ROUTER_TIMEOUT_S", "15"))
CORS_ORIGINS = [x.strip() for x in os.environ.get(
    "MUNEA_WORKER_CORS_ORIGINS",
    "capacitor://localhost,ionic://localhost,http://localhost,https://localhost,https://munea-b2b.vercel.app",
).split(",") if x.strip()]

round_robin = RoundRobinPicker(N_PROCS)


def backend_port(index):
    return process_port(BASE_PORT, index)


def backend_base_url(index):
    return "http://%s:%d" % (BACKEND_HOST, backend_port(index))


def _explicit_slot(request):
    raw = request.query.get("slot")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _forward_http(request, index):
    if index is None:
        return web.json_response({"error": "no backend process available"}, status=503)
    target = backend_base_url(index) + request.path
    body = await request.read()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    try:
        async with ClientSession(timeout=ClientTimeout(total=REQUEST_TIMEOUT_S)) as session:
            async with session.request(request.method, target, params=request.query,
                                        data=body, headers=headers) as resp:
                resp_body = await resp.read()
                return web.Response(status=resp.status, body=resp_body,
                                     content_type=resp.content_type)
    except asyncio.TimeoutError:
        return web.json_response({"error": "backend timeout", "index": index}, status=504)
    except OSError as exc:
        return web.json_response({"error": "backend unreachable", "index": index,
                                   "detail": str(exc)}, status=502)


async def handle_offer(request):
    token = request.query.get("token", "")
    idx = pick_backend_index("/offer", token, None, BASE_WORKER_ID, N_PROCS, round_robin)
    return await _forward_http(request, idx)


async def handle_demo_session(request):
    idx = pick_backend_index("/demo/session", "", None, BASE_WORKER_ID, N_PROCS, round_robin)
    return await _forward_http(request, idx)


async def handle_switch(request):
    token = request.query.get("token", "")
    idx = pick_backend_index("/switch", token, _explicit_slot(request),
                              BASE_WORKER_ID, N_PROCS, round_robin)
    if idx is None:
        return web.json_response({"error": "slot out of range"}, status=400)
    return await _forward_http(request, idx)


async def handle_diag(request):
    # 純日誌用途，哪一台都行，固定送 process 0 方便查 log 時知道去哪找。
    return await _forward_http(request, 0)


async def handle_health(request):
    results = [None] * N_PROCS

    async def fetch(i):
        try:
            async with ClientSession(timeout=ClientTimeout(total=5)) as session:
                async with session.get(backend_base_url(i) + "/health",
                                        params=request.query) as resp:
                    if resp.status == 200:
                        results[i] = await resp.json()
        except Exception:
            results[i] = None

    await asyncio.gather(*(fetch(i) for i in range(N_PROCS)))
    body = merge_health_snapshots(list(enumerate(results)), BASE_WORKER_ID)
    return web.json_response(body)


async def handle_audio_ws(request):
    token = request.query.get("token", "")
    idx = pick_backend_index("/audio", token, None, BASE_WORKER_ID, N_PROCS, round_robin)
    if idx is None:
        return web.json_response({"error": "no backend process available"}, status=503)

    ws_client = web.WebSocketResponse()
    await ws_client.prepare(request)

    backend_url = "ws://%s:%d/audio" % (BACKEND_HOST, backend_port(idx))
    if request.query_string:
        backend_url += "?" + request.query_string

    try:
        async with ClientSession() as session:
            async with session.ws_connect(backend_url, timeout=REQUEST_TIMEOUT_S) as ws_backend:

                async def pump_client_to_backend():
                    async for msg in ws_client:
                        if msg.type == WSMsgType.TEXT:
                            await ws_backend.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await ws_backend.send_bytes(msg.data)
                        else:
                            break
                    if not ws_backend.closed:
                        await ws_backend.close()

                async def pump_backend_to_client():
                    async for msg in ws_backend:
                        if msg.type == WSMsgType.TEXT:
                            await ws_client.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await ws_client.send_bytes(msg.data)
                        else:
                            break
                    if not ws_client.closed:
                        await ws_client.close()

                await asyncio.gather(pump_client_to_backend(), pump_backend_to_client())
    except (OSError, asyncio.TimeoutError):
        if not ws_client.closed:
            await ws_client.close()

    return ws_client


@web.middleware
async def cors_middleware(request, handler):
    origin = request.headers.get("Origin", "")
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    if origin in CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def build_app():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_post("/offer", handle_offer)
    app.router.add_options("/offer", handle_offer)
    app.router.add_post("/demo/session", handle_demo_session)
    app.router.add_options("/demo/session", handle_demo_session)
    app.router.add_post("/switch", handle_switch)
    app.router.add_options("/switch", handle_switch)
    app.router.add_post("/diag", handle_diag)
    app.router.add_options("/diag", handle_diag)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/audio", handle_audio_ws)
    return app


def main():
    if N_PROCS <= 1:
        print("[router] MUNEA_FH_PROCS<=1 -- the single flashhead_server "
              "process should bind MUNEA_FACE_PORT directly instead. "
              "Refusing to start (would just collide on the same port).",
              flush=True)
        raise SystemExit(1)
    if not BASE_WORKER_ID:
        print("[router] WARNING: MUNEA_WORKER_ID is empty -- token-based "
              "worker_id routing will never match, every request with a real "
              "call token will fall back to round robin.", flush=True)
    app = build_app()
    print("[router] listening on 0.0.0.0:%d -> %d backend process(es) at %s:%d..%d"
          % (BASE_PORT, N_PROCS, BACKEND_HOST, backend_port(0), backend_port(N_PROCS - 1)),
          flush=True)
    web.run_app(app, host="0.0.0.0", port=BASE_PORT)


if __name__ == "__main__":
    main()
