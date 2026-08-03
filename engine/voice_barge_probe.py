#!/usr/bin/env python3
"""Voice-only barge-in acceptance probe for Munea's Gemini Live bridge.

The default path mirrors the App's two-phase protocol:
``barge_in_start`` -> retained PCM evidence -> ``barge_in`` commit. It can
also exercise the legacy single-message path for compatibility checks.
"""

import argparse
import asyncio
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import websockets

import localization
from voice_echo_guard import frame_rms, normalized_rms_to_pcm16, sustained_voice_evidence
from voice_s2s_probe import (
    INPUT_RATE,
    OUTPUT_RATE,
    _resample_pcm16,
    _stream_input,
    _synthetic_input,
    _with_local_gate,
)


FIRST_PHRASE = "我最近想聽一段關於清晨散步的故事，慢慢說。"
SECOND_PHRASE = "等等，我想改聊懷舊老歌。"
SECOND_EXPECTED = "懷舊老歌"
FRAME_MS = 20.0
FRAME_BYTES = int(INPUT_RATE * FRAME_MS / 1000.0) * 2


async def _pcm_for(text):
    pcm, source_rate = await asyncio.to_thread(_synthetic_input, text)
    pcm = _resample_pcm16(pcm, source_rate)
    duration = len(pcm) / (INPUT_RATE * 2)
    if duration > 12:
        raise RuntimeError(f"probe TTS input is unexpectedly long: {duration:.1f}s")
    return pcm


def _barge_frames(pcm, threshold, sustain_ms, pre_roll_ms):
    """Select retained evidence beginning just before the first sustained voice."""
    frames = [pcm[offset:offset + FRAME_BYTES] for offset in range(0, len(pcm), FRAME_BYTES)]
    if not frames:
        raise RuntimeError("barge-in PCM is empty")
    levels = [(frame_rms(frame), len(frame) / float(INPUT_RATE * 2) * 1000.0) for frame in frames]
    accepted, evidence_ms, onset = sustained_voice_evidence(
        levels, normalized_rms_to_pcm16(threshold), sustain_ms,
    )
    if not accepted:
        peak = max((rms for rms, _ in levels), default=0.0) / 32768.0
        raise RuntimeError(
            f"probe input never crosses its own sustain gate: peak={peak:.4f}, "
            f"threshold={threshold:.4f}, evidence_ms={evidence_ms:.0f}"
        )
    margin_frames = max(1, math.ceil(max(0.0, pre_roll_ms - sustain_ms) / FRAME_MS))
    start = max(0, onset - margin_frames)
    required_frames = math.ceil(max(120.0, sustain_ms) / FRAME_MS) + 2
    evidence_end = min(len(frames), onset + required_frames)
    selected = frames[start:]
    evidence_count = max(1, evidence_end - start)
    peak = max((rms for rms, _ in levels[start:evidence_end]), default=0.0) / 32768.0
    return selected[:evidence_count], selected[evidence_count:], peak


async def _stream_two_phase_barge(ws, pcm, threshold, sustain_ms, pre_roll_ms,
                                  frame_sleep=0.02, tail_seconds=1.1):
    evidence, remainder, peak = _barge_frames(pcm, threshold, sustain_ms, pre_roll_ms)
    payload = {
        "rms": round(peak, 4),
        "threshold": round(float(threshold), 4),
        "sustain_ms": round(float(sustain_ms)),
        "evidence_frames": len(evidence),
    }
    await ws.send(json.dumps({"type": "barge_in_start", **payload}))
    for frame in evidence:
        await ws.send(frame)
    await ws.send(json.dumps({"type": "barge_in", **payload}))
    for frame in remainder:
        await ws.send(frame)
        if frame_sleep:
            await asyncio.sleep(frame_sleep)
    silent_frame = b"\x00" * FRAME_BYTES
    for _ in range(math.ceil(max(0.0, tail_seconds) / (FRAME_MS / 1000.0))):
        await ws.send(silent_frame)
        if frame_sleep:
            await asyncio.sleep(frame_sleep)
    return payload


async def _run_once(args, first_pcm, second_pcm, run_index):
    first_audio = 0
    leaked_audio = 0
    second_audio = 0
    acked = False
    ack_accepted = None
    ack_reason = ""
    ack_evidence_ms = 0
    interrupted = False
    second_heard = False
    completed = False
    second_sender = None
    second_caption = ""
    barge_started_at = None
    ack_at = None
    interrupted_at = None
    second_audio_at = None
    loop = asyncio.get_running_loop()

    async with websockets.connect(_with_local_gate(args.url), max_size=None, open_timeout=10) as ws:
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=20)
            if isinstance(message, str) and json.loads(message).get("type") == "ready":
                break

        await _stream_input(ws, first_pcm)
        deadline = loop.time() + args.timeout
        try:
            while loop.time() < deadline:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=10)
                except asyncio.TimeoutError:
                    continue
                if isinstance(message, (bytes, bytearray)):
                    if second_heard:
                        if second_audio_at is None:
                            second_audio_at = loop.time()
                        second_audio += len(message)
                    elif acked:
                        leaked_audio += len(message)
                    else:
                        first_audio += len(message)
                        if first_audio >= round(OUTPUT_RATE * 2 * 0.3) and second_sender is None:
                            barge_started_at = loop.time()
                            if args.protocol == "two-phase":
                                second_sender = asyncio.create_task(_stream_two_phase_barge(
                                    ws, second_pcm, args.threshold, args.sustain_ms, args.pre_roll_ms,
                                ))
                            else:
                                await ws.send(json.dumps({"type": "barge_in"}))
                                second_sender = asyncio.create_task(_stream_input(ws, second_pcm))
                    continue

                event = json.loads(message)
                event_type = event.get("type")
                if event_type == "barge_in_ack":
                    acked = True
                    ack_at = loop.time()
                    ack_accepted = event.get("accepted")
                    ack_reason = str(event.get("reason") or "")
                    ack_evidence_ms = int(event.get("evidence_ms") or 0)
                elif event_type == "interrupted":
                    interrupted = True
                    interrupted_at = loop.time()
                elif event_type == "caption" and event.get("who") == "user" and second_sender is not None:
                    second_caption += event.get("text") or ""
                    transcript = localization.canonicalize_transcription(second_caption, "zh-TW")
                    second_heard = args.expect in transcript
                elif event_type == "turn_complete" and second_heard and second_audio >= OUTPUT_RATE:
                    completed = True
                    break
        finally:
            if second_sender is not None:
                await second_sender

    explicit_accept = ack_accepted is True if args.protocol == "two-phase" else ack_accepted is not False
    checks = {
        "assistant_audio_before_barge": first_audio > 0,
        "barge_ack": acked,
        "barge_explicitly_accepted": explicit_accept,
        "model_interrupted": interrupted,
        "new_topic_transcribed": second_heard,
        "new_response_audio": second_audio >= OUTPUT_RATE,
        "barge_turn_completed": completed,
        "stale_audio_stopped": leaked_audio <= OUTPUT_RATE * 2,
    }
    metric = lambda end: round((end - barge_started_at) * 1000) if end and barge_started_at else None
    transcript = localization.canonicalize_transcription(second_caption, "zh-TW")
    return {
        "run": run_index,
        "ok": all(checks.values()),
        "protocol": args.protocol,
        "checks": checks,
        "metrics": {
            "ack_ms": metric(ack_at),
            "interrupted_ms": metric(interrupted_at),
            "new_audio_ms": metric(second_audio_at),
            "ack_evidence_ms": ack_evidence_ms,
            "first_audio_bytes": first_audio,
            "leaked_audio_bytes": leaked_audio,
            "second_audio_bytes": second_audio,
        },
        "ack": {"accepted": ack_accepted, "reason": ack_reason},
        "transcript": transcript,
    }


async def run(args):
    # Generate sequentially: the prototype TTS fallback is not concurrency-safe.
    first_pcm = await _pcm_for(args.first_phrase)
    second_pcm = await _pcm_for(args.second_phrase)
    results = []
    for index in range(1, args.runs + 1):
        result = await _run_once(args, first_pcm, second_pcm, index)
        results.append(result)
        status = "PASS" if result["ok"] else "FAIL"
        metrics = result["metrics"]
        print(
            f"{status} run={index} protocol={args.protocol} ack={metrics['ack_ms']}ms "
            f"interrupted={metrics['interrupted_ms']}ms new_audio={metrics['new_audio_ms']}ms "
            f"evidence={metrics['ack_evidence_ms']}ms leaked={metrics['leaked_audio_bytes']}B"
        )
        if args.show_transcript:
            print("ASR second transcript=" + result["transcript"])

    report = {
        "schema": "munea.voice-barge-acceptance.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "url": args.url.split("?")[0],
        "protocol": args.protocol,
        "threshold": args.threshold,
        "sustain_ms": args.sustain_ms,
        "pre_roll_ms": args.pre_roll_ms,
        "runs": results,
        "summary": {
            "passed": sum(1 for result in results if result["ok"]),
            "total": len(results),
        },
    }
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report={report_path}")
    return 0 if all(result["ok"] for result in results) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8291?topics=園藝花草,懷舊老歌&user=爸爸&fam=4")
    parser.add_argument("--first-phrase", default=FIRST_PHRASE)
    parser.add_argument("--second-phrase", default=SECOND_PHRASE)
    parser.add_argument("--expect", default=SECOND_EXPECTED)
    parser.add_argument("--protocol", choices=("two-phase", "legacy"), default="two-phase")
    parser.add_argument("--threshold", type=float, default=0.04)
    parser.add_argument("--sustain-ms", type=float, default=150.0)
    parser.add_argument("--pre-roll-ms", type=float, default=400.0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--report")
    parser.add_argument("--show-transcript", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 30:
        parser.error("--runs must be between 1 and 30")
    if not 0.028 <= args.threshold <= 0.07:
        parser.error("--threshold must be between 0.028 and 0.07")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
