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


normalize_transcript, transcript_char_recall, source_playout_metrics = load_functions(
    "normalize_transcript", "transcript_char_recall", "source_playout_metrics"
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

# The release-facing path must default to App relay, require a scored human WAV,
# and forward Voice binary PCM into Avatar's /audio websocket.
assert 'choices=("relay", "direct"), default="relay"' in SOURCE
assert 'parser.error("--expected-text is required with --mic-wav' in SOURCE
assert 'await self.avatar_feed.send(bytes(message))' in SOURCE
assert 'await self.avatar_feed.send("finish")' in SOURCE
assert '"asr_char_recall"' in SOURCE and '"first_response"' in SOURCE
assert '"no_unsolicited_repeat"' in SOURCE and '"source_playout"' in SOURCE
assert 'all(metrics["gates"].values())' in SOURCE

print("Fake phone contract PASS: real relay PCM, scored human ASR, latency and continuity gates")
