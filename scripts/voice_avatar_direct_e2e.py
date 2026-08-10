#!/usr/bin/env python3
"""Capture real Voice -> Avatar direct-route audio and detect missing playout frames.

This is a pre-release media gate, not a replacement for the exact-build iPhone
gate. It creates an isolated test account, obtains a real Gateway lease/call
token, routes Voice to an explicit 0% canary, captures both Voice PCM and the
Avatar WebRTC audio track, writes WAV evidence, and deletes the test account.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
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
from call_control_store import SupabaseCallStore  # noqa: E402


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
    return {
        "ok": max_gap_ms <= 40 and len(material) == 0,
        "alignment_ms": lag * 20,
        "envelope_correlation": round(envelope_correlation, 4),
        "reference_speech_frames": int(np.sum(speech)),
        "missing_speech_runs": len(material),
        "max_missing_speech_ms": int(max_gap_ms),
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
        self.capture_tasks = []
        self.avatar_audio = []
        self.avatar_rate = 48000
        self.stop_capture = False

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
        if track.kind != "audio":
            while not self.stop_capture:
                try:
                    await asyncio.wait_for(track.recv(), timeout=2)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    return
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
            self.avatar_audio.append(np.clip(array, -32768, 32767).astype(np.int16).reshape(-1))
            self.avatar_rate = int(frame.sample_rate)

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

    async def run_media(self):
        avatar_url, avatar_session = await self.connect_avatar()
        if not avatar_session:
            raise RuntimeError("Avatar session missing")
        token = self.lease["call_token"]
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
        async with websockets.connect(voice_url + "/?" + query, max_size=None, open_timeout=20) as voice:
            deadline = time.monotonic() + self.args.timeout
            while time.monotonic() < deadline:
                message = await asyncio.wait_for(voice.recv(), timeout=20)
                if isinstance(message, str) and json.loads(message).get("type") == "ready":
                    break
            await voice.send(json.dumps({
                "type": "faceaudio", "on": True, "url": avatar_url, "session": avatar_session,
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
                frame_samples = 320
                next_send = time.monotonic()
                for offset in range(0, len(mic_pcm), frame_samples):
                    await voice.send(mic_pcm[offset:offset + frame_samples].tobytes())
                    next_send += 0.020
                    await asyncio.sleep(max(0.0, next_send - time.monotonic()))
                await voice.send(json.dumps({"type": "audio_end"}))
            else:
                await voice.send(json.dumps({"type": "text", "text": self.args.prompt}, ensure_ascii=False))
            deadline = time.monotonic() + self.args.timeout
            while time.monotonic() < deadline:
                message = await asyncio.wait_for(voice.recv(), timeout=20)
                if isinstance(message, (bytes, bytearray)):
                    voice_chunks.append(bytes(message))
                    voice_times.append(time.monotonic())
                    continue
                event = json.loads(message)
                if event.get("type") == "faceaudio_status":
                    statuses.append(event)
                elif event.get("type") == "avatar_pcm_received":
                    avatar_ack = True
                elif event.get("type") == "caption" and event.get("who") == "user":
                    user_caption += str(event.get("text") or "")
                elif event.get("type") == "caption" and event.get("who") == "nening":
                    assistant_caption += str(event.get("text") or "")
                elif event.get("type") == "turn_complete" and voice_chunks:
                    turn_complete = True
                    break
            await asyncio.sleep(3.0)
        if not turn_complete:
            raise RuntimeError("Voice turn did not complete")
        if not avatar_ack:
            raise RuntimeError("Avatar did not ACK direct PCM")
        if any(item.get("on") is False for item in statuses):
            raise RuntimeError("direct route fell back during the turn")
        voice_pcm = np.frombuffer(b"".join(voice_chunks), dtype=np.int16).copy()
        avatar_pcm = np.concatenate(self.avatar_audio) if self.avatar_audio else np.zeros(0, dtype=np.int16)
        arrival_gaps = [1000 * (right - left) for left, right in zip(voice_times, voice_times[1:])]
        return voice_pcm, avatar_pcm, {
            "direct_status": "ready",
            "avatar_ack": avatar_ack,
            "voice_chunks": len(voice_chunks),
            "voice_audio_ms": round(len(voice_pcm) / 24),
            # This measures what the test laptop's event loop received. Avatar
            # direct playout is judged separately against captured WebRTC PCM.
            "client_receive_max_gap_ms": round(max(arrival_gaps, default=0), 1),
            "avatar_audio_ms": round(len(avatar_pcm) / self.avatar_rate * 1000),
            "user_caption": user_caption,
            "assistant_caption": assistant_caption,
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


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice-canary", required=True)
    parser.add_argument("--gateway", default="https://munea-call-control-491603544409.asia-east1.run.app")
    parser.add_argument("--character", default="a05")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mic-wav", default="")
    parser.add_argument("--mic-seconds", type=float, default=5.0)
    parser.add_argument("--prompt", default="請只用自然台灣華語，連續清楚地說一段約十五秒的話，內容是今天精神還不錯、早餐吃得下、下午想在家休息；不要列點，也不要問問題。")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    run = EvidenceRun(args)
    try:
        run.create_test_identity()
        run.acquire()
        voice_pcm, avatar_pcm, metrics = await run.run_media()
        wav_write(output / "voice-reference.wav", voice_pcm, 24000)
        wav_write(output / "avatar-webrtc.wav", avatar_pcm, run.avatar_rate)
        metrics["continuity"] = continuity_metrics(voice_pcm, avatar_pcm, run.avatar_rate)
        metrics["ok"] = bool(metrics["continuity"].get("ok"))
        (output / "result.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        print("evidence=" + str(output))
        if not metrics["ok"]:
            raise SystemExit(2)
    finally:
        run.stop_capture = True
        if run.pc:
            await run.pc.close()
        for task in run.capture_tasks:
            task.cancel()
        run.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
