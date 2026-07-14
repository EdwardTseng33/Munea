#!/usr/bin/env python3
"""Voice-only regression probe for Munea's Gemini Live bridge.

The bridge receives PCM audio only. With no --wav, this script generates a
temporary Mandarin utterance with the Mac's Taiwan voice, resamples it to 16
kHz, and streams it at microphone speed. It never uses the bridge's text test
message.
"""

import argparse
import asyncio
import array
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import wave
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets

import localization


DEFAULT_PHRASE = "我想聊園藝，明天下午要回診。"
DEFAULT_EXPECTED = ("園藝", "回診")
INPUT_RATE = 16000
OUTPUT_RATE = 24000


def _read_wav(source):
    with wave.open(source, "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("probe input must be mono PCM16 WAV")
        return wav.readframes(wav.getnframes()), wav.getframerate()


def _synthetic_input(phrase):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        errors = []
        for model in ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=phrase,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            language_code="cmn-TW",
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Leda")
                            ),
                        ),
                    ),
                )
                pcm = response.candidates[0].content.parts[0].inline_data.data
                if pcm:
                    return pcm, 24000
            except Exception as exc:
                errors.append(f"{model}:{type(exc).__name__}")
        raise RuntimeError("probe TTS failed: " + ", ".join(errors))

    if platform.system() == "Darwin" and shutil.which("say") and shutil.which("afconvert"):
        with tempfile.TemporaryDirectory(prefix="munea-voice-probe-") as temp_dir:
            aiff_path = os.path.join(temp_dir, "input.aiff")
            wav_path = os.path.join(temp_dir, "input.wav")
            subprocess.run(
                ["say", "-v", "Meijia", "-o", aiff_path, phrase],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    "afconvert", aiff_path, "-o", wav_path,
                    "-f", "WAVE", "-d", "LEI16@16000", "-c", "1",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            pcm, sample_rate = _read_wav(wav_path)
            if not pcm:
                raise RuntimeError("macOS say produced an empty probe file")
            return pcm, sample_rate

    raise RuntimeError("probe input needs GEMINI_API_KEY, --wav, or macOS say")


def _resample_pcm16(pcm, source_rate, target_rate=INPUT_RATE):
    if source_rate == target_rate:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    target_count = max(1, round(len(samples) * target_rate / source_rate))
    output = array.array("h")
    for index in range(target_count):
        position = index * source_rate / target_rate
        left = min(len(samples) - 1, int(position))
        right = min(len(samples) - 1, left + 1)
        fraction = position - left
        output.append(round(samples[left] * (1 - fraction) + samples[right] * fraction))
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


def _with_local_gate(url):
    gate = os.environ.get("MUNEA_APP_KEY", "").strip()
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    if gate and "key" not in query and "token" not in query:
        query["key"] = gate
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _trailing_silence_ms(pcm):
    samples = memoryview(pcm).cast("h") if pcm else []
    silent = 0
    for sample in reversed(samples):
        if abs(sample) > 1:
            break
        silent += 1
    return round(silent / OUTPUT_RATE * 1000)


async def _stream_input(ws, pcm):
    frame_bytes = int(INPUT_RATE * 0.02) * 2
    for offset in range(0, len(pcm), frame_bytes):
        await ws.send(pcm[offset:offset + frame_bytes])
        await asyncio.sleep(0.02)
    for _ in range(math.ceil(1.1 / 0.02)):
        await ws.send(b"\x00" * frame_bytes)
        await asyncio.sleep(0.02)


async def run(args):
    if args.wav:
        pcm, source_rate = _read_wav(args.wav)
    else:
        pcm, source_rate = await asyncio.to_thread(_synthetic_input, args.phrase)
    pcm = _resample_pcm16(pcm, source_rate)
    url = _with_local_gate(args.url)
    user_caption = ""
    assistant_caption = ""
    output = bytearray()
    completed = False

    async with websockets.connect(url, max_size=None, open_timeout=10) as ws:
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=20)
            if not isinstance(message, str):
                continue
            event = json.loads(message)
            if event.get("type") == "ready":
                break

        sender = asyncio.create_task(_stream_input(ws, pcm))
        try:
            while True:
                message = await asyncio.wait_for(ws.recv(), timeout=args.timeout)
                if isinstance(message, (bytes, bytearray)):
                    output.extend(message)
                    continue
                event = json.loads(message)
                if event.get("type") == "caption" and event.get("who") == "user":
                    user_caption += event.get("text") or ""
                elif event.get("type") == "caption" and event.get("who") == "nening":
                    assistant_caption += event.get("text") or ""
                elif event.get("type") == "turn_complete":
                    completed = True
                    break
        finally:
            await sender

    canonical_asr = localization.canonicalize_transcription(user_caption, "zh-TW")
    compact_asr = "".join(canonical_asr.split())
    expected = tuple(args.expect or DEFAULT_EXPECTED)
    recognized = [term for term in expected if term in compact_asr]
    checks = {
        "ASR 關鍵詞": len(recognized) == len(expected),
        "S2S 有回語音": len(output) > OUTPUT_RATE,
        "回合有完成": completed,
        "輸出未偵測到台語": not localization.looks_like_taiwanese_hokkien(assistant_caption),
        "句尾靜音保護": _trailing_silence_ms(output) >= 170,
    }
    print("Munea S2S / ASR voice-only probe")
    for label, passed in checks.items():
        print(("PASS" if passed else "FAIL") + " " + label)
    print(f"ASR chars={len(canonical_asr)} matched={','.join(recognized) or '-'}")
    if args.show_transcript:
        print(f"ASR synthetic transcript={canonical_asr}")
    print(f"output_bytes={len(output)} trailing_silence_ms={_trailing_silence_ms(output)}")
    return 0 if all(checks.values()) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8291?topics=園藝花草&user=爸爸&fam=4")
    parser.add_argument("--wav", help="Optional real mono PCM16 WAV input")
    parser.add_argument("--phrase", default=DEFAULT_PHRASE, help="Synthetic input phrase when --wav is absent")
    parser.add_argument("--expect", action="append", help="ASR term that must be recognized; repeat as needed")
    parser.add_argument(
        "--show-transcript",
        action="store_true",
        help="Print the transcript only for non-sensitive synthetic regression audio",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
