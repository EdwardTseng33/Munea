"""沐寧 · 即時語音橋接（stage 1）

瀏覽器 ⇄ 這個橋 ⇄ Gemini Live。讓長輩「開口就即時跟寧寧講電話」。
- 獨立的 async WebSocket 伺服器（:8201），不動 engine/server.py（那是 Codex 的地盤）。
- 把寧寧的人格＋非醫療界線＋長輩記憶（重用 chat_engine）當成 Live 的 system instruction，
  所以即時語音的寧寧也有個性、也記得使用者。

跑法：GEMINI_API_KEY=... python engine/live_voice_server.py
訊息協定（瀏覽器→橋）：
  - binary：麥克風 PCM16 @16kHz（即時串流）
  - {"type":"text","text":"..."}：純文字（測試/打字備援）
  - {"type":"audio_end"}：這段說完了
訊息協定（橋→瀏覽器）：
  - binary：寧寧的語音 PCM16 @24kHz
  - {"type":"caption","who":"nening|user","text":"..."}
  - {"type":"interrupted"} / {"type":"turn_complete"}
"""

import os
import sys
import json
import time
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chat_engine as eng
from google import genai
from google.genai import types
import websockets
from websockets.http11 import Response
from websockets.datastructures import Headers

MODEL = "gemini-3.1-flash-live-preview"
KEY = os.environ.get("GEMINI_API_KEY")
if not KEY:
    sys.exit("需要 GEMINI_API_KEY")

client = genai.Client(api_key=KEY)

import mimetypes

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "web"))


def _file_response(rel):
    fp = os.path.normpath(os.path.join(WEB, rel))
    if not fp.startswith(WEB) or not os.path.isfile(fp):
        return Response(404, "Not Found", Headers({"Content-Length": "0"}), b"")
    with open(fp, "rb") as f:
        body = f.read()
    ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
    h = Headers()
    h["Content-Type"] = ctype + ("; charset=utf-8" if ctype.startswith("text/") else "")
    h["Content-Length"] = str(len(body))
    return Response(200, "OK", h, body)


def process_request(connection, request):
    """非 WebSocket 的請求就當靜態網站服務（測試頁＋臉圖等），讓網頁與語音走同一個門。"""
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None
    path = request.path.split("?")[0].lstrip("/")
    if path in ("", "index.html"):
        path = "live-voice-test.html"
    return _file_response(path)


def system_instruction(char="寧寧"):
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    base = c.get("persona", "")
    base += eng.RED
    base += (
        "（現在是即時語音通話。你剛接起電話：先用『一句』溫暖的話打招呼就好，別一次講一大串。"
        "你還不知道對方是誰，所以絕對不要亂猜名字、不要亂叫稱呼（不可以叫人『阿姨』或任何名字）；"
        "可以自然地說『喂～我是寧寧，今天想聊聊什麼呀？』。"
        "整通電話都要：口語、句子短、一次只講一兩句、講完就停下來等對方回應。）"
    )
    return base


def live_config(char="寧寧"):
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system_instruction(char),
    )


def _diag(cid, event, **kv):
    parts = " ".join(f"{k}={v}" for k, v in kv.items())
    print(f"[diag] c{cid} {event} {parts}".rstrip(), flush=True)


_CID = {"n": 0}


async def handle(ws):
    char = "寧寧"
    _CID["n"] += 1
    cid = _CID["n"]
    t0 = time.monotonic()
    st = {"in": 0, "out": 0, "last_in": None, "await_first": True, "first_mic": False}
    _diag(cid, "connected")
    try:
        async with client.aio.live.connect(model=MODEL, config=live_config(char)) as session:
            async def from_browser():
                async for message in ws:
                    if isinstance(message, (bytes, bytearray)):
                        n = len(message)
                        st["in"] += n
                        st["last_in"] = time.monotonic()
                        st["await_first"] = True
                        if not st["first_mic"]:
                            st["first_mic"] = True
                            _diag(cid, "node.mic_uplink", ms=round((st["last_in"] - t0) * 1000))
                        await session.send_realtime_input(
                            audio=types.Blob(data=bytes(message), mime_type="audio/pcm;rate=16000")
                        )
                    else:
                        try:
                            obj = json.loads(message)
                        except Exception:
                            continue
                        t = obj.get("type")
                        if t == "text" and obj.get("text"):
                            st["last_in"] = time.monotonic()
                            st["await_first"] = True
                            await session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part(text=obj["text"])]),
                                turn_complete=True,
                            )
                        elif t == "audio_end":
                            await session.send_realtime_input(audio_stream_end=True)

            async def from_live():
                turn_out = 0
                async for msg in session.receive():
                    data = getattr(msg, "data", None)
                    if data:
                        if st["await_first"] and st["last_in"] is not None:
                            lat = round((time.monotonic() - st["last_in"]) * 1000)
                            st["await_first"] = False
                            _diag(cid, "node.first_audio", latency_ms=lat)
                            try:
                                await ws.send(json.dumps({"type": "diag", "firstAudioMs": lat}))
                            except Exception:
                                pass
                        st["out"] += len(data)
                        turn_out += len(data)
                        await ws.send(data)
                    sc = getattr(msg, "server_content", None)
                    if sc:
                        ot = getattr(sc, "output_transcription", None)
                        if ot and getattr(ot, "text", None):
                            await ws.send(json.dumps({"type": "caption", "who": "nening", "text": ot.text}))
                        it = getattr(sc, "input_transcription", None)
                        if it and getattr(it, "text", None):
                            await ws.send(json.dumps({"type": "caption", "who": "user", "text": it.text}))
                        if getattr(sc, "interrupted", False):
                            _diag(cid, "node.interrupted")
                            await ws.send(json.dumps({"type": "interrupted"}))
                        if getattr(sc, "turn_complete", False):
                            ms = round(turn_out / (24000 * 2) * 1000)
                            _diag(cid, "node.turn_done", out_bytes=turn_out, audio_ms=ms)
                            turn_out = 0
                            st["await_first"] = True
                            await ws.send(json.dumps({"type": "turn_complete"}))

            await asyncio.gather(from_browser(), from_live())
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        _diag(cid, "node.error", err=f"{type(e).__name__}:{str(e)[:80]}")
    finally:
        _diag(cid, "closed", in_bytes=st["in"], out_bytes=st["out"])


async def main():
    async with websockets.serve(handle, "127.0.0.1", 8201, max_size=None, process_request=process_request):
        print("即時語音橋接已啟動：http://127.0.0.1:8201 （網頁＋語音同門，模型 " + MODEL + "）")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
