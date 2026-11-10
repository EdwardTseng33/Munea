#!/usr/bin/env python3
"""Gemini Live 引擎 A/B 探針:3.1 Flash Live Preview vs 2.5 Flash Native Audio。

2026-07-25 卡西法:Munea 語音線(engine/live_voice_server.py)現用
gemini-3.1-flash-live-preview。7/24 調研結論:非阻塞工具呼叫
(NON_BLOCKING + WHEN_IDLE/SILENT/INTERRUPT 排程)、affective dialog
(語氣隨情緒)、proactive audio(模型自決何時開口)三件套只在 2.5 native
audio 系列,3.1 只有同步工具呼叫。本探針直連 Gemini Live API 本身(不透過
Munea 的橋接層 live_voice_server.py),量化兩者差異、回答「要不要換」。

只做量測,不改語音線程式、不部署。獨立檔案,不被主程式 import。

用法:
    export GEMINI_API_KEY=xxx
    python engine/voice_native_audio_ab_probe.py --rounds 5

輸出:
    stdout 印摘要表;--json-out 另存完整結構化結果;
    語音樣本存 voice-samples/native-audio-ab/ 供人耳比對。
"""

import argparse
import array
import asyncio
import json
import os
import statistics
import sys
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types

BASELINE_MODEL = "gemini-3.1-flash-live-preview"

NATIVE_AUDIO_CANDIDATES = [
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.5-flash-native-audio-preview-09-2025",
    "gemini-2.5-flash-native-audio-latest",
]

INPUT_RATE = 16000
OUTPUT_RATE = 24000
VOICE_NAME = "Leda"
LANGUAGE_CODE = "cmn-TW"

GREETING_PHRASE = "早安,今天天氣真好,晚點要不要一起去公園走走?"
LOOKUP_PHRASE = "欸,幫我查一下,巷口那家水餃店最近好像有換老闆,你知道嗎?"
EMOTION_PHRASE = "我今天心情有點不好,家裡的事讓我很煩,不知道該怎麼辦。"

TTS_MODELS = ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts")

TOOL_DELAY_SECONDS = 4.0


def _read_key(explicit):
    key = (explicit or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not key:
        raise SystemExit("需要 GEMINI_API_KEY(環境變數或 --key)")
    return key


def _resample_pcm16(pcm, source_rate, target_rate):
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


def _save_wav(path, pcm, rate):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)


def _synthesize_input_pcm(client, phrase):
    errors = []
    for model in TTS_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=phrase,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        language_code=LANGUAGE_CODE,
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
                        ),
                    ),
                ),
            )
            part = response.candidates[0].content.parts[0]
            pcm = part.inline_data.data
            if isinstance(pcm, str):
                import base64
                pcm = base64.b64decode(pcm)
            if pcm:
                return _resample_pcm16(pcm, 24000, INPUT_RATE), model
        except Exception as exc:
            errors.append(model + ":" + type(exc).__name__ + ":" + str(exc)[:80])
    raise RuntimeError("input TTS synth failed: " + "; ".join(errors))


async def _stream_speech_then_silence(session, pcm, speech_end_marker):
    frame_bytes = int(INPUT_RATE * 0.02) * 2
    mime = "audio/pcm;rate=" + str(INPUT_RATE)
    for offset in range(0, len(pcm), frame_bytes):
        chunk = pcm[offset:offset + frame_bytes]
        await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type=mime))
        await asyncio.sleep(0.02)
    speech_end_marker["t"] = time.monotonic()
    silence_frames = int(round(1.1 / 0.02))
    silence_chunk = b"\x00" * frame_bytes
    for _ in range(silence_frames):
        await session.send_realtime_input(audio=types.Blob(data=silence_chunk, mime_type=mime))
        await asyncio.sleep(0.02)
    await session.send_realtime_input(audio_stream_end=True)


async def _next_message(session_iter, timeout_s):
    """session.receive() 是沒有內建逾時的 async iterator——伺服器若在工具等待期
    整段沉默不送任何訊息也不斷線,原本的 async for 會卡死。這裡逐則包 wait_for,
    逾時就丟 asyncio.TimeoutError 讓呼叫端記成 error 並收工,不讓探針掛住。"""
    return await asyncio.wait_for(session_iter.__anext__(), timeout=timeout_s)


def _base_config(tools=None, affective=False, proactive=False, language_code=LANGUAGE_CODE):
    # 2026-07-25 實測:2.5 native audio 系列不吃顯式 language_code(連 cmn-CN/zh-TW 都拒),
    # 只有 3.1 系列吃 cmn-TW(7/12 台灣腔修正用的那個)。language_code=None 時退回不設定,
    # 讓 native audio 自己從輸入音檔偵測語言 —— 這代表換 2.5 會失去「明講台灣腔」這個鎖點。
    if language_code:
        speech_config = types.SpeechConfig(
            language_code=language_code,
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
            ),
        )
    else:
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
            ),
        )
    kwargs = dict(
        response_modalities=["AUDIO"],
        system_instruction="你是語音助理的 A/B 測試對象,用自然、簡短的台灣華語口語回應。",
        output_audio_transcription=types.AudioTranscriptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=speech_config,
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=300,
                silence_duration_ms=800,
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
    )
    if tools:
        kwargs["tools"] = tools
    if affective:
        kwargs["enable_affective_dialog"] = True
    if proactive:
        kwargs["proactivity"] = types.ProactivityConfig(proactive_audio=True)
    return types.LiveConnectConfig(**kwargs)


async def check_connectivity(client, model):
    t0 = time.monotonic()
    try:
        async with client.aio.live.connect(model=model, config=_base_config(language_code=LANGUAGE_CODE)):
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            return {
                "model": model, "ok": True, "connect_ms": elapsed_ms, "error": None,
                "language_code_effective": LANGUAGE_CODE,
            }
    except Exception as exc:
        first_err = type(exc).__name__ + ": " + str(exc)[:200]
        if "anguage code" not in str(exc):
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            return {
                "model": model, "ok": False, "connect_ms": elapsed_ms, "error": first_err,
                "language_code_effective": None,
            }
    # cmn-TW 被拒 -> 退無 language_code 再試一次(2.5 native audio 的已知限制)
    t1 = time.monotonic()
    try:
        async with client.aio.live.connect(model=model, config=_base_config(language_code=None)):
            elapsed_ms = round((time.monotonic() - t1) * 1000, 1)
            return {
                "model": model, "ok": True, "connect_ms": elapsed_ms,
                "error": "language_code=" + LANGUAGE_CODE + " rejected, fell back to auto-detect: " + first_err,
                "language_code_effective": None,
            }
    except Exception as exc2:
        elapsed_ms = round((time.monotonic() - t1) * 1000, 1)
        return {
            "model": model, "ok": False, "connect_ms": elapsed_ms,
            "error": first_err + " | retry_without_lang: " + type(exc2).__name__ + ": " + str(exc2)[:150],
            "language_code_effective": None,
        }


async def run_latency_round(client, model, pcm, round_idx, samples_dir, label, language_code=LANGUAGE_CODE):
    result = {"model": model, "round": round_idx, "label": label}
    t0 = time.monotonic()
    speech_end_marker = {}
    try:
        async with client.aio.live.connect(model=model, config=_base_config(language_code=language_code)) as session:
            t_ready = time.monotonic()
            result["connect_ms"] = round((t_ready - t0) * 1000, 1)

            sender = asyncio.create_task(
                _stream_speech_then_silence(session, pcm, speech_end_marker))

            output = bytearray()
            output_transcript = ""
            input_transcript = ""
            first_audio_ms = None
            turn_complete = False
            t_turn_complete = None

            session_iter = session.receive().__aiter__()
            while True:
                remaining = 35 - (time.monotonic() - t0)
                if remaining <= 0:
                    result["error"] = "timeout waiting for turn_complete"
                    break
                try:
                    message = await _next_message(session_iter, min(remaining, 15))
                except (asyncio.TimeoutError, StopAsyncIteration):
                    result["error"] = "timeout waiting for next message (no server activity)"
                    break
                now = time.monotonic()
                data = message.data
                if data:
                    if first_audio_ms is None and "t" in speech_end_marker:
                        first_audio_ms = round((now - speech_end_marker["t"]) * 1000, 1)
                    output.extend(data)
                sc = message.server_content
                if sc:
                    if sc.output_transcription and sc.output_transcription.text:
                        output_transcript += sc.output_transcription.text
                    if sc.input_transcription and sc.input_transcription.text:
                        input_transcript += sc.input_transcription.text
                    if sc.turn_complete:
                        turn_complete = True
                        t_turn_complete = now
                        break

            sender.cancel()
            try:
                await sender
            except Exception:
                pass

            result["first_audio_latency_ms"] = first_audio_ms
            result["turn_complete"] = turn_complete
            if turn_complete and "t" in speech_end_marker:
                result["total_response_ms"] = round((t_turn_complete - speech_end_marker["t"]) * 1000, 1)
            result["output_bytes"] = len(output)
            result["output_duration_s"] = round(len(output) / 2 / OUTPUT_RATE, 2)
            result["output_transcript"] = output_transcript.strip()
            result["input_transcript_asr"] = input_transcript.strip()

            if output:
                sample_name = label + "_" + model.replace(".", "_") + "_round" + str(round_idx) + ".wav"
                sample_path = samples_dir / sample_name
                _save_wav(sample_path, bytes(output), OUTPUT_RATE)
                result["sample_path"] = str(sample_path)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)[:300]
    return result


def _slow_lookup_tool(non_blocking):
    behavior = types.Behavior.NON_BLOCKING if non_blocking else types.Behavior.BLOCKING
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="slow_lookup",
            description="查詢店家最新資訊時呼叫這個工具,查詢需要幾秒鐘。",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="要查的店家或問題"),
                },
                required=["query"],
            ),
            behavior=behavior,
        )
    ])


async def run_tool_round(client, model, pcm, non_blocking, scheduling, samples_dir, label, language_code=LANGUAGE_CODE):
    result = {
        "model": model, "label": label, "non_blocking": non_blocking,
        "scheduling": scheduling.name if scheduling else None,
    }
    tool = _slow_lookup_tool(non_blocking)
    config = _base_config(tools=[tool], language_code=language_code)
    t0 = time.monotonic()
    speech_end_marker = {}
    timeline = []
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            result["connect_ms"] = round((time.monotonic() - t0) * 1000, 1)
            sender = asyncio.create_task(
                _stream_speech_then_silence(session, pcm, speech_end_marker))

            output = bytearray()
            output_transcript = ""
            tool_call_seen_at = None
            tool_response_sent_at_box = {}
            turn_complete = False
            t_turn_complete = None
            responder_task = None

            async def _respond_after_delay(sess, call_id, fn_name):
                await asyncio.sleep(TOOL_DELAY_SECONDS)
                await sess.send_tool_response(function_responses=types.FunctionResponse(
                    id=call_id, name=fn_name,
                    response={"result": "老闆換人了,但水餃味道差不多,生意還不錯。"},
                    scheduling=scheduling,
                ))
                sent_at = time.monotonic()
                tool_response_sent_at_box["t"] = sent_at
                timeline.append({"t_rel_s": round(sent_at - t0, 2), "event": "tool_response_sent"})

            session_iter = session.receive().__aiter__()
            while True:
                remaining = 45 - (time.monotonic() - t0)
                if remaining <= 0:
                    result["error"] = "timeout waiting for turn_complete"
                    break
                try:
                    message = await _next_message(session_iter, min(remaining, 15))
                except (asyncio.TimeoutError, StopAsyncIteration):
                    result["error"] = "timeout waiting for next message (no server activity)"
                    timeline.append({
                        "t_rel_s": round(time.monotonic() - t0, 2), "event": "receive_timeout",
                    })
                    break
                now = time.monotonic()
                data = message.data
                if data:
                    output.extend(data)
                    timeline.append({
                        "t_rel_s": round(now - t0, 2), "event": "audio_chunk",
                        "bytes": len(data),
                        "during_tool_wait": bool(tool_call_seen_at and "t" not in tool_response_sent_at_box),
                    })
                sc = message.server_content
                if sc:
                    if sc.output_transcription and sc.output_transcription.text:
                        text = sc.output_transcription.text
                        output_transcript += text
                        timeline.append({
                            "t_rel_s": round(now - t0, 2), "event": "output_text",
                            "text": text,
                            "during_tool_wait": bool(tool_call_seen_at and "t" not in tool_response_sent_at_box),
                        })
                    if sc.turn_complete:
                        turn_complete = True
                        t_turn_complete = now
                        break
                if message.tool_call and tool_call_seen_at is None:
                    tool_call_seen_at = now
                    fc = message.tool_call.function_calls[0]
                    timeline.append({
                        "t_rel_s": round(now - t0, 2), "event": "tool_call_received",
                        "fn": fc.name, "args": dict(fc.args or {}),
                    })
                    responder_task = asyncio.create_task(
                        _respond_after_delay(session, fc.id, fc.name))

            sender.cancel()
            try:
                await sender
            except Exception:
                pass
            if responder_task:
                try:
                    await asyncio.wait_for(responder_task, timeout=10)
                except Exception:
                    responder_task.cancel()

            result["tool_call_seen"] = tool_call_seen_at is not None
            result["turn_complete"] = turn_complete
            result["output_bytes"] = len(output)
            result["output_transcript"] = output_transcript.strip()
            result["timeline"] = timeline
            spoke_during_wait = False
            for e in timeline:
                if e["event"] in ("audio_chunk", "output_text") and e.get("during_tool_wait"):
                    spoke_during_wait = True
                    break
            result["spoke_during_tool_wait"] = spoke_during_wait
            if output:
                sample_name = label + "_" + model.replace(".", "_") + "_tool.wav"
                sample_path = samples_dir / sample_name
                _save_wav(sample_path, bytes(output), OUTPUT_RATE)
                result["sample_path"] = str(sample_path)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)[:300]
        result["timeline"] = timeline
    return result


async def check_affect_proactive_accept(client, model, language_code=LANGUAGE_CODE):
    out = {"model": model}
    variants = (
        ("affective_dialog", dict(affective=True)),
        ("proactive_audio", dict(proactive=True)),
        ("both", dict(affective=True, proactive=True)),
    )
    for name, kwargs in variants:
        t0 = time.monotonic()
        try:
            cfg = _base_config(language_code=language_code, **kwargs)
            async with client.aio.live.connect(model=model, config=cfg):
                out[name] = {"accepted": True, "connect_ms": round((time.monotonic() - t0) * 1000, 1)}
        except Exception as exc:
            out[name] = {"accepted": False, "error": type(exc).__name__ + ": " + str(exc)[:150]}
    return out


async def run_emotion_round(client, model, pcm, affective, samples_dir, language_code=LANGUAGE_CODE):
    label = "emotion_affective" + str(int(affective))
    config = _base_config(affective=affective, language_code=language_code)
    result = {"model": model, "affective_dialog": affective}
    t0 = time.monotonic()
    speech_end_marker = {}
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            sender = asyncio.create_task(
                _stream_speech_then_silence(session, pcm, speech_end_marker))
            output = bytearray()
            output_transcript = ""
            turn_complete = False
            t_turn_complete = None
            session_iter = session.receive().__aiter__()
            while True:
                remaining = 30 - (time.monotonic() - t0)
                if remaining <= 0:
                    result["error"] = "timeout"
                    break
                try:
                    message = await _next_message(session_iter, min(remaining, 15))
                except (asyncio.TimeoutError, StopAsyncIteration):
                    result["error"] = "timeout waiting for next message (no server activity)"
                    break
                now = time.monotonic()
                if message.data:
                    output.extend(message.data)
                sc = message.server_content
                if sc:
                    if sc.output_transcription and sc.output_transcription.text:
                        output_transcript += sc.output_transcription.text
                    if sc.turn_complete:
                        turn_complete = True
                        t_turn_complete = now
                        break
            sender.cancel()
            try:
                await sender
            except Exception:
                pass
            result["turn_complete"] = turn_complete
            if turn_complete and "t" in speech_end_marker:
                result["total_response_ms"] = round((t_turn_complete - speech_end_marker["t"]) * 1000, 1)
            result["output_transcript"] = output_transcript.strip()
            result["output_duration_s"] = round(len(output) / 2 / OUTPUT_RATE, 2)
            if output_transcript.strip():
                dur = max(result["output_duration_s"], 0.01)
                result["speaking_rate_chars_per_s"] = round(len(output_transcript.strip()) / dur, 2)
            if output:
                sample_name = label + "_" + model.replace(".", "_") + ".wav"
                sample_path = samples_dir / sample_name
                _save_wav(sample_path, bytes(output), OUTPUT_RATE)
                result["sample_path"] = str(sample_path)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)[:300]
    return result


def _summ(values):
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return None
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 1),
        "median": round(statistics.median(values), 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
    }


async def main_async(args):
    key = _read_key(args.key)
    client = genai.Client(api_key=key)
    samples_dir = Path(args.out_dir)
    samples_dir.mkdir(parents=True, exist_ok=True)

    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "baseline_model": BASELINE_MODEL}

    print("== 1. model connectivity ==")
    connectivity = []
    for model in [BASELINE_MODEL] + NATIVE_AUDIO_CANDIDATES:
        r = await check_connectivity(client, model)
        connectivity.append(r)
        status = "OK  " if r["ok"] else "FAIL"
        print("  " + status + " " + model + " connect_ms=" + str(r["connect_ms"]) + " err=" + str(r["error"]))
    report["connectivity"] = connectivity

    working_native = []
    for c in connectivity:
        if c["ok"] and c["model"] != BASELINE_MODEL:
            working_native.append(c["model"])
    if not working_native:
        print("!! no 2.5 native audio model reachable, skip remaining tests")
        report["native_model_used"] = None
        _write_report(report, args)
        return report
    primary_native = working_native[0]
    report["native_model_used"] = primary_native
    print("  -> deep test target: " + primary_native)

    lang_by_model = {c["model"]: c.get("language_code_effective") for c in connectivity}
    baseline_lang = lang_by_model.get(BASELINE_MODEL, LANGUAGE_CODE)
    native_lang = lang_by_model.get(primary_native)
    report["language_code_used"] = {"baseline": baseline_lang, "native": native_lang}
    if native_lang != LANGUAGE_CODE:
        print("  !! native audio 不吃 language_code=" + LANGUAGE_CODE
              + " -> 該模型後續測試改用自動語言偵測(language_code=None),已記入報告")

    print("")
    print("== 2. synth greeting input ==")
    greeting_pcm, tts_model = _synthesize_input_pcm(client, GREETING_PHRASE)
    print("  synth by " + tts_model + " bytes=" + str(len(greeting_pcm)) + " rate=" + str(INPUT_RATE))
    _save_wav(samples_dir / "input_greeting_16k.wav", greeting_pcm, INPUT_RATE)

    print("")
    print("== 3. baseline latency A/B x" + str(args.rounds) + " ==")
    latency_results = {"baseline": [], "native": []}
    for i in range(1, args.rounds + 1):
        r = await run_latency_round(client, BASELINE_MODEL, greeting_pcm, i, samples_dir, "greeting", language_code=baseline_lang)
        latency_results["baseline"].append(r)
        print("  [3.1][" + str(i) + "] connect=" + str(r.get("connect_ms")) + "ms first_audio="
              + str(r.get("first_audio_latency_ms")) + "ms total=" + str(r.get("total_response_ms"))
              + "ms err=" + str(r.get("error")))
        await asyncio.sleep(1.5)
    for i in range(1, args.rounds + 1):
        r = await run_latency_round(client, primary_native, greeting_pcm, i, samples_dir, "greeting", language_code=native_lang)
        latency_results["native"].append(r)
        print("  [2.5][" + str(i) + "] connect=" + str(r.get("connect_ms")) + "ms first_audio="
              + str(r.get("first_audio_latency_ms")) + "ms total=" + str(r.get("total_response_ms"))
              + "ms err=" + str(r.get("error")))
        await asyncio.sleep(1.5)
    report["latency"] = latency_results
    report["latency_summary"] = {
        "baseline_connect_ms": _summ([r.get("connect_ms") for r in latency_results["baseline"]]),
        "baseline_first_audio_ms": _summ([r.get("first_audio_latency_ms") for r in latency_results["baseline"]]),
        "baseline_total_ms": _summ([r.get("total_response_ms") for r in latency_results["baseline"]]),
        "native_connect_ms": _summ([r.get("connect_ms") for r in latency_results["native"]]),
        "native_first_audio_ms": _summ([r.get("first_audio_latency_ms") for r in latency_results["native"]]),
        "native_total_ms": _summ([r.get("total_response_ms") for r in latency_results["native"]]),
    }

    if not args.skip_tool_test:
        print("")
        print("== 4. non-blocking tool call test x" + str(args.tool_rounds)
              + " (simulated " + str(TOOL_DELAY_SECONDS) + "s lookup) ==")
        lookup_pcm, _ = _synthesize_input_pcm(client, LOOKUP_PHRASE)
        _save_wav(samples_dir / "input_lookup_16k.wav", lookup_pcm, INPUT_RATE)

        print("  -- 3.1 baseline (sync/BLOCKING) --")
        tool_baseline_runs = []
        for i in range(1, args.tool_rounds + 1):
            r = await run_tool_round(
                client, BASELINE_MODEL, lookup_pcm, non_blocking=False, scheduling=None,
                samples_dir=samples_dir, label="lookup_sync_r" + str(i), language_code=baseline_lang)
            tool_baseline_runs.append(r)
            print("     [" + str(i) + "] tool_call_seen=" + str(r.get("tool_call_seen"))
                  + " spoke_during_wait=" + str(r.get("spoke_during_tool_wait"))
                  + " err=" + str(r.get("error")))
            await asyncio.sleep(1.5)

        print("  -- 2.5 native audio (NON_BLOCKING + WHEN_IDLE) --")
        tool_native_runs = []
        for i in range(1, args.tool_rounds + 1):
            r = await run_tool_round(
                client, primary_native, lookup_pcm, non_blocking=True,
                scheduling=types.FunctionResponseScheduling.WHEN_IDLE,
                samples_dir=samples_dir, label="lookup_nonblocking_whenidle_r" + str(i), language_code=native_lang)
            tool_native_runs.append(r)
            print("     [" + str(i) + "] tool_call_seen=" + str(r.get("tool_call_seen"))
                  + " spoke_during_wait=" + str(r.get("spoke_during_tool_wait"))
                  + " err=" + str(r.get("error")))
            await asyncio.sleep(1.5)

        report["tool_call_test"] = {
            "baseline_sync_runs": tool_baseline_runs,
            "native_nonblocking_whenidle_runs": tool_native_runs,
            "baseline_tool_call_rate": sum(1 for r in tool_baseline_runs if r.get("tool_call_seen")) / len(tool_baseline_runs),
            "native_tool_call_rate": sum(1 for r in tool_native_runs if r.get("tool_call_seen")) / len(tool_native_runs),
        }
    else:
        report["tool_call_test"] = None

    if not args.skip_affect_test:
        print("")
        print("== 5. affective_dialog / proactive_audio acceptance ==")
        affect_accept = {}
        for model in [BASELINE_MODEL, primary_native]:
            model_lang = baseline_lang if model == BASELINE_MODEL else native_lang
            r = await check_affect_proactive_accept(client, model, language_code=model_lang)
            affect_accept[model] = r
            print("  " + model + ": affective=" + str(r["affective_dialog"])
                  + " proactive=" + str(r["proactive_audio"]) + " both=" + str(r["both"]))
        report["affect_proactive_accept"] = affect_accept

        print("  -- emotion phrase quick test (native audio, affective on/off) --")
        emotion_pcm, _ = _synthesize_input_pcm(client, EMOTION_PHRASE)
        _save_wav(samples_dir / "input_emotion_16k.wav", emotion_pcm, INPUT_RATE)
        emo_off = await run_emotion_round(client, primary_native, emotion_pcm, affective=False, samples_dir=samples_dir, language_code=native_lang)
        await asyncio.sleep(1.5)
        emo_on = await run_emotion_round(client, primary_native, emotion_pcm, affective=True, samples_dir=samples_dir, language_code=native_lang)
        print("     affective=False transcript=" + str(emo_off.get("output_transcript", ""))[:60])
        print("     affective=True  transcript=" + str(emo_on.get("output_transcript", ""))[:60])
        report["emotion_test"] = {"affective_off": emo_off, "affective_on": emo_on}
    else:
        report["affect_proactive_accept"] = None
        report["emotion_test"] = None

    print("")
    print("== 6. pricing note ==")
    report["pricing_note"] = (
        "2026-07-25 ai.google.dev/gemini-api/docs/pricing scrape: "
        "3.1 Flash Live Preview input text $0.75/1M, audio $3.00/1M(or $0.005/min), "
        "output text $4.50/1M, audio $12.00/1M(or $0.018/min); "
        "2.5 Flash Native Audio(12-2025) input text $0.50/1M, audio/video $3.00/1M, "
        "output text $2.00/1M, audio $12.00/1M(no per-min option). "
        "Audio output unit price is the same, but 2.5 native audio text tokens are cheaper; "
        "both are labeled Preview on Developer API(not Vertex), stricter rate limits."
    )
    print("  " + report["pricing_note"])

    _write_report(report, args)
    return report


def _write_report(report, args):
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("")
        print("JSON full result saved: " + args.json_out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", help="Gemini API key (default env GEMINI_API_KEY)")
    parser.add_argument("--rounds", type=int, default=5, help="rounds per model for basic latency A/B")
    parser.add_argument("--out-dir", default="voice-samples/native-audio-ab", help="audio sample output dir")
    parser.add_argument("--json-out", default="voice-samples/native-audio-ab/report.json", help="full JSON result path")
    parser.add_argument("--tool-rounds", type=int, default=3, help="non-blocking tool call test repeats per model")
    parser.add_argument("--skip-tool-test", action="store_true")
    parser.add_argument("--skip-affect-test", action="store_true")
    parser.add_argument("--global-timeout", type=float, default=600.0, help="整支探針的硬上限秒數,防止任何一步卡死")
    args = parser.parse_args()
    try:
        asyncio.run(asyncio.wait_for(main_async(args), timeout=args.global_timeout))
    except asyncio.TimeoutError:
        print("")
        print("!! GLOBAL TIMEOUT hit (" + str(args.global_timeout) + "s) - probe aborted, see partial log above")
        sys.exit(1)


if __name__ == "__main__":
    main()
