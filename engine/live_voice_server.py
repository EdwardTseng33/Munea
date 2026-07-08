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
from env_loader import load_engine_env
load_engine_env()  # 跟 server.py 同款：自動吃 engine/.env.local 的鑰匙、環境變數優先
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


import server  # 重用文字聊天同一套「腦」組裝：人格層＋記憶層＋感知層＋守護腦，確保即時語音同步


def system_instruction(char="寧寧", name=None, mood=None, topics=None):
    """跟 /chat 同一套腦：角色人格 + 非醫療界線 + 記憶層 + 感知層 + 守護腦。"""
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    # 共同底盤（管家身分＋專業邊界＋告警/情緒/調解能力）在最前面，角色性格疊在上面
    base = eng.CORE + c.get("persona", "") + eng.RED
    try:
        # displayName 跟著角色走：用戶自訂名優先、否則用角色本名。
        # 不傳的話會 fallback 到存檔的陪伴檔案（寧寧），把換角色的名字蓋回去。
        data = {"displayName": (name or char)}
        if mood:
            data["userMood"] = mood
        if topics:
            data["interests"] = topics  # 用戶挑的興趣話題（?topics=）→ 開場/接話的方向
        ctx = server.build_reply_context([], char, data)
        base += server.reply_context_instruction(ctx)
    except Exception:
        pass
    if c.get("type") == "animal" and c.get("style"):
        base += f"（你講話的聲音演技：{c['style']}）"
    base += (
        "（現在是即時語音通話。剛接起電話先用一句溫暖的話打招呼；不確定對方是誰時不要亂猜名字或稱呼；"
        "句子短、口語、一次一兩句、講完停下來等對方回應。）"
    )
    base += (
        "（你有「即時查詢」工具，聊天時可以真的上網查。聊到餐廳店家、景點旅遊（例如日本哪裡好玩、桃園有什麼好吃的）、"
        "電影影劇、天氣預報、時事、活動檔期這類「講錯會誤導人」的具體話題——先安靜查一下再回，"
        "只講查到的真店名、真地點、真資訊；用「我聽很多人推薦…」「那邊最有名的是…」這種像自己去過或朋友推薦的口吻，"
        "自然分享一兩個亮點就好，順便帶一個有意思的小知識或典故更好。不要唸清單、不要報網址、不要像導覽機。"
        "查不到或不確定就老實說「這我不太確定，我幫你查查看」——寧可少講，絕對不可以自己編店名、地址、價格或營業時間。"
        "天氣要講就查當地真的預報再講。"
        "要查東西時，先自然講一句短的過場再查（例如「喔這我知道有個好地方，等我想一下」），"
        "別讓對方對著沒聲音的電話等好幾秒。）"
    )
    nm = (name or "").strip()
    if nm and nm not in ("寧寧", "沐寧", "munea", "Munea"):
        base += (
            f"（很重要：用戶把你的名字改成「{nm}」了。從現在起你就叫「{nm}」，"
            f"打招呼、自我介紹、自稱一律用「{nm}」，絕對不要再說自己叫寧寧。）"
        )
    return base


def live_config(char="寧寧", name=None, mood=None, topics=None):
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    voice = c.get("voice") or "Leda"
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system_instruction(char, name, mood, topics),
        # 即時查詢（Google 搜尋）：聊到店家/景點/影劇/天氣等具體話題先查再答、不編造——跟文字聊天同一套能力
        tools=[types.Tool(google_search=types.GoogleSearch())],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )


def _diag(cid, event, **kv):
    parts = " ".join(f"{k}={v}" for k, v in kv.items())
    print(f"[diag] c{cid} {event} {parts}".rstrip(), flush=True)


_CID = {"n": 0}


async def handle(ws):
    char = "寧寧"
    # 從連線網址讀使用者改過的名字（?name=新名字），讓 AI 知道自己現在叫什麼
    name = None
    mood = None
    topics = None
    try:
        from urllib.parse import urlparse, parse_qs
        path = getattr(getattr(ws, "request", None), "path", None) or getattr(ws, "path", "") or ""
        _q = parse_qs(urlparse(path).query)
        vals = _q.get("name")
        if vals:
            name = vals[0]
        mvals = _q.get("mood")
        if mvals:
            mood = mvals[0]
        # ?char=咪咪：切換角色模板（人格＋聲音都跟 characters.json 走）；沒帶或帶錯就維持寧寧
        cvals = _q.get("char")
        if cvals and cvals[0] in eng.CHARS:
            char = cvals[0]
        # ?topics=旅遊景點,美食餐廳：用戶挑的興趣話題 → 開場方向＋接話素材（最多收 8 個、防亂塞）
        tvals = _q.get("topics")
        if tvals:
            topics = [t.strip() for t in tvals[0].split(",") if t.strip()][:8] or None
    except Exception:
        pass
    _CID["n"] += 1
    cid = _CID["n"]
    t0 = time.monotonic()
    st = {"in": 0, "out": 0, "last_in": None, "await_first": True, "first_mic": False}
    _diag(cid, "connected", name=name or "-", char=char)
    try:
        async with client.aio.live.connect(model=MODEL, config=live_config(char, name, mood, topics)) as session:
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
                # session.receive() 每輪結束就收（SDK 行為）；外層 while 讓「一輪接完再等下一輪」＝多輪對話不斷
                while True:
                    turn_out = 0
                    got = False
                    async for msg in session.receive():
                        got = True
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
                    if not got:
                        break   # receive() 立刻空 = session 真的結束 → 收線

            # 任一邊結束（使用者掛斷 or session 收）就取消另一邊，乾淨收線
            tasks = [asyncio.create_task(from_browser()), asyncio.create_task(from_live())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        _diag(cid, "node.error", err=f"{type(e).__name__}:{str(e)[:80]}")
    finally:
        _diag(cid, "closed", in_bytes=st["in"], out_bytes=st["out"])


async def main():
    # 綁 0.0.0.0＝同一個 Wi-Fi 的手機也連得到（真機測聊聊用）；純本機測試連 127.0.0.1 亦可。
    host = os.environ.get("LIVE_VOICE_HOST", "0.0.0.0")
    # 門牌：雲端主機（Cloud Run）會用 PORT 指定；本機沒設就照舊 8201
    port = int(os.environ.get("PORT") or os.environ.get("MUNEA_VOICE_PORT") or "8201")
    async with websockets.serve(handle, host, port, max_size=None, process_request=process_request):
        print(f"即時語音橋接已啟動：{host}:{port} （網頁＋語音同門，模型 {MODEL}）")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
