#!/usr/bin/env python3
"""Voice-only barge-in probe for Munea's Gemini Live bridge."""

import argparse
import asyncio
import json

import websockets

import localization
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


async def _pcm_for(text):
    pcm, source_rate = await asyncio.to_thread(_synthetic_input, text)
    pcm = _resample_pcm16(pcm, source_rate)
    duration = len(pcm) / (INPUT_RATE * 2)
    if duration > 12:
        raise RuntimeError(f"probe TTS input is unexpectedly long: {duration:.1f}s")
    return pcm


async def run(args):
    # Generate sequentially: the prototype TTS fallback is not concurrency-safe.
    first_pcm = await _pcm_for(args.first_phrase)
    second_pcm = await _pcm_for(args.second_phrase)
    first_audio = 0
    leaked_audio = 0
    second_audio = 0
    acked = False
    interrupted = False
    second_heard = False
    completed = False
    second_sender = None
    second_caption = ""

    async with websockets.connect(_with_local_gate(args.url), max_size=None, open_timeout=10) as ws:
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=20)
            if isinstance(message, str) and json.loads(message).get("type") == "ready":
                break

        await _stream_input(ws, first_pcm)
        deadline = asyncio.get_running_loop().time() + args.timeout
        try:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=10)
                except asyncio.TimeoutError:
                    continue
                if isinstance(message, (bytes, bytearray)):
                    if second_heard:
                        second_audio += len(message)
                    elif acked:
                        leaked_audio += len(message)
                    else:
                        first_audio += len(message)
                        if first_audio >= round(OUTPUT_RATE * 2 * 0.3) and second_sender is None:
                            await ws.send(json.dumps({"type": "barge_in"}))
                            second_sender = asyncio.create_task(_stream_input(ws, second_pcm))
                    continue

                event = json.loads(message)
                event_type = event.get("type")
                if event_type == "barge_in_ack":
                    acked = True
                elif event_type == "interrupted":
                    interrupted = True
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

    checks = {
        "AI 說話中收到插話": first_audio > 0,
        "App 插話握手": acked,
        "Gemini 中斷舊回覆": interrupted,
        "ASR 聽到新話題": second_heard,
        "插話後產生新回覆": second_audio >= OUTPUT_RATE,
        "插話回合完成": completed,
        "舊音訊快速停止": leaked_audio <= OUTPUT_RATE * 2,
    }
    print("Munea voice-only barge-in probe")
    for label, passed in checks.items():
        print(("PASS" if passed else "FAIL") + " " + label)
    print(
        f"first_audio_bytes={first_audio} leaked_audio_bytes={leaked_audio} "
        f"second_audio_bytes={second_audio}"
    )
    if args.show_transcript:
        print("ASR second transcript=" + localization.canonicalize_transcription(second_caption, "zh-TW"))
    return 0 if all(checks.values()) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8291?topics=園藝花草,懷舊老歌&user=爸爸&fam=4")
    parser.add_argument("--first-phrase", default=FIRST_PHRASE)
    parser.add_argument("--second-phrase", default=SECOND_PHRASE)
    parser.add_argument("--expect", default=SECOND_EXPECTED)
    parser.add_argument("--show-transcript", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
