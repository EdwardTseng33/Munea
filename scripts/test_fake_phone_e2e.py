#!/usr/bin/env python3
"""Fast contracts for the fake phone transcript and relay gate."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "scripts" / "voice_avatar_direct_e2e.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")


def load_functions(*names):
    tree = ast.parse(SOURCE)
    nodes = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name in names]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {"re": __import__("re"), "difflib": __import__("difflib")}
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return [namespace[name] for name in names]


normalize_transcript, transcript_char_recall, source_playout_metrics, webrtc_frame_timing_metrics, webrtc_speech_gap_metrics, avatar_av_sync_metrics, avatar_playout_complete, avatar_mouth_roi = load_functions(
    "normalize_transcript", "transcript_char_recall", "source_playout_metrics",
    "webrtc_frame_timing_metrics", "webrtc_speech_gap_metrics", "avatar_av_sync_metrics",
    "avatar_playout_complete", "avatar_mouth_roi",
)

assert normalize_transcript("我沒有發燒，但、有痰！") == "我沒有發燒但有痰"
assert transcript_char_recall("我沒有發燒但有痰", "我沒有發燒，但有痰。") == 1.0
assert transcript_char_recall("我沒有發燒但有痰", "我沒有發燒") < 0.8
continuous = source_playout_metrics(
    [b"0" * 9600] * 4, [0.0, 0.15, 0.30, 0.45], prebuffer_ms=350
)
assert continuous["underrun_count"] == 0
starved = source_playout_metrics(
    [b"0" * 9600] * 3, [0.0, 0.15, 1.20], prebuffer_ms=350
)
assert starved["underrun_count"] == 1 and starved["max_underrun_ms"] >= 400
timing_ok = webrtc_frame_timing_metrics([
    (0, 960, 48000, 0.00), (960, 960, 48000, 0.02), (1920, 960, 48000, 0.04)
])
assert timing_ok["ok"] and timing_ok["gap_count"] == 0
timing_gap = webrtc_frame_timing_metrics([
    (0, 960, 48000, 0.00), (1920, 960, 48000, 0.04)
])
assert not timing_gap["ok"] and timing_gap["max_pts_gap_ms"] == 20.0
assert timing_gap["pts_gaps"] == [{"at_captured_ms": 20.0, "duration_ms": 20.0}]
assert not webrtc_speech_gap_metrics(
    timing_gap, {"speech_windows_ms": [[0, 100]]}
)["ok"]
assert webrtc_speech_gap_metrics(
    timing_gap, {"speech_windows_ms": [[200, 300]]}
)["ok"]
av_aligned = avatar_av_sync_metrics(
    [(1.00, 0.01), (1.02, 0.08)],
    [(0.98, 0.01), (1.14, 0.04), (1.18, 0.035)],
    max_skew_ms=250,
)
assert av_aligned["ok"] and av_aligned["skew_ms"] == 120.0
av_late = avatar_av_sync_metrics(
    [(1.00, 0.08)], [(1.40, 0.04), (1.44, 0.035)], max_skew_ms=250
)
assert not av_late["ok"] and av_late["reason"] == "av_skew"
av_missing = avatar_av_sync_metrics([(1.00, 0.08)], [], 250)
assert not av_missing["ok"] and av_missing["motion_diagnostics"]["samples"] == 0
av_idle_then_aligned = avatar_av_sync_metrics(
    [(2.00, 0.08)],
    [(1.76, 0.05), (1.90, 0.01), (2.06, 0.04)],
    max_skew_ms=250,
)
assert av_idle_then_aligned["ok"] and av_idle_then_aligned["skew_ms"] == 60.0
av_single_strong_frame = avatar_av_sync_metrics(
    [(3.00, 0.08)], [(3.078, 0.004), (3.109, 0.0382)], max_skew_ms=250,
)
assert av_single_strong_frame["ok"] and av_single_strong_frame["skew_ms"] == 109.0
av_subtle_sustained = avatar_av_sync_metrics(
    [(4.00, 0.08)],
    [(3.40, 0.003), (3.60, 0.004), (4.03, 0.0176), (4.10, 0.0155)],
    max_skew_ms=250,
)
assert av_subtle_sustained["ok"] and av_subtle_sustained["skew_ms"] == 30.0
av_quiet_syllable = avatar_av_sync_metrics(
    [(5.00, 0.08)],
    [(4.40, 0.0), (4.60, 0.001), (4.859, 0.0173), (4.890, 0.0082)],
    max_skew_ms=250,
)
assert av_quiet_syllable["ok"] and av_quiet_syllable["skew_ms"] == -141.0
av_quiet_voice = avatar_av_sync_metrics(
    [(6.00, 0.003), (6.02, 0.018), (6.04, 0.024)],
    [(6.00, 0.001), (6.04, 0.018), (6.08, 0.017)],
    max_skew_ms=250,
)
assert av_quiet_voice["ok"] and av_quiet_voice["skew_ms"] == 20.0
assert av_quiet_voice["audio_diagnostics"]["threshold"] == 0.012
av_video_lead_does_not_poison_idle_baseline = avatar_av_sync_metrics(
    [(10.00, 0.08)],
    [
        (9.25, 0.0223), (9.35, 0.0223), (9.45, 0.0223), (9.55, 0.0223),
        (9.65, 0.0223), (9.75, 0.0223), (9.80, 0.0223),
        (9.89, 0.0255), (9.921, 0.0118), (9.953, 0.0085),
        (10.00, 0.0150), (10.046, 0.0135), (10.078, 0.0194),
        (10.125, 0.0222), (10.156, 0.0134),
        (10.265, 0.0241), (10.312, 0.0295),
    ],
    max_skew_ms=300,
)
assert av_video_lead_does_not_poison_idle_baseline["ok"]
assert av_video_lead_does_not_poison_idle_baseline["skew_ms"] == 265.0
assert av_video_lead_does_not_poison_idle_baseline["motion_diagnostics"]["weak_threshold"] == 0.02
av_comfort_noise_only = avatar_av_sync_metrics(
    [(7.00, 0.003), (7.02, 0.008), (7.04, 0.009)],
    [(7.00, 0.02), (7.04, 0.02)],
    max_skew_ms=250,
)
assert not av_comfort_noise_only["ok"]
assert av_comfort_noise_only["reason"] == "no_audio_onset"
assert not avatar_playout_complete([(8.0, 0.08)], 2000, 10.2)
assert avatar_playout_complete([(8.0, 0.08)], 2000, 10.35)
assert not avatar_playout_complete([(8.0, 0.008)], 2000, 20.0)
fake_portrait = __import__("numpy").zeros((640, 640), dtype="uint8")
mouth_roi = avatar_mouth_roi(fake_portrait)
assert mouth_roi.shape == (108, 217)

# The release-facing path must exercise Voice -> Avatar direct PCM by default.
# Relay remains available as a fallback test, but cannot certify the primary route.
assert 'choices=("relay", "direct"), default="direct"' in SOURCE
assert 'parser.error("--expected-text is required with --mic-wav' in SOURCE
assert '"--expect-short-recovery", action="store_true"' in SOURCE
assert 'event.get("type") == "short_turn_recovery"' in SOURCE
assert 'metrics.get("short_turn_recovery") is True' in SOURCE
assert '"--mic-seconds", type=float, default=0.0' in SOURCE
assert "if self.args.mic_seconds > 0:" in SOURCE
assert "raw = source.readframes(frame_count)" in SOURCE
assert 'await self.avatar_feed.send(bytes(message))' in SOURCE
assert 'await self.avatar_feed.send("finish")' in SOURCE
assert '"asr_char_recall"' in SOURCE and '"first_response"' in SOURCE
assert '"no_unsolicited_repeat"' in SOURCE and '"source_playout"' in SOURCE
assert '"avatar_reported_underrun"' in SOURCE and '"avatar_health_after"' in SOURCE
assert '"avatar_webrtc_speech_timing"' in SOURCE
assert '"avatar_av_sync"' in SOURCE and 'track.kind == "video"' in SOURCE
assert '"avatar_route": metrics.get("avatar_ack") is True' in SOURCE
assert 'parser.add_argument("--turns", type=int, default=1)' in SOURCE
assert 'parser.add_argument("--prompts-json", default="")' in SOURCE
assert 'parser.add_argument("--prompts-b64", default="")' in SOURCE
assert 'parser.add_argument("--min-call-seconds", type=float, default=0)' in SOURCE
assert 'for turn_number in range(1, self.args.turns + 1):' in SOURCE
assert 'await self.wait_for_avatar_playout(' in SOURCE
assert '"avatar_playout_complete": avatar_playout_complete_for_turn' in SOURCE
assert '"avatar_playout": bool(metrics.get("turns"))' in SOURCE
assert '"call_id": str(getattr(error, "munea_call_id", "") or "")' in SOURCE
assert '"all_turns_completed"' in SOURCE and '"completed_turns"' in SOURCE
assert '"minimum_call_duration"' in SOURCE and '"call_duration_ms"' in SOURCE
assert 'self.args.turn_prompts[turn_number - 1]' in SOURCE
assert 'base64.b64decode(args.prompts_b64).decode("utf-8")' in SOURCE
assert 'raise RuntimeError("Voice disconnected after turn %d" % turn_number)' in SOURCE
assert 'await asyncio.sleep(15.0)' in SOURCE
assert '"/heartbeat"' in SOURCE and '"component": "app"' in SOURCE
assert 'run.heartbeat_task = asyncio.create_task(run.heartbeat_loop())' in SOURCE
assert '"gateway_heartbeat": bool(metrics.get("gateway_heartbeat", {}).get("ok"))' in SOURCE
assert 'self.test_credit_balance = max(' in SOURCE and '"balance": self.test_credit_balance' in SOURCE
assert 'all(metrics["gates"].values())' in SOURCE

WRAPPER = (ROOT / "scripts" / "fake_phone_e2e.py").read_text(encoding="utf-8")
assert 'sys.argv.extend(["--runs", "3"])' in WRAPPER
assert '"required_consecutive_runs"' in SOURCE and '"summary.json"' in SOURCE

print("Fake phone contract PASS: direct PCM, Gateway heartbeat, ASR, latency, continuity and multi-turn state gates")
