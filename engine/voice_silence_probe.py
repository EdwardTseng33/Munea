#!/usr/bin/env python3
"""Low-level room-noise probe for false ASR/VAD activations."""

import argparse
import array
import asyncio
import json
import math
import os
import random
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets

INPUT_RATE = 16000


def _with_local_gate(url):
    gate = os.environ.get("MUNEA_APP_KEY", "").strip()
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    if gate and "key" not in query and "token" not in query:
        query["key"] = gate
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _room_tone_frame(index, amplitude):
    rng = random.Random(index)
    samples = array.array("h")
    frame_samples = int(INPUT_RATE * 0.02)
    for offset in range(frame_samples):
        hum = math.sin(2 * math.pi * 60 * (index * frame_samples + offset) / INPUT_RATE)
        samples.append(round(hum * amplitude * 0.35 + rng.uniform(-amplitude, amplitude)))
    return samples.tobytes()


async def run(args):
    captions = 0
    output_bytes = 0
    unexpected_turns = 0
    async with websockets.connect(_with_local_gate(args.url), max_size=None, open_timeout=10) as ws:
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=20)
            if isinstance(message, str) and json.loads(message).get("type") == "ready":
                break

        frames = math.ceil(args.seconds / 0.02)
        for index in range(frames):
            await ws.send(_room_tone_frame(index, args.amplitude))
            await asyncio.sleep(0.02)

        deadline = asyncio.get_running_loop().time() + args.settle
        while asyncio.get_running_loop().time() < deadline:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            if isinstance(message, (bytes, bytearray)):
                output_bytes += len(message)
                continue
            event = json.loads(message)
            if event.get("type") == "caption" and event.get("who") == "user":
                captions += 1
            elif event.get("type") == "turn_complete":
                unexpected_turns += 1

    checks = {
        "底噪未觸發 ASR": captions == 0,
        "底噪未觸發 AI 回覆": output_bytes == 0,
        "底噪未建立假回合": unexpected_turns == 0,
    }
    print("Munea voice-only room-noise probe")
    for label, passed in checks.items():
        print(("PASS" if passed else "FAIL") + " " + label)
    print(f"seconds={args.seconds:g} amplitude={args.amplitude} captions={captions} output_bytes={output_bytes}")
    return 0 if all(checks.values()) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8291?user=爸爸&fam=4")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--settle", type=float, default=2.5)
    parser.add_argument("--amplitude", type=int, default=150)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
