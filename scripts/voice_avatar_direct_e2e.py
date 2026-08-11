#!/usr/bin/env python3
"""Act as a fake phone on the real Gateway -> Voice -> Avatar call path.

This is the automated gate that runs before a human receives a candidate. It
creates an isolated test account, obtains a real Gateway lease/call token,
streams a recorded human WAV into Voice, requires Voice to send PCM directly to
Avatar, captures Avatar WebRTC audio and video, measures real mouth-to-audio
onset, scores the ASR transcript, and deletes the test account. ``--transport relay`` remains available to verify the fallback,
but cannot certify the release candidate's primary audio route.

It still does not certify iOS permissions, WebView audio routing, or an exact
installed build. Those remain the final device gate after this fake phone has
passed.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import difflib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path

import numpy as np
import requests
import websockets
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from scipy.signal import correlate, correlation_lags, resample_poly


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "gateway"))
sys.path.insert(0, str(ROOT / "engine"))
from env_loader import load_engine_env  # noqa: E402
from call_control_store import SupabaseCallStore  # noqa: E402

load_engine_env()


def normalize_transcript(value: str) -> str:
    """Keep only comparable CJK letters and alphanumerics."""
    return "".join(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", str(value or ""))).lower()


def transcript_char_recall(expected: str, actual: str) -> float:
    """Ordered character recall; suitable for short Mandarin ASR fixtures."""
    wanted = normalize_transcript(expected)
    heard = normalize_transcript(actual)
    if not wanted:
        return 1.0
    matcher = difflib.SequenceMatcher(a=wanted, b=heard, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(wanted)


def source_playout_metrics(chunks, arrival_times, prebuffer_ms=350.0) -> dict:
    """Model the App/Avatar PCM queue and expose audible source starvation."""
    if not chunks or not arrival_times or len(chunks) != len(arrival_times):
        return {"ok": False, "underrun_count": 0, "max_underrun_ms": None}
    head = float(arrival_times[0]) + max(0.0, float(prebuffer_ms)) / 1000.0
    gaps = []
    for chunk, arrived in zip(chunks, arrival_times):
        arrived = float(arrived)
        if arrived > head:
            gaps.append(1000.0 * (arrived - head))
            head = arrived + max(0.0, float(prebuffer_ms)) / 1000.0
        head += len(chunk) / float(24000 * 2)
    material = [gap for gap in gaps if gap >= 40.0]
    return {
        "ok": not material,
        "underrun_count": len(material),
        "max_underrun_ms": round(max(material, default=0.0), 1),
    }


def webrtc_frame_timing_metrics(frames) -> dict:
    """Detect RTP timeline holes separately from content-envelope comparison."""
    if len(frames) < 2:
        return {"ok": False, "frame_count": len(frames), "gap_count": 0,
                "max_pts_gap_ms": None, "max_receive_late_ms": None}
    pts_gaps = []
    receive_late = []
    captured_samples = 0
    for previous, current in zip(frames, frames[1:]):
        prev_pts, prev_samples, prev_rate, prev_received = previous
        pts, _samples, rate, received = current
        rate = int(rate or prev_rate or 0)
        captured_samples += int(prev_samples)
        if rate > 0 and pts is not None and prev_pts is not None:
            missing = int(pts) - (int(prev_pts) + int(prev_samples))
            if missing > 0:
                pts_gaps.append({
                    "at_captured_ms": 1000.0 * captured_samples / rate,
                    "duration_ms": 1000.0 * missing / rate,
                })
        expected_s = float(prev_samples) / max(1, int(prev_rate or rate or 1))
        late_ms = 1000.0 * ((float(received) - float(prev_received)) - expected_s)
        if late_ms > 0:
            receive_late.append(late_ms)
    material_pts = [gap for gap in pts_gaps if gap["duration_ms"] >= 20.0]
    max_receive = max(receive_late, default=0.0)
    return {
        "ok": not material_pts,
        "frame_count": len(frames),
        "gap_count": len(material_pts),
        "max_pts_gap_ms": round(max(
            (gap["duration_ms"] for gap in material_pts), default=0.0
        ), 1),
        "pts_gaps": [{key: round(value, 1) for key, value in gap.items()}
                     for gap in material_pts],
        # Diagnostic only: browser/aiortc jitter buffers can absorb wall-clock
        # delivery variance without an audible RTP timeline hole.
        "max_receive_late_ms": round(max_receive, 1),
    }


def webrtc_speech_gap_metrics(timing: dict, continuity: dict) -> dict:
    """Fail only RTP holes that intersect captured assistant speech.

    WebRTC can drop idle/poster silence before the Avatar begins speaking. That
    remains diagnostic evidence, but it is not the audible in-sentence failure
    this release gate is designed to block.
    """
    windows = continuity.get("speech_windows_ms") or []
    material = []
    for gap in timing.get("pts_gaps") or []:
        at_ms = float(gap.get("at_captured_ms") or 0.0)
        for start_ms, end_ms in windows:
            if float(start_ms) - 20.0 <= at_ms <= float(end_ms) + 20.0:
                material.append(gap)
                break
    return {
        "ok": not material,
        "speech_gap_count": len(material),
        "max_speech_pts_gap_ms": round(max(
            (float(gap.get("duration_ms") or 0.0) for gap in material), default=0.0
        ), 1),
        "speech_pts_gaps": material,
    }


def avatar_av_sync_metrics(audio_levels, video_motion, max_skew_ms=250.0) -> dict:
    """Measure actual WebRTC audio onset against image-derived mouth motion.

    Positive skew means the user hears speech before the mouth begins moving.
    This deliberately consumes receiver timestamps rather than Voice PCM arrival,
    because independent WebRTC audio/video jitter buffers are part of the product
    experience we need to certify.
    """
    audio_on = next((float(stamp) for stamp, rms in audio_levels
                     if float(rms) >= 0.045), None)
    if audio_on is None:
        return {"ok": False, "reason": "no_audio_onset", "skew_ms": None}
    # FlashHead 的待機呼吸與微小頭動也會讓單一影格越過門檻。嘴型啟動必須是
    # 120ms 內至少兩格持續變化，並且其中一格達到強門檻；再選最靠近聲音
    # onset 的那一組。這樣量到的是說話嘴型，不是回合前的待機動畫。
    window = sorted(
        (float(stamp), float(motion)) for stamp, motion in video_motion
        if audio_on - 0.25 <= float(stamp) <= audio_on + 1.5
    )
    candidates = []
    for index, (stamp, motion) in enumerate(window):
        nearby = [
            next_motion
            for next_stamp, next_motion in window[index:index + 5]
            if 0.0 <= next_stamp - stamp <= 0.12
        ]
        if (
            motion >= 0.020
            and sum(value >= 0.020 for value in nearby) >= 2
            and max(nearby, default=0.0) >= 0.028
        ):
            candidates.append((stamp, max(nearby)))
    if not candidates:
        return {"ok": False, "reason": "no_mouth_motion", "skew_ms": None}
    mouth_on, peak = min(candidates, key=lambda item: abs(item[0] - audio_on))
    skew_ms = 1000.0 * (mouth_on - audio_on)
    limit = max(0.0, float(max_skew_ms))
    return {
        "ok": abs(skew_ms) <= limit,
        "reason": "aligned" if abs(skew_ms) <= limit else "av_skew",
        "audio_onset_at": round(audio_on, 6),
        "mouth_onset_at": round(mouth_on, 6),
        "skew_ms": round(skew_ms, 1),
        "mouth_motion": round(peak, 4),
        "max_skew_ms": round(limit, 1),
    }


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(name + " is required")
    return value


def json_request(method: str, url: str, body=None, bearer="", headers=None, timeout=30):
    request_headers = {"Accept": "application/json", "Content-Type": "application/json"}
    request_headers.update(headers or {})
    if bearer:
        request_headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers=request_headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wav_write(path: Path, pcm: np.ndarray, rate: int):
    pcm = np.clip(np.asarray(pcm).reshape(-1), -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm.tobytes())


def frame_rms(pcm: np.ndarray, rate: int, frame_ms=20) -> np.ndarray:
    size = max(1, int(rate * frame_ms / 1000))
    usable = len(pcm) // size * size
    if not usable:
        return np.zeros(0, dtype=np.float32)
    frames = pcm[:usable].astype(np.float32).reshape(-1, size) / 32768.0
    return np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)


def continuity_metrics(voice_pcm: np.ndarray, avatar_pcm: np.ndarray, avatar_rate: int) -> dict:
    if not len(voice_pcm) or not len(avatar_pcm):
        return {"ok": False, "reason": "missing_audio"}
    reference = resample_poly(voice_pcm.astype(np.float32), avatar_rate, 24000)
    ref_env = frame_rms(reference, avatar_rate)
    out_env = frame_rms(avatar_pcm, avatar_rate)
    if not len(ref_env) or not len(out_env):
        return {"ok": False, "reason": "empty_envelope"}

    # Envelope correlation is resilient to Opus and sample-rate conversion.
    corr = correlate(out_env - np.mean(out_env), ref_env - np.mean(ref_env), mode="full", method="fft")
    lags = correlation_lags(len(out_env), len(ref_env), mode="full")
    lag = int(lags[int(np.argmax(corr))])
    ref_start = max(0, -lag)
    out_start = max(0, lag)
    count = min(len(ref_env) - ref_start, len(out_env) - out_start)
    ref = ref_env[ref_start:ref_start + count]
    out = out_env[out_start:out_start + count]
    speech = ref >= max(0.006, float(np.percentile(ref, 60)) * 0.45)
    missing = speech & (out < np.maximum(0.0025, ref * 0.20))

    runs = []
    start = None
    for index, value in enumerate(missing):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append(index - start)
            start = None
    if start is not None:
        runs.append(len(missing) - start)
    material = [run for run in runs if run >= 2]  # at least 40 ms inside reference speech

    if count > 1 and np.std(ref) > 1e-9 and np.std(out) > 1e-9:
        envelope_correlation = float(np.corrcoef(ref, out)[0, 1])
    else:
        envelope_correlation = 0.0
    max_gap_ms = max(material, default=0) * 20
    speech_windows = []
    speech_start = None
    for index, value in enumerate(speech):
        if value and speech_start is None:
            speech_start = index
        elif not value and speech_start is not None:
            speech_windows.append([
                int((out_start + speech_start) * 20), int((out_start + index) * 20)
            ])
            speech_start = None
    if speech_start is not None:
        speech_windows.append([
            int((out_start + speech_start) * 20), int((out_start + len(speech)) * 20)
        ])
    return {
        "ok": max_gap_ms <= 40 and len(material) == 0,
        "alignment_ms": lag * 20,
        "envelope_correlation": round(envelope_correlation, 4),
        "reference_speech_frames": int(np.sum(speech)),
        "missing_speech_runs": len(material),
        "max_missing_speech_ms": int(max_gap_ms),
        "speech_windows_ms": speech_windows,
    }


class EvidenceRun:
    def __init__(self, args):
        self.args = args
        self.run_id = uuid.uuid4().hex[:12]
        self.store = SupabaseCallStore(required("SUPABASE_URL"), required("SUPABASE_SERVICE_ROLE_KEY"))
        self.user_id = ""
        self.account_id = ""
        self.access_token = ""
        self.lease = None
        self.pc = None
        self.avatar_feed = None
        self.avatar_feed_task = None
        self.avatar_feed_ack = False
        self.capture_tasks = []
        self.avatar_audio = []
        self.avatar_audio_levels = []
        self.avatar_frame_timing = []
        self.avatar_video_motion = []
        self.avatar_video_frames = 0
        self._avatar_video_previous = None
        self.avatar_rate = 48000
        self.stop_capture = False

    def avatar_health(self, base, token):
        """Read only decision-useful Avatar counters; never persist the call token."""
        try:
            response = requests.get(
                base.rstrip("/") + "/health", params={"token": token}, timeout=10
            )
            response.raise_for_status()
            body = response.json()
            return {
                "ok": bool(body.get("ok")),
                "round_count": body.get("round_count"),
                "round_latencies_ms": body.get("round_latencies_ms", []),
                "gen_compute_ms_rolling": body.get("gen_compute_ms_rolling", {}),
                "audio_underrun": body.get("audio_underrun", {}),
                "audio_sender": body.get("audio_sender", {}),
            }
        except Exception as error:
            return {"ok": False, "error": type(error).__name__}

    def service_headers(self, prefer=""):
        return self.store._service_headers(prefer)

    def rest(self, method, path, body=None, prefer=""):
        return self.store._json(
            method, self.store.url + "/rest/v1/" + path, body=body,
            headers=self.service_headers(prefer),
        )

    def create_test_identity(self):
        email = "voice-avatar-e2e-" + self.run_id + "@example.invalid"
        password = "VoiceE2E-" + uuid.uuid4().hex + "!9"
        auth = self.store._json(
            "POST", self.store.url + "/auth/v1/admin/users",
            body={"email": email, "password": password, "email_confirm": True,
                  "user_metadata": {"purpose": "voice-avatar-direct-e2e", "run_id": self.run_id}},
            headers=self.service_headers(),
        )
        self.user_id = str((auth or {}).get("id") or "")
        if not self.user_id:
            raise RuntimeError("temporary auth user creation failed")
        rows = self.rest(
            "POST", "accounts",
            {"name": "Voice Avatar E2E", "locale": "zh-TW", "is_test_account": True},
            "return=representation",
        )
        self.account_id = str((rows or [{}])[0].get("id") or "")
        self.rest("POST", "account_members", {
            "account_id": self.account_id, "user_id": self.user_id,
            "role": "owner", "status": "active",
        }, "return=minimal")
        self.rest("POST", "credit_wallets", {
            "account_id": self.account_id, "wallet_type": "purchased",
            "period": "voice-avatar-e2e-" + self.run_id, "balance": 4,
            "status": "active", "metadata": {"purpose": "voice-avatar-direct-e2e"},
        }, "return=minimal")
        signed = json_request(
            "POST", self.store.url + "/auth/v1/token?grant_type=password",
            {"email": email, "password": password},
            headers={"apikey": required("SUPABASE_PUBLISHABLE_KEY")},
        )
        self.access_token = str(signed.get("access_token") or "")
        if not self.access_token:
            raise RuntimeError("temporary user sign-in failed")

    def acquire(self):
        deadline = time.monotonic() + self.args.timeout
        key = "voice-avatar-e2e-" + self.run_id
        while time.monotonic() < deadline:
            self.lease = json_request(
                "POST", self.args.gateway.rstrip("/") + "/v1/calls",
                {"character_id": "寧寧", "idempotency_key": key},
                bearer=self.access_token,
            )
            if self.lease.get("status") == "connect":
                return
            if self.lease.get("status") != "queued":
                raise RuntimeError("Gateway lease failed: " + str(self.lease.get("reason") or self.lease.get("status")))
            time.sleep(1.0)
        raise RuntimeError("Gateway lease timed out")

    async def capture_track(self, track):
        if track.kind == "video":
            while not self.stop_capture:
                try:
                    frame = await asyncio.wait_for(track.recv(), timeout=2)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    return
                image = frame.to_ndarray(format="gray")
                height, width = image.shape[:2]
                mouth = image[
                    int(height * 0.33):max(int(height * 0.50), int(height * 0.33) + 1),
                    int(width * 0.30):max(int(width * 0.70), int(width * 0.30) + 1),
                ][::3, ::3].astype(np.float32)
                motion = 0.0
                if (self._avatar_video_previous is not None
                        and self._avatar_video_previous.shape == mouth.shape):
                    motion = float(np.mean(np.abs(mouth - self._avatar_video_previous)) / 255.0)
                self._avatar_video_previous = mouth
                self.avatar_video_motion.append((time.monotonic(), motion))
                self.avatar_video_frames += 1
            return
        if track.kind != "audio":
            return
        while not self.stop_capture:
            try:
                frame = await asyncio.wait_for(track.recv(), timeout=2)
            except asyncio.TimeoutError:
                continue
            except Exception:
                return
            array = frame.to_ndarray()
            channels = len(frame.layout.channels)
            if channels > 1:
                if array.ndim == 2 and array.shape[0] == channels:
                    array = array.astype(np.float32).mean(axis=0)
                else:
                    array = array.reshape(-1, channels).astype(np.float32).mean(axis=1)
            pcm = np.clip(array, -32768, 32767).astype(np.int16).reshape(-1)
            self.avatar_audio.append(pcm)
            rms = float(np.sqrt(np.mean(np.square(pcm.astype(np.float32) / 32768.0)))) if len(pcm) else 0.0
            self.avatar_audio_levels.append((time.monotonic(), rms))
            self.avatar_rate = int(frame.sample_rate)
            self.avatar_frame_timing.append(
                (frame.pts, frame.samples, frame.sample_rate, time.monotonic())
            )

    async def connect_avatar(self):
        token = self.lease["call_token"]
        base = self.lease["worker"]["url"].rstrip("/")
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[
            RTCIceServer(urls="stun:stun.l.google.com:19302"),
            RTCIceServer(
                urls=["turn:34.81.102.52:3478?transport=udp", "turn:34.81.102.52:3478?transport=tcp"],
                username="muneaturn", credential="munea-turn-a7k2q",
            ),
        ]))
        self.pc.addTransceiver("video", direction="recvonly")
        self.pc.addTransceiver("audio", direction="recvonly")

        @self.pc.on("track")
        def on_track(track):
            self.capture_tasks.append(asyncio.create_task(self.capture_track(track)))

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        for _ in range(100):
            if self.pc.iceGatheringState == "complete":
                break
            await asyncio.sleep(0.05)
        response = requests.post(
            base + "/offer", params={"token": token, "char": self.args.character},
            json={"sdp": self.pc.localDescription.sdp, "type": self.pc.localDescription.type}, timeout=30,
        )
        response.raise_for_status()
        answer = response.json()
        if answer.get("error"):
            raise RuntimeError("Avatar offer failed: " + str(answer["error"]))
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        for _ in range(150):
            if self.pc.connectionState == "connected":
                break
            await asyncio.sleep(0.1)
        if self.pc.connectionState != "connected":
            raise RuntimeError("Avatar WebRTC did not connect")
        return base, str(answer.get("session") or "")

    async def read_avatar_feed(self):
        try:
            async for message in self.avatar_feed:
                if not isinstance(message, str):
                    continue
                event = json.loads(message)
                if event.get("type") == "avatar_pcm_received":
                    self.avatar_feed_ack = True
        except Exception:
            return

    async def connect_avatar_feed(self, base, session, token):
        query = urllib.parse.urlencode({"token": token, "session": session})
        feed_url = base.replace("https://", "wss://").replace("http://", "ws://")
        self.avatar_feed = await websockets.connect(
            feed_url + "/audio?" + query,
            open_timeout=20,
            close_timeout=2,
            max_size=None,
        )
        self.avatar_feed_task = asyncio.create_task(self.read_avatar_feed())

    async def run_media(self):
        call_started_at = time.monotonic()
        avatar_url, avatar_session = await self.connect_avatar()
        if not avatar_session:
            raise RuntimeError("Avatar session missing")
        token = self.lease["call_token"]
        avatar_health_before = self.avatar_health(avatar_url, token)
        voice_url = self.args.voice_canary.rstrip("/").replace("https://", "wss://")
        query = urllib.parse.urlencode({
            "token": token, "char": "寧寧", "user": "自動聲音驗收", "fam": "0",
        })
        voice_chunks = []
        voice_times = []
        statuses = []
        user_caption = ""
        assistant_caption = ""
        avatar_ack = False
        turn_complete = False
        unsolicited_audio_bytes = 0
        unsolicited_caption = ""
        disconnected_after_turn = False
        first_response_at = None
        mic_finished_at = None
        relay_turn_started = False
        turn_results = []
        if self.args.transport == "relay":
            await self.connect_avatar_feed(avatar_url, avatar_session, token)
        async with websockets.connect(voice_url + "/?" + query, max_size=None, open_timeout=20) as voice:
            deadline = time.monotonic() + self.args.timeout
            while time.monotonic() < deadline:
                message = await asyncio.wait_for(voice.recv(), timeout=20)
                if isinstance(message, str) and json.loads(message).get("type") == "ready":
                    break
            if self.args.transport == "direct":
                await voice.send(json.dumps({
                    "type": "faceaudio", "on": True, "url": avatar_url,
                    "session": avatar_session,
                }))
                while time.monotonic() < deadline:
                    message = await asyncio.wait_for(voice.recv(), timeout=20)
                    if not isinstance(message, str):
                        continue
                    event = json.loads(message)
                    if event.get("type") == "faceaudio_status":
                        statuses.append(event)
                        if event.get("on") is True:
                            break
                        raise RuntimeError("Voice direct route failed: " + str(event.get("reason")))
            mic_pcm = None
            if self.args.mic_wav:
                with wave.open(self.args.mic_wav, "rb") as source:
                    if source.getnchannels() != 1 or source.getsampwidth() != 2:
                        raise RuntimeError("mic WAV must be mono PCM16")
                    input_rate = source.getframerate()
                    raw = source.readframes(min(source.getnframes(), int(input_rate * self.args.mic_seconds)))
                mic_pcm = np.frombuffer(raw, dtype=np.int16)
                if input_rate != 16000:
                    mic_pcm = np.clip(
                        resample_poly(mic_pcm.astype(np.float32), 16000, input_rate),
                        -32768, 32767,
                    ).astype(np.int16)

            for turn_number in range(1, self.args.turns + 1):
                voice_chunks = []
                voice_times = []
                self.avatar_audio = []
                self.avatar_audio_levels = []
                self.avatar_frame_timing = []
                self.avatar_video_motion = []
                self.avatar_video_frames = 0
                turn_user_caption = ""
                turn_assistant_caption = ""
                turn_complete = False
                first_response_at = None
                relay_turn_started = False
                if mic_pcm is not None:
                    frame_samples = 320
                    next_send = time.monotonic()
                    for offset in range(0, len(mic_pcm), frame_samples):
                        await voice.send(mic_pcm[offset:offset + frame_samples].tobytes())
                        next_send += 0.020
                        await asyncio.sleep(max(0.0, next_send - time.monotonic()))
                    await voice.send(json.dumps({"type": "audio_end"}))
                    mic_finished_at = time.monotonic()
                else:
                    turn_prompt = (
                        self.args.turn_prompts[turn_number - 1]
                        if self.args.turn_prompts else self.args.prompt
                    )
                    await voice.send(json.dumps({"type": "text", "text": turn_prompt}, ensure_ascii=False))
                    mic_finished_at = time.monotonic()

                deadline = time.monotonic() + self.args.timeout
                while time.monotonic() < deadline:
                    message = await asyncio.wait_for(voice.recv(), timeout=20)
                    if isinstance(message, (bytes, bytearray)):
                        if first_response_at is None:
                            first_response_at = time.monotonic()
                        voice_chunks.append(bytes(message))
                        voice_times.append(time.monotonic())
                        if self.args.transport == "relay":
                            if not relay_turn_started:
                                await self.avatar_feed.send("reset")
                                await self.avatar_feed.send("turn:%d" % turn_number)
                                relay_turn_started = True
                            await self.avatar_feed.send(bytes(message))
                        continue
                    event = json.loads(message)
                    if event.get("type") == "faceaudio_status":
                        statuses.append(event)
                    elif event.get("type") == "avatar_pcm_received":
                        avatar_ack = True
                    elif event.get("type") == "caption" and event.get("who") == "user":
                        turn_user_caption += str(event.get("text") or "")
                    elif event.get("type") == "caption" and event.get("who") == "nening":
                        turn_assistant_caption += str(event.get("text") or "")
                    elif event.get("type") == "turn_complete" and voice_chunks:
                        if self.args.transport == "relay":
                            await self.avatar_feed.send("finish")
                        turn_complete = True
                        break
                if not turn_complete:
                    raise RuntimeError("Voice turn %d did not complete" % turn_number)

                user_caption += turn_user_caption
                assistant_caption += turn_assistant_caption
                turn_first_response_ms = (
                    round(1000 * (first_response_at - mic_finished_at))
                    if first_response_at and mic_finished_at else None
                )
                turn_results.append({
                    "turn": turn_number,
                    "turn_complete": True,
                    "first_response_ms": turn_first_response_ms,
                    "voice_audio_ms": round(len(np.frombuffer(b"".join(voice_chunks), dtype=np.int16)) / 24),
                    "user_caption": turn_user_caption,
                    "assistant_caption": turn_assistant_caption,
                    "source_playout": source_playout_metrics(voice_chunks, voice_times),
                    "avatar_av_sync": avatar_av_sync_metrics(
                        self.avatar_audio_levels, self.avatar_video_motion,
                        self.args.max_av_skew_ms,
                    ),
                    "avatar_video_frames": self.avatar_video_frames,
                })

                # Between turns this is the exact risk gate: the same socket must
                # stay quiet, survive provider recovery, and accept fresh mic PCM.
                quiet_seconds = (
                    self.args.post_turn_quiet_seconds
                    if turn_number == self.args.turns else self.args.between_turn_seconds
                )
                quiet_deadline = time.monotonic() + quiet_seconds
                while time.monotonic() < quiet_deadline:
                    try:
                        message = await asyncio.wait_for(
                            voice.recv(), timeout=max(0.05, quiet_deadline - time.monotonic())
                        )
                    except asyncio.TimeoutError:
                        break
                    except Exception:
                        disconnected_after_turn = True
                        break
                    if isinstance(message, (bytes, bytearray)):
                        unsolicited_audio_bytes += len(message)
                        continue
                    event = json.loads(message)
                    if event.get("type") == "caption" and event.get("who") == "nening":
                        unsolicited_caption += str(event.get("text") or "")
                if disconnected_after_turn:
                    raise RuntimeError("Voice disconnected after turn %d" % turn_number)
        avatar_health_after = self.avatar_health(avatar_url, token)
        before_underruns = int(
            avatar_health_before.get("audio_underrun", {}).get("count") or 0
        )
        after_underruns = int(
            avatar_health_after.get("audio_underrun", {}).get("count") or 0
        )
        if len(turn_results) != self.args.turns:
            raise RuntimeError("Voice did not complete every requested turn")
        if self.args.transport == "direct":
            if not avatar_ack:
                raise RuntimeError("Avatar did not ACK direct PCM")
            if any(item.get("on") is False for item in statuses):
                raise RuntimeError("direct route fell back during the turn")
        elif not self.avatar_feed_ack and not self.avatar_audio:
            raise RuntimeError("Avatar relay received no PCM acknowledgement or WebRTC audio")
        voice_pcm = np.frombuffer(b"".join(voice_chunks), dtype=np.int16).copy()
        avatar_pcm = np.concatenate(self.avatar_audio) if self.avatar_audio else np.zeros(0, dtype=np.int16)
        arrival_gaps = [1000 * (right - left) for left, right in zip(voice_times, voice_times[1:])]
        source_playout = source_playout_metrics(voice_chunks, voice_times)
        return voice_pcm, avatar_pcm, {
            "call_id": str(self.lease.get("call_id") or ""),
            "call_duration_ms": round((time.monotonic() - call_started_at) * 1000),
            "transport": self.args.transport,
            "transport_status": "ready",
            "avatar_ack": avatar_ack if self.args.transport == "direct" else self.avatar_feed_ack,
            "voice_chunks": len(voice_chunks),
            "voice_audio_ms": round(len(voice_pcm) / 24),
            # This measures what the test laptop's event loop received. Avatar
            # direct playout is judged separately against captured WebRTC PCM.
            "client_receive_max_gap_ms": round(max(arrival_gaps, default=0), 1),
            "source_playout": source_playout,
            "avatar_audio_ms": round(len(avatar_pcm) / self.avatar_rate * 1000),
            "avatar_webrtc_timing": webrtc_frame_timing_metrics(self.avatar_frame_timing),
            "avatar_video_frames": self.avatar_video_frames,
            "user_caption": user_caption,
            "assistant_caption": assistant_caption,
            "first_response_ms": max(
                (item["first_response_ms"] for item in turn_results
                 if item.get("first_response_ms") is not None),
                default=None,
            ),
            "requested_turns": self.args.turns,
            "completed_turns": len(turn_results),
            "turns": turn_results,
            "avatar_av_sync": {
                "ok": bool(turn_results) and all(
                    item.get("avatar_av_sync", {}).get("ok") is True
                    for item in turn_results
                ),
                "turn_skew_ms": [
                    item.get("avatar_av_sync", {}).get("skew_ms")
                    for item in turn_results
                ],
                "max_skew_ms": self.args.max_av_skew_ms,
            },
            "unsolicited_audio_bytes": unsolicited_audio_bytes,
            "unsolicited_caption": unsolicited_caption,
            "disconnected_after_turn": disconnected_after_turn,
            "avatar_health_before": avatar_health_before,
            "avatar_health_after": avatar_health_after,
            "avatar_reported_underrun_delta": max(0, after_underruns - before_underruns),
        }

    def cleanup(self):
        if self.lease and self.lease.get("call_id") and self.access_token:
            try:
                json_request(
                    "POST", self.args.gateway.rstrip("/") + "/v1/calls/" +
                    urllib.parse.quote(str(self.lease["call_id"])) + "/release",
                    {"lease_version": self.lease["lease_version"],
                     "event_id": "voice-avatar-e2e-release-" + uuid.uuid4().hex,
                     "reason": "voice_avatar_direct_e2e_complete"},
                    bearer=self.access_token,
                )
            except Exception as error:
                print("cleanup lease warning:", type(error).__name__, file=sys.stderr)
        if self.account_id:
            try:
                self.rest("DELETE", "accounts?id=eq." + urllib.parse.quote(self.account_id))
            except Exception as error:
                print("cleanup account warning:", type(error).__name__, file=sys.stderr)
        if self.user_id:
            try:
                self.store._json(
                    "DELETE", self.store.url + "/auth/v1/admin/users/" + urllib.parse.quote(self.user_id),
                    headers=self.service_headers(),
                )
            except Exception as error:
                print("cleanup auth warning:", type(error).__name__, file=sys.stderr)


async def execute_run(args, output):
    output.mkdir(parents=True, exist_ok=True)
    run = EvidenceRun(args)
    try:
        run.create_test_identity()
        run.acquire()
        voice_pcm, avatar_pcm, metrics = await run.run_media()
        wav_write(output / "voice-reference.wav", voice_pcm, 24000)
        wav_write(output / "avatar-webrtc.wav", avatar_pcm, run.avatar_rate)
        metrics["continuity"] = continuity_metrics(voice_pcm, avatar_pcm, run.avatar_rate)
        metrics["avatar_webrtc_speech_timing"] = webrtc_speech_gap_metrics(
            metrics.get("avatar_webrtc_timing", {}), metrics["continuity"]
        )
        metrics["asr_expected"] = args.expected_text
        metrics["asr_char_recall"] = round(
            transcript_char_recall(args.expected_text, metrics.get("user_caption", "")), 4
        ) if args.expected_text else None
        metrics["gates"] = {
            "transport": metrics.get("transport_status") == "ready",
            "avatar_route": metrics.get("avatar_ack") is True,
            "asr": (metrics["asr_char_recall"] is None
                    or metrics["asr_char_recall"] >= args.min_asr_char_recall),
            "first_response": (metrics.get("first_response_ms") is not None
                               and metrics["first_response_ms"] <= args.max_first_response_ms),
            "avatar_audio": metrics.get("avatar_audio_ms", 0) >= args.min_avatar_audio_ms,
            "continuity": bool(metrics["continuity"].get("ok")),
            "avatar_reported_underrun": (
                metrics.get("avatar_health_before", {}).get("ok") is True
                and metrics.get("avatar_health_after", {}).get("ok") is True
                and metrics.get("avatar_reported_underrun_delta") == 0
            ),
            "avatar_webrtc_speech_timing": bool(
                metrics.get("avatar_webrtc_speech_timing", {}).get("ok")
            ),
            "avatar_av_sync": bool(metrics.get("avatar_av_sync", {}).get("ok")),
            "source_playout": (
                metrics.get("source_playout", {}).get("max_underrun_ms") is not None
                and metrics["source_playout"]["max_underrun_ms"] <= args.max_source_underrun_ms
            ),
            "no_unsolicited_repeat": (
                metrics.get("unsolicited_audio_bytes", 0) == 0
                and not metrics.get("unsolicited_caption")
            ),
            "connection_held": not metrics.get("disconnected_after_turn"),
            "all_turns_completed": (
                metrics.get("completed_turns") == metrics.get("requested_turns")
                and all(item.get("turn_complete") is True for item in metrics.get("turns", []))
                and all(
                    item.get("first_response_ms") is not None
                    and item["first_response_ms"] <= args.max_first_response_ms
                    and item.get("source_playout", {}).get("max_underrun_ms") is not None
                    and item["source_playout"]["max_underrun_ms"] <= args.max_source_underrun_ms
                    for item in metrics.get("turns", [])
                )
            ),
            "minimum_call_duration": (
                metrics.get("call_duration_ms", 0) >= args.min_call_seconds * 1000
            ),
        }
        metrics["ok"] = all(metrics["gates"].values())
        (output / "result.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metrics
    finally:
        run.stop_capture = True
        if run.pc:
            await run.pc.close()
        if run.avatar_feed:
            await run.avatar_feed.close()
        if run.avatar_feed_task:
            run.avatar_feed_task.cancel()
        for task in run.capture_tasks:
            task.cancel()
        run.cleanup()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice-canary", required=True)
    parser.add_argument("--gateway", default="https://munea-call-control-491603544409.asia-east1.run.app")
    parser.add_argument("--character", default="a05")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--out", required=True)
    parser.add_argument("--transport", choices=("relay", "direct"), default="direct")
    parser.add_argument("--mic-wav", default="")
    parser.add_argument("--mic-seconds", type=float, default=5.0)
    parser.add_argument("--expected-text", default="")
    parser.add_argument("--min-asr-char-recall", type=float, default=0.80)
    parser.add_argument("--max-first-response-ms", type=int, default=4500)
    parser.add_argument("--min-avatar-audio-ms", type=int, default=1000)
    parser.add_argument("--max-source-underrun-ms", type=int, default=250)
    parser.add_argument("--max-av-skew-ms", type=int, default=250)
    parser.add_argument("--post-turn-quiet-seconds", type=float, default=3.0)
    parser.add_argument("--between-turn-seconds", type=float, default=1.2)
    parser.add_argument("--turns", type=int, default=1)
    parser.add_argument("--prompts-json", default="")
    parser.add_argument("--prompts-b64", default="")
    parser.add_argument("--min-call-seconds", type=float, default=0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--prompt", default="請只用自然台灣華語，連續清楚地說一段約十五秒的話，內容是今天精神還不錯、早餐吃得下、下午想在家休息；不要列點，也不要問問題。")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.turns < 1:
        parser.error("--turns must be at least 1")
    args.turn_prompts = []
    if args.prompts_json and args.prompts_b64:
        parser.error("use only one of --prompts-json or --prompts-b64")
    prompts_payload = args.prompts_json
    if args.prompts_b64:
        try:
            prompts_payload = base64.b64decode(args.prompts_b64).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            parser.error("--prompts-b64 must be base64-encoded UTF-8 JSON: " + str(error))
    if prompts_payload:
        try:
            args.turn_prompts = json.loads(prompts_payload)
        except json.JSONDecodeError as error:
            parser.error("turn prompts must be a JSON array: " + str(error))
        if (
            not isinstance(args.turn_prompts, list)
            or len(args.turn_prompts) != args.turns
            or not all(isinstance(item, str) and item.strip() for item in args.turn_prompts)
        ):
            parser.error("--prompts-json must contain exactly --turns non-empty strings")
    if args.mic_wav and not args.expected_text.strip():
        parser.error("--expected-text is required with --mic-wav; a fake phone must score what Voice heard")
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for index in range(args.runs):
        run_output = output if args.runs == 1 else output / ("run-%02d" % (index + 1))
        try:
            metrics = await execute_run(args, run_output)
        except Exception as error:
            metrics = {
                "ok": False,
                "error": type(error).__name__,
                "error_message": str(error),
            }
            run_output.mkdir(parents=True, exist_ok=True)
            (run_output / "result.json").write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        results.append(metrics)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        print("evidence=" + str(run_output))
    summary = {
        "required_consecutive_runs": args.runs,
        "passed_runs": sum(1 for result in results if result.get("ok") is True),
        "ok": all(result.get("ok") is True for result in results),
        "results": results,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: summary[key] for key in (
        "required_consecutive_runs", "passed_runs", "ok"
    )}, ensure_ascii=False))
    if not summary["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
