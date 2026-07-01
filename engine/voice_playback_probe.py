"""即時語音 · 播放平順度自測（不用喇叭、不用人耳）

原理：連上語音橋、送一句話，記錄每一小塊聲音「幾毫秒到、多長」，
然後在程式裡「模擬播放」——算出：
  1) 聲音是「比即時快還是慢」到（<1x 代表送得比播得慢，一定會斷）
  2) 用不同大小的緩衝墊，會不會發生「播到一半沒聲音」（underrun=斷點）
  3) 要 0 斷點，最小需要多大緩衝墊 → 直接告訴我該把緩衝設多少

跑法（要先開 live_voice_server.py）：python engine/voice_playback_probe.py
"""

import sys
import json
import time
import asyncio

import websockets

URL = "ws://127.0.0.1:8201"
PROMPT = sys.argv[1] if len(sys.argv) > 1 else "寧寧，跟我說說今天適合做什麼，講長一點沒關係"
RATE = 24000
BYTES_PER_SEC = RATE * 2


def simulate(chunks, buffer_s):
    """chunks: [(arrival_s, dur_s)]。回傳 (斷點數, 總靜音秒)。"""
    if not chunks:
        return 0, 0.0
    play_start = chunks[0][0] + buffer_s
    playhead = play_start
    underruns, silence = 0, 0.0
    for arrival, dur in chunks:
        if arrival > playhead + 1e-6:
            underruns += 1
            silence += arrival - playhead
            playhead = arrival
        playhead += dur
    return underruns, silence


async def run():
    ws = await asyncio.wait_for(websockets.connect(URL, max_size=None), timeout=8)
    t_send = time.monotonic()
    await ws.send(json.dumps({"type": "text", "text": PROMPT}))
    chunks = []
    total = 0
    try:
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(msg, (bytes, bytearray)):
                chunks.append((time.monotonic() - t_send, len(msg) / BYTES_PER_SEC))
                total += len(msg)
            elif isinstance(msg, str) and json.loads(msg).get("type") == "turn_complete":
                break
    except asyncio.TimeoutError:
        pass
    finally:
        await ws.close()

    if not chunks:
        print("沒收到聲音——先確認語音橋有開。")
        return
    audio_s = total / BYTES_PER_SEC
    first = chunks[0][0]
    stream_wall = chunks[-1][0] - first
    ratio = (audio_s / stream_wall) if stream_wall > 0 else 99
    maxgap = max((chunks[i][0] - chunks[i - 1][0]) for i in range(1, len(chunks))) if len(chunks) > 1 else 0

    print("即時語音 · 播放平順度自測")
    print(f"  輸入：{PROMPT!r}")
    print("  " + "-" * 46)
    print(f"  小塊數        : {len(chunks)}")
    print(f"  聲音總長      : {audio_s:.1f}s")
    print(f"  首聲延遲      : {first*1000:.0f}ms")
    print(f"  串流耗時      : {stream_wall:.1f}s")
    print(f"  送達速度      : {ratio:.2f}x 即時  ({'夠快、緩衝可解' if ratio>=1.0 else '比即時慢，光靠緩衝救不了、要改送法'})")
    print(f"  最大塊間隔    : {maxgap*1000:.0f}ms")
    print("  " + "-" * 46)
    print("  不同緩衝墊的斷點數：")
    best = None
    for b in [0, 0.05, 0.1, 0.18, 0.3, 0.5, 0.8, 1.2]:
        u, sil = simulate(chunks, b)
        flag = "✅" if u == 0 else "⚠️"
        print(f"    緩衝 {int(b*1000):>4}ms → 斷點 {u:>2} 次，靜音 {sil*1000:>4.0f}ms {flag}")
        if u == 0 and best is None:
            best = b
    print("  " + "-" * 46)
    if best is not None:
        print(f"  結論：緩衝墊設 {int(best*1000)}ms 就 0 斷點、播放會順。")
    else:
        print(f"  結論：送達比即時慢（{ratio:.2f}x），要改『送法』（例如整段收齊再播，或要求更快模型）。")


if __name__ == "__main__":
    asyncio.run(run())
