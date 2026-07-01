"""即時語音 · 逐節點診斷測試

連上正在跑的語音橋接（ws://127.0.0.1:8201），送一句話，量出整條路每一段的時間與資料量，
一眼看出問題卡在哪個節點。跑法（要先開著 live_voice_server.py）：
    python engine/voice_node_test.py

節點：① 連線 ② 送出 ③ 首次回聲(最關鍵的「反應快不快」) ④ 下行語音量 ⑤ 字幕 ⑥ 整段完成
"""

import sys
import json
import time
import asyncio

import websockets

URL = "ws://127.0.0.1:8201"
PROMPT = sys.argv[1] if len(sys.argv) > 1 else "你好，你是誰？"


def verdict(ms, good, slow):
    return "OK" if ms <= good else ("慢" if ms <= slow else "太慢")


async def run():
    t0 = time.monotonic()
    try:
        ws = await asyncio.wait_for(websockets.connect(URL, max_size=None), timeout=8)
    except Exception as e:
        print(f"① 連線      : 失敗 —— {type(e).__name__}: {e}")
        print("   （語音服務沒開？先跑 engine/live_voice_server.py）")
        return
    connect_ms = round((time.monotonic() - t0) * 1000)

    t_send = time.monotonic()
    await ws.send(json.dumps({"type": "text", "text": PROMPT}))

    first_ms = None
    audio = 0
    caption = ""
    server_first = None
    done_ms = None
    try:
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(msg, (bytes, bytearray)):
                if first_ms is None:
                    first_ms = round((time.monotonic() - t_send) * 1000)
                audio += len(msg)
            else:
                o = json.loads(msg)
                if o.get("type") == "caption" and o.get("who") == "nening":
                    caption += o.get("text", "")
                elif o.get("type") == "diag" and o.get("firstAudioMs") is not None:
                    server_first = o["firstAudioMs"]
                elif o.get("type") == "turn_complete":
                    done_ms = round((time.monotonic() - t_send) * 1000)
                    break
    except asyncio.TimeoutError:
        pass
    finally:
        await ws.close()

    audio_ms = round(audio / (24000 * 2) * 1000)
    print("即時語音 · 逐節點診斷")
    print(f"  輸入：{PROMPT!r}")
    print("  " + "-" * 42)
    print(f"  ① 連線        : OK  {connect_ms}ms")
    print(f"  ② 送出文字    : OK")
    if first_ms is None:
        print(f"  ③ 首次回聲    : 太慢/沒回 —— 30 秒沒收到語音")
    else:
        print(f"  ③ 首次回聲    : {verdict(first_ms,2000,4000)}  {first_ms}ms  (好<2000 / 慢>4000)"
              + (f"  [伺服器量:{server_first}ms]" if server_first is not None else ""))
    print(f"  ④ 下行語音    : {audio} bytes ≈ {audio_ms/1000:.1f}s 語音")
    print(f"  ⑤ 字幕        : {caption!r}")
    print(f"  ⑥ 整段完成    : {done_ms}ms" if done_ms else "  ⑥ 整段完成    : 未收到完成訊號")
    print("  " + "-" * 42)
    slow = (first_ms or 9999) > 4000
    print("  判讀：" + ("反應偏慢，重點查 ③（Live 回應）或網路" if slow else "整條路健康，反應在可用範圍"))


if __name__ == "__main__":
    asyncio.run(run())
