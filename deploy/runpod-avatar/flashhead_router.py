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

2026-07-24 熱修（正式線上線後抓到）：key= 萬用鑰匙／任何無 token 或 token
worker_id 對不上本機的請求走 round robin，/offer 建立 session 在 A 房、緊
接著的 /audio?session=X 完全沒有路由信號可以決定性地推回 A 房，round robin
繼續往前轉就把它送去 B 房、403。修法見 flashhead_router_core.py 的
SessionRouteTable：/offer 成功回應後記下 session_id -> backend index，
/audio、/switch 帶 session 參數時優先查這張表。

跑法（機器上，MUNEA_FH_PROCS>1 時由 start-vocaframe.sh 自動起）：
  MUNEA_FH_PROCS=3 MUNEA_FACE_PORT=8188 MUNEA_WORKER_ID=glows-tw06 python3 flashhead_router.py
"""
import asyncio
import json
import os
import sys

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flashhead_router_core import (RoundRobinPicker, SessionRouteTable, merge_health_snapshots,
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
# 2026-07-24 熱修：session -> backend 對照表，TTL/上限防漏水（見
# flashhead_router_core.SessionRouteTable 文件）。1 小時夠涵蓋任何合理的
# 單通通話長度；500 筆遠高於這張卡實際容量（N 通常是 2-3），純粹當安全閥。
SESSION_TTL_S = float(os.environ.get("MUNEA_FH_ROUTER_SESSION_TTL_S", "3600"))
SESSION_MAX_ENTRIES = int(os.environ.get("MUNEA_FH_ROUTER_SESSION_MAX", "500"))

round_robin = RoundRobinPicker(N_PROCS)
session_table = SessionRouteTable(ttl_s=SESSION_TTL_S, max_entries=SESSION_MAX_ENTRIES)


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


async def _forward_http(request, index, on_success=None):
    """on_success(resp_body_bytes, index) 在 backend 回 200 時被呼叫一次
    -- 目前只有 handle_offer 用它來記錄 session -> backend 對照
    （2026-07-24 熱修，見檔頭說明），其餘呼叫端不傳就跟以前完全一樣。"""
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
                if resp.status == 200 and on_success is not None:
                    on_success(resp_body, index)
                return web.Response(status=resp.status, body=resp_body,
                                     content_type=resp.content_type)
    except asyncio.TimeoutError:
        return web.json_response({"error": "backend timeout", "index": index}, status=504)
    except OSError as exc:
        return web.json_response({"error": "backend unreachable", "index": index,
                                   "detail": str(exc)}, status=502)


def _record_session_from_offer_response(resp_body, index):
    """/offer 成功回應的 JSON body 帶 "session" 欄位（flashhead_server.py 的
    /offer handler 固定回傳 {"sdp":..., "type":..., "session": session_id}）
    -- 記進 session_table，後續 /audio、/switch 帶同一個 session 就能查表
    決定性地回到這個 backend，不再受 round robin 影響（2026-07-24 熱修）。
    解析失敗/沒有 session 欄位就靜默略過，不影響原本的轉發結果。"""
    try:
        data = json.loads(resp_body)
    except (ValueError, TypeError):
        return
    session_id = data.get("session") if isinstance(data, dict) else None
    if session_id:
        session_table.record(session_id, index)


async def handle_offer(request):
    token = request.query.get("token", "")
    # /offer 本身不接收上游傳入的 session（flashhead_server.py 的 /offer
    # handler 永遠自己 uuid4 生一個新的，見檔頭 2026-07-24 說明），這裡查表
    # 只是防呆 -- 正常情況下不會命中。
    idx = pick_backend_index("/offer", token, None, BASE_WORKER_ID, N_PROCS, round_robin,
                              session=request.query.get("session", ""), session_table=session_table)
    return await _forward_http(request, idx, on_success=_record_session_from_offer_response)


async def handle_demo_session(request):
    idx = pick_backend_index("/demo/session", "", None, BASE_WORKER_ID, N_PROCS, round_robin)
    return await _forward_http(request, idx)


async def handle_switch(request):
    token = request.query.get("token", "")
    idx = pick_backend_index("/switch", token, _explicit_slot(request),
                              BASE_WORKER_ID, N_PROCS, round_robin,
                              session=request.query.get("session", ""), session_table=session_table)
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
    # 2026-07-24 熱修核心：session 查表優先於 token/round robin，這是修
    # 正式線那個 403 bug 的關鍵一行 -- 沒有這行，key= 萬用鑰匙路徑的
    # /audio 每次都吃 round robin，跟 /offer 建立 session 的那個 process
    # 對不上。
    idx = pick_backend_index("/audio", token, None, BASE_WORKER_ID, N_PROCS, round_robin,
                              session=request.query.get("session", ""), session_table=session_table)
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
