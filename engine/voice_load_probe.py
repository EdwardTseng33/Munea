#!/usr/bin/env python3
"""併發語音壓測探針（測試機專用 · 2026-07-25 · 卡西法）

只量測、不改服務設定，也不碰正式機。同時開 N 條 WebSocket 連到
munea-voice-staging，用 {"type":"greet"} 觸發寧寧開口、turn_complete 後
再用純文字請她接著聊，藉此在整個測試窗口內維持「伺服器→瀏覽器」方向
的連續語音串流，量測音訊 chunk 到達間隔（gap）的分布——用來判斷
1 vCPU / concurrency 20 在多通同時講話時，是不是音訊抖動/斷續的元兇。

刻意不送真人聲音輸入（省合成成本、也不影響量測重點）：這裡要測的是
伺服器事件迴圈把 Gemini 吐回來的音訊 bytes 轉送給每個連線的節奏是否
被其他併發連線的 CPU 工作（ASR/guardian 掃描/JSON 編解碼等）卡住，
不是語音辨識準不準。

用法：
    python voice_load_probe.py --url wss://munea-voice-staging-....run.app \
        --key mnk_xxx --rounds 1,4,8,12 --duration 60 --gap 30 \
        --out-dir <folder>
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from urllib.parse import quote

import websockets

DEFAULT_URL = "wss://munea-voice-staging-491603544409.asia-east1.run.app"

KEEP_TALKING_PROMPTS = [
    "請你自然地繼續聊,分享一件你今天想到的小事,不用問我問題,慢慢說就好。",
    "接著再多聊一點,可以講講你觀察到的天氣或生活小事,語氣輕鬆,不用等我回答。",
    "再繼續說一小段,像平常聊天一樣,不用刻意收尾,講久一點也沒關係。",
    "好,繼續講下去,換個話題也可以,輕鬆聊就好。",
]


def _pct(data, p):
    if not data:
        return None
    data = sorted(data)
    k = (len(data) - 1) * p
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


async def run_one_call(call_id, url, key, duration_s, results, stagger_max):
    record = {
        "call_id": call_id,
        "connected_at": None,
        "ready_at": None,
        "greet_sent_at": None,
        "first_audio_at": None,
        "chunks": [],   # (monotonic_ts, nbytes, turn_idx)
        "turns": [],    # (turn_idx, start_ts, end_ts, total_bytes)
        "errors": [],
        "closed_at": None,
    }
    results[call_id] = record

    if stagger_max > 0:
        await asyncio.sleep(random.uniform(0, stagger_max))

    sep = "&" if "?" in url else "?"
    full_url = (
        f"{url}{sep}key={quote(key)}&topics=%E5%A4%A9%E6%B0%A3,%E5%AE%B6%E5%B8%B8,%E5%9C%92%E8%97%9D"
        f"&user={quote('長輩' + call_id)}&fam=80&loadtest={quote(call_id)}"
    )

    turn_idx = -1
    turn_start_ts = None
    turn_bytes = 0
    prompt_i = 0

    try:
        async with websockets.connect(full_url, max_size=None, open_timeout=15) as ws:
            record["connected_at"] = time.monotonic()
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=20)
                if isinstance(msg, str):
                    evt = json.loads(msg)
                    if evt.get("type") == "ready":
                        record["ready_at"] = time.monotonic()
                        break
                    if evt.get("type") == "error":
                        record["errors"].append({"t": time.monotonic(), "err": f"server_error:{evt}"})

            deadline = record["ready_at"] + duration_s
            await ws.send(json.dumps({"type": "greet"}))
            record["greet_sent_at"] = time.monotonic()

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 15) if remaining > 0 else 0.1)
                except asyncio.TimeoutError:
                    record["errors"].append({"t": time.monotonic(), "err": "recv_timeout"})
                    break
                now = time.monotonic()
                if isinstance(msg, (bytes, bytearray)):
                    n = len(msg)
                    if turn_idx == -1:
                        turn_idx = len(record["turns"])
                        turn_start_ts = now
                        turn_bytes = 0
                    if record["first_audio_at"] is None:
                        record["first_audio_at"] = now
                    turn_bytes += n
                    record["chunks"].append((now, n, turn_idx))
                    continue
                try:
                    evt = json.loads(msg)
                except Exception:
                    continue
                t = evt.get("type")
                if t == "turn_complete":
                    if evt.get("phase") == "greet_input_ready":
                        continue
                    if turn_idx != -1:
                        record["turns"].append((turn_idx, turn_start_ts, now, turn_bytes))
                        turn_idx = -1
                        turn_bytes = 0
                    if time.monotonic() < deadline:
                        prompt = KEEP_TALKING_PROMPTS[prompt_i % len(KEEP_TALKING_PROMPTS)]
                        prompt_i += 1
                        try:
                            await ws.send(json.dumps({"type": "text", "text": prompt}))
                        except Exception as exc:
                            record["errors"].append({"t": time.monotonic(), "err": f"send_fail:{exc}"})
                            break
                elif t == "interrupted":
                    record["errors"].append({"t": now, "err": "interrupted"})
            if turn_idx != -1:
                record["turns"].append((turn_idx, turn_start_ts, time.monotonic(), turn_bytes))
            record["closed_at"] = time.monotonic()
    except Exception as exc:
        record["errors"].append({"t": time.monotonic(), "err": f"conn_fail:{type(exc).__name__}:{exc}"})


def analyze_round(label, concurrency, duration_s, results):
    all_gaps = []
    mid_gaps = []       # 講話「中間」的音訊到達間隔(排除每個完成 turn 的最後一個 gap)
    turn_tail_gaps = []  # 每個完成 turn 的「最後一段內容→turn_complete 收尾包」等待時間
    per_call = {}
    first_audio_latencies = []
    conn_failures = 0
    total_chunks = 0
    total_bytes = 0
    turn_counts = []

    for cid, r in results.items():
        chunks = sorted(r["chunks"], key=lambda c: c[0])
        if not chunks and r["errors"]:
            conn_failures += 1
        total_chunks += len(chunks)
        total_bytes += sum(c[1] for c in chunks)
        turn_counts.append(len(r["turns"]))
        if r.get("greet_sent_at") and r.get("first_audio_at"):
            first_audio_latencies.append(r["first_audio_at"] - r["greet_sent_at"])

        # 每個「自然講完」的 turn,最後一個 gap 是「等伺服器送 turn_complete
        # / 句尾靜音收尾包」的等待時間,不是講話中間真的斷了——這段要跟
        # 「講話中間的音訊到達間隔」分開看,不然會被這個尾段等待污染掉
        # 併發抖動的判讀(2026-07-25 baseline 單通已觀測到 3.2s 這種尾段
        # 等待,若不排除會誤判成嚴重併發問題)。
        completed_turns = {t[0] for t in r["turns"]}
        turn_chunk_lists = {}
        for ts, n, turn in chunks:
            turn_chunk_lists.setdefault(turn, []).append(ts)

        prev_ts = None
        prev_turn = None
        call_max_gap = 0.0
        call_gaps = []
        call_mid_gaps = []
        for ts, n, turn in chunks:
            if prev_ts is not None and prev_turn == turn:
                gap = ts - prev_ts
                all_gaps.append(gap)
                call_gaps.append(gap)
                call_max_gap = max(call_max_gap, gap)
                is_last_gap_of_completed_turn = (
                    turn in completed_turns and ts == turn_chunk_lists[turn][-1]
                )
                if not is_last_gap_of_completed_turn:
                    mid_gaps.append(gap)
                    call_mid_gaps.append(gap)
                else:
                    turn_tail_gaps.append(gap)
            prev_ts = ts
            prev_turn = turn
        per_call[cid] = {
            "chunks": len(chunks),
            "bytes": sum(c[1] for c in chunks),
            "turns": len(r["turns"]),
            "max_gap_ms": round(call_max_gap * 1000, 1),
            "mid_gap_p95_ms": round(_pct(call_mid_gaps, 0.95) * 1000, 1) if call_mid_gaps else None,
            "mid_gap_max_ms": round(max(call_mid_gaps) * 1000, 1) if call_mid_gaps else None,
            "errors": r["errors"],
            "first_audio_latency_ms": (
                round((r["first_audio_at"] - r["greet_sent_at"]) * 1000, 1)
                if r.get("greet_sent_at") and r.get("first_audio_at") else None
            ),
        }

    # 「講話中間」的抖動判讀(排除 turn 收尾等待) —— 這才是併發是否卡音訊的主指標
    underrun_300 = sum(1 for g in mid_gaps if g > 0.3)
    underrun_500 = sum(1 for g in mid_gaps if g > 0.5)
    underrun_1000 = sum(1 for g in mid_gaps if g > 1.0)

    return {
        "label": label,
        "concurrency": concurrency,
        "duration_s": duration_s,
        "total_calls": len(results),
        "conn_failures": conn_failures,
        "total_chunks": total_chunks,
        "total_audio_bytes": total_bytes,
        "total_turns": sum(turn_counts),
        "gap_count": len(all_gaps),
        "gap_mean_ms": round(statistics.mean(all_gaps) * 1000, 1) if all_gaps else None,
        "gap_p50_ms": round(_pct(all_gaps, 0.50) * 1000, 1) if all_gaps else None,
        "gap_p95_ms": round(_pct(all_gaps, 0.95) * 1000, 1) if all_gaps else None,
        "gap_p99_ms": round(_pct(all_gaps, 0.99) * 1000, 1) if all_gaps else None,
        "gap_max_ms": round(max(all_gaps) * 1000, 1) if all_gaps else None,
        # mid_* = 排除每個完成 turn 最後一個 gap(那是等 turn_complete 收尾包,
        # 不是講話中斷)——這組才是回答「1 vCPU 併發下音訊會不會斷斷續續」的主指標
        "mid_gap_count": len(mid_gaps),
        "mid_gap_mean_ms": round(statistics.mean(mid_gaps) * 1000, 1) if mid_gaps else None,
        "mid_gap_p50_ms": round(_pct(mid_gaps, 0.50) * 1000, 1) if mid_gaps else None,
        "mid_gap_p95_ms": round(_pct(mid_gaps, 0.95) * 1000, 1) if mid_gaps else None,
        "mid_gap_p99_ms": round(_pct(mid_gaps, 0.99) * 1000, 1) if mid_gaps else None,
        "mid_gap_max_ms": round(max(mid_gaps) * 1000, 1) if mid_gaps else None,
        "underrun_gt300ms": underrun_300,
        "underrun_gt500ms": underrun_500,
        "underrun_gt1000ms": underrun_1000,
        "turn_tail_gap_count": len(turn_tail_gaps),
        "turn_tail_gap_mean_ms": round(statistics.mean(turn_tail_gaps) * 1000, 1) if turn_tail_gaps else None,
        "turn_tail_gap_max_ms": round(max(turn_tail_gaps) * 1000, 1) if turn_tail_gaps else None,
        "first_audio_latency_mean_ms": (
            round(statistics.mean(first_audio_latencies) * 1000, 1) if first_audio_latencies else None
        ),
        "first_audio_latency_p95_ms": (
            round(_pct(first_audio_latencies, 0.95) * 1000, 1) if first_audio_latencies else None
        ),
        "per_call": per_call,
    }


async def run_round(label, url, key, concurrency, duration_s, out_dir, stagger_max):
    results = {}
    tasks = [
        asyncio.create_task(
            run_one_call(f"{label}-c{i:02d}", url, key, duration_s, results, stagger_max)
        )
        for i in range(concurrency)
    ]
    wall_start = time.time()
    await asyncio.gather(*tasks)
    wall_end = time.time()
    summary = analyze_round(label, concurrency, duration_s, results)
    summary["wall_start_epoch"] = wall_start
    summary["wall_end_epoch"] = wall_end
    summary["wall_start_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(wall_start))
    summary["wall_end_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(wall_end))

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "raw": results}, f, ensure_ascii=False, indent=2, default=str)

    print(f"[{label}] concurrency={concurrency} calls={summary['total_calls']} "
          f"fail={summary['conn_failures']} chunks={summary['total_chunks']} "
          f"mid_gap_p50={summary['mid_gap_p50_ms']}ms mid_gap_p95={summary['mid_gap_p95_ms']}ms "
          f"mid_gap_max={summary['mid_gap_max_ms']}ms underrun300={summary['underrun_gt300ms']} "
          f"turn_tail_mean={summary['turn_tail_gap_mean_ms']}ms "
          f"first_audio_p95={summary['first_audio_latency_p95_ms']}ms")
    return summary


async def main_async(args):
    key = args.key or os.environ.get("MUNEA_APP_KEY", "").strip()
    if not key:
        raise SystemExit("需要 --key 或環境變數 MUNEA_APP_KEY")

    rounds = [int(x) for x in args.rounds.split(",") if x.strip()]
    all_summaries = []
    for i, concurrency in enumerate(rounds):
        label = f"round-{concurrency:02d}"
        summary = await run_round(label, args.url, key, concurrency, args.duration, args.out_dir, args.stagger)
        all_summaries.append(summary)
        if i < len(rounds) - 1 and args.gap > 0:
            print(f"...冷卻 {args.gap} 秒再進下一階...")
            await asyncio.sleep(args.gap)

    combined_path = os.path.join(args.out_dir, "combined-summary.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, ensure_ascii=False, indent=2)
    print(f"合併摘要已存: {combined_path}")


def main():
    parser = argparse.ArgumentParser(description="Munea voice bridge 併發壓測探針（staging 專用）")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--key", default="", help="MUNEA_APP_KEY（薄門通行碼）；留空則讀環境變數")
    parser.add_argument("--rounds", default="1,4,8,12", help="逗號分隔的併發階梯,例如 1,4,8,12")
    parser.add_argument("--duration", type=float, default=60.0, help="每階每通秒數")
    parser.add_argument("--gap", type=float, default=30.0, help="階與階之間冷卻秒數")
    parser.add_argument("--stagger", type=float, default=1.5, help="同階內每通連線的隨機錯開秒數上限")
    parser.add_argument("--out-dir", required=True, help="原始數據與摘要輸出資料夾")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
