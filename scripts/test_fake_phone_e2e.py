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


normalize_transcript, transcript_char_recall, source_playout_metrics, webrtc_frame_timing_metrics, webrtc_speech_gap_metrics, avatar_av_sync_metrics = load_functions(
    "normalize_transcript", "transcript_char_recall", "source_playout_metrics",
    "webrtc_frame_timing_metrics", "webrtc_speech_gap_metrics", "avatar_av_sync_metrics"
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

# The release-facing path must exercise Voice -> Avatar direct PCM by default.
# Relay remains available as a fallback test, but cannot certify the primary route.
assert 'choices=("relay", "direct"), default="direct"' in SOURCE
assert 'parser.error("--expected-text is required with --mic-wav' in SOURCE
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
assert '"all_turns_completed"' in SOURCE and '"completed_turns"' in SOURCE
assert '"minimum_call_duration"' in SOURCE and '"call_duration_ms"' in SOURCE
assert 'self.args.turn_prompts[turn_number - 1]' in SOURCE
assert 'base64.b64decode(args.prompts_b64).decode("utf-8")' in SOURCE
assert 'raise RuntimeError("Voice disconnected after turn %d" % turn_number)' in SOURCE
assert 'all(metrics["gates"].values())' in SOURCE

WRAPPER = (ROOT / "scripts" / "fake_phone_e2e.py").read_text(encoding="utf-8")
assert 'sys.argv.extend(["--runs", "3"])' in WRAPPER
assert '"required_consecutive_runs"' in SOURCE and '"summary.json"' in SOURCE

print("Fake phone contract PASS: direct PCM, ASR, latency, continuity and multi-turn state gates")
