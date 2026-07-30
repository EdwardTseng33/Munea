# -*- coding: utf-8 -*-
"""WebRTC 最後一哩 · 試作台伺服器（2026-07-30 · Edward 拍板推進）

目的：證明「電話級水管」（WebRTC）這條路我們自己搭得起來——
瀏覽器的聲音送進來、原路彈回去（回音測試），同時開一條資料通道量來回時間。

為什麼要有這台：7/30 晚的災難實錘「斷續全發生在手機↔機房那一哩」——
現在那段走的是普通水管（WebSocket），網路一晃聲音就斷。WebRTC 內建
防抖緩衝、自動調速、丟包補償，全世界視訊通話都用它。這台試作台先驗：
  ① 我們的 Python 端能不能穩定收/發 WebRTC 聲音（aiortc）
  ② 來回延遲、抖動長什麼樣（資料通道 ping 每秒 4 次）
  ③ 之後把「彈回去」換成「接進 Gemini」＝正式接管聊聊的聲音路

跑法：python tools/webrtc-spike/spike_server.py  → 開 http://localhost:8377
"""
import asyncio
import json
import os
import sys

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("SPIKE_PORT", "8377"))
pcs = set()


async def index(request):
    return web.FileResponse(os.path.join(HERE, "spike.html"))


async def offer(request):
    params = await request.json()
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            # ping/pong：瀏覽器帶時間戳來、原樣彈回，讓它自己算來回毫秒
            if isinstance(message, str) and message.startswith("ping:"):
                channel.send("pong:" + message[5:])

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            # 回音：收到什麼聲音、原路送回去（之後這裡換成接 Gemini 的橋）
            pc.addTrack(track)

    @pc.on("connectionstatechange")
    async def on_state():
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=params["sdp"], type=params["type"]))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})


async def on_shutdown(app):
    await asyncio.gather(*[pc.close() for pc in pcs], return_exceptions=True)
    pcs.clear()


def main():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)
    print(f"WebRTC 試作台：http://localhost:{PORT}", flush=True)
    web.run_app(app, host="127.0.0.1", port=PORT, print=None)


if __name__ == "__main__":
    main()
