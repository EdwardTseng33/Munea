# -*- coding: utf-8 -*-
"""WebRTC 最後一哩 · 第 2 步：真的接上聊聊的腦（2026-07-30 晚）

第 1 步（spike_server.py）證明了我們收發得動電話級水管的聲音（回音）。
這一步把「彈回去」換成「接進 Gemini」：

    瀏覽器麥克風 → WebRTC → 這台橋 → 重採樣 48k→16k → Gemini Live
    Gemini 的聲音 24k → 重採樣 → WebRTC → 瀏覽器（防抖緩衝由水管自帶）

同時這就是「假人考場」的雛形：測試頁可以不用麥克風、改播一段真人錄音當嘴巴，
整條真語音路（含講完沒的判斷）自動量——正是 7/30 災難教訓要補的那種驗證。

跑法：GEMINI_API_KEY=... python tools/webrtc-spike/bridge_server.py → http://localhost:8378
注意：試作台限本機、用開發者鑰匙、簡化說明書——不是產品線，驗完管線才談整併。
"""
import asyncio
import fractions
import json
import os
import sys
import time

import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError
from av import AudioFrame, AudioResampler
from google import genai
from google.genai import types

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("SPIKE_PORT", "8378"))
MODEL = os.environ.get("SPIKE_MODEL", "gemini-3.1-flash-live-preview")
pcs = set()


class GeminiVoiceTrack(AudioStreamTrack):
    """把 Gemini 吐回來的 24kHz 聲音，變成 WebRTC 能播的音軌（20ms 一格、48kHz）。

    節奏鐵律：WebRTC 這頭要「準時」——每 20ms 準點交一格；Gemini 那頭是
    「有就一大坨」。中間用佇列當水庫：有料就播料、沒料就交安靜格，
    永遠不遲到＝水管另一端聽起來永遠連續。
    """

    def __init__(self):
        super().__init__()
        self.queue = asyncio.Queue()
        self._resampler = AudioResampler(format="s16", layout="mono", rate=48000)
        self._buf = np.zeros(0, dtype=np.int16)   # 48k 待播樣本
        self._pts = 0
        self._wall0 = None   # 起播牆鐘（配速基準）

    def feed(self, pcm24k: bytes):
        self.queue.put_nowait(pcm24k)

    def flush(self):
        """被打斷＝水庫立刻倒掉（跟正式 App 收到 barge_in 清播放佇列同款）。
        不倒的話，插話考量到的是緩衝裡的殘音、不是她的反應。"""
        while not self.queue.empty():
            self.queue.get_nowait()
        self._buf = np.zeros(0, dtype=np.int16)

    async def recv(self):
        # 每格 20ms＝48000*0.02=960 個樣本
        need = 960
        while len(self._buf) < need and not self.queue.empty():
            chunk = self.queue.get_nowait()
            frame = AudioFrame(format="s16", layout="mono", samples=len(chunk) // 2)
            frame.planes[0].update(chunk)
            frame.sample_rate = 24000
            for rf in self._resampler.resample(frame):
                arr = rf.to_ndarray().reshape(-1).astype(np.int16)
                self._buf = np.concatenate([self._buf, arr])
        if len(self._buf) >= need:
            out, self._buf = self._buf[:need], self._buf[need:]
        else:
            out = np.zeros(need, dtype=np.int16)   # 沒料＝安靜格，準時最重要
        frame = AudioFrame(format="s16", layout="mono", samples=need)
        frame.planes[0].update(out.tobytes())
        frame.sample_rate = 48000
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, 48000)
        self._pts += need
        # 牆鐘校準配速（跟 fake_caller 同病同修）：固定睡 0.02 在 Windows 實際睡 31ms
        # →只有 0.64 倍速。對「起播牆鐘＋已播樣本數」校準、睡過頭下一格自動補回。
        if self._wall0 is None:
            self._wall0 = time.monotonic()
        target = self._wall0 + self._pts / 48000.0
        wait = target - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        return frame


async def run_gemini(session_holder, out_track, status):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    cfg = dict(
        response_modalities=["AUDIO"],
        system_instruction="你是台灣的語音陪伴者寧寧（試作台版）。口語、親切、每次一兩句。",
        speech_config=types.SpeechConfig(
            language_code="cmn-TW",
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Leda"))),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # 收音節奏抄正式線（假人考場要同規格才公平——2026-07-30 第一輪考出 99 段「搶話」，
        # 其實是引擎預設 VAD 太急、錄音每個自然停頓她都跳進來；正式線是低靈敏+800ms 靜音窗）
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=300,
                silence_duration_ms=int(os.environ.get("SPIKE_SILENCE_MS", "800")),
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
    )
    async with client.aio.live.connect(model=MODEL, config=cfg) as session:
        session_holder["s"] = session
        status["engine"] = "connected"
        # （開場招呼探針已拆——假人考場要量「純聽與答」，開場招呼會跟假人錄音重疊、
        #   把整段開頭都算成搶話。要單獨驗下行時再臨時加回。）
        while True:   # receive() 每輪結束會收尾，要外圈重進（跟正式線同款）
          got = False
          async for msg in session.receive():
            got = True
            status["msg_count"] = status.get("msg_count", 0) + 1
            data = getattr(msg, "data", None)
            if data:
                out_track.feed(bytes(data))
                status["her_bytes"] = status.get("her_bytes", 0) + len(data)
                if status.get("turn_asked_at") and not status.get("first_reply_ms"):
                    status["first_reply_ms"] = round((time.monotonic() - status["turn_asked_at"]) * 1000)
            sc = getattr(msg, "server_content", None)
            if sc:
                if getattr(sc, "interrupted", None):
                    out_track.flush()
                    status["interrupts"] = status.get("interrupts", 0) + 1
                ot = getattr(sc, "output_transcription", None)
                if ot and getattr(ot, "text", None):
                    status["caption"] = (status.get("caption", "") + ot.text)[-120:]
          if not got:
            status["engine"] = "receive-ended"
            break


async def pump_uplink(track, session_holder, status):
    """瀏覽器來的聲音 → 16kHz → Gemini。她聽得到你＝這條成立。

    2026-07-30 深夜第一課：一開始每 20ms 送一小包，來回確認的開銷讓上行只有
    真實時間的 0.5 倍——她聽到慢動作破碎人聲、永遠等不到「講完」。
    改攢 200ms 一包（跟正式線的送法同量級），節奏立刻跟上。"""
    resampler = AudioResampler(format="s16", layout="mono", rate=16000)
    buf = b""
    BATCH = 16000 * 2 // 5   # 200ms
    while True:
        try:
            frame = await track.recv()
        except MediaStreamError:
            return
        for rf in resampler.resample(frame):
            buf += rf.to_ndarray().astype(np.int16).tobytes()
        if len(buf) < BATCH:
            continue
        pcm, buf = buf, b""
        s = session_holder.get("s")
        if s is not None:
            arr = np.frombuffer(pcm, dtype=np.int16)
            if arr.size and np.abs(arr).mean() > 200 and not status.get("turn_asked_at"):
                status["turn_asked_at"] = time.monotonic()
            await s.send_realtime_input(
                audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))
            status["you_bytes"] = status.get("you_bytes", 0) + len(pcm)


async def index(request):
    return web.FileResponse(os.path.join(HERE, "bridge.html"))


async def sample_wav(request):
    p = os.path.join(HERE, "..", "..", "web", "demo-assets", "voice-sample.wav")
    return web.FileResponse(os.path.abspath(p))


async def status_endpoint(request):
    return web.json_response(request.app["status"])


async def offer(request):
    params = await request.json()
    # 每通獨立的量測簿（2026-07-30 假人考場轉正）：之前掛全域、上一通的
    # 時間戳污染下一通（first_reply_ms 曾量出 10 萬毫秒的笑話）。
    app_status = {"rtc": "idle", "engine": "connecting"}
    request.app["status"] = app_status   # /status 永遠回「最近一通」
    pc = RTCPeerConnection()
    pcs.add(pc)
    session_holder = {}
    out_track = GeminiVoiceTrack()
    pc.addTrack(out_track)
    tasks = []

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            tasks.append(asyncio.ensure_future(pump_uplink(track, session_holder, app_status)))

    @pc.on("connectionstatechange")
    async def on_state():
        app_status["rtc"] = pc.connectionState
        if pc.connectionState in ("failed", "closed"):
            for t in tasks: t.cancel()
            await pc.close(); pcs.discard(pc)

    tasks.append(asyncio.ensure_future(run_gemini(session_holder, out_track, app_status)))
    await pc.setRemoteDescription(RTCSessionDescription(sdp=params["sdp"], type=params["type"]))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("需要 GEMINI_API_KEY")
    app = web.Application()
    app["status"] = {"rtc": "idle", "engine": "connecting"}
    app.router.add_get("/", index)
    app.router.add_get("/sample.wav", sample_wav)
    app.router.add_get("/status", status_endpoint)
    app.router.add_post("/offer", offer)
    print(f"WebRTC×Gemini 橋：http://localhost:{PORT}", flush=True)
    web.run_app(app, host="127.0.0.1", port=PORT, print=None)


if __name__ == "__main__":
    main()
