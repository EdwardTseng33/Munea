# -*- coding: utf-8 -*-
"""Gemini 換代守門（2026-11-18）。

1. TTS 聲音格式：3.8 TTS 回 WAV、舊預覽版回裸 PCM——兩種都要轉成 24kHz 單聲道 16-bit 裸 PCM，
   格式不對要回空的（呼叫端看到空的就換下一顆，不能把檔頭當聲音播出去）。
2. 停用的模型名稱不可以再出現在正式程式裡（註解除外）：
   gemini-2.5-flash（12/1 停）、gemini-2.0-flash（6/1 已停）、gemini-flash-latest（不知道指到哪顆）、
   gemini-2.5-flash-preview-tts／gemini-3.1-flash-tts-preview（12/18 停）。
3. 3.5-flash-lite 帶 thinking_budget 會回 400（11/18 實測），正式程式不可以再帶 thinking_budget。
"""
import io
import os
import re
import struct
import sys
import types as pytypes
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gemini_models  # noqa: E402

RETIRED = (
    "gemini-2.5-flash\"", "gemini-2.5-flash'", "gemini-2.5-flash,",
    "gemini-2.0-flash", "gemini-flash-latest",
    "gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview",
)
# 另一個工作階段正在換代並重量守護腦（A4），併入主線後把這一行拿掉
PENDING_ELSEWHERE = {"perception_engine.py"}


def _wav_bytes(rate=24000, channels=1, width=2, frames=b"\x01\x00\x02\x00\x03\x00"):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def _blob(data, mime):
    return pytypes.SimpleNamespace(data=data, mime_type=mime)


class TtsAudioTests(unittest.TestCase):
    def test_wav_from_38_tts_becomes_raw_pcm(self):
        frames = b"\x10\x00\x20\x00\x30\x00\x40\x00"
        pcm = gemini_models.pcm24k_from_inline(_blob(_wav_bytes(frames=frames), "audio/wav"))
        self.assertEqual(pcm, frames)

    def test_raw_l16_from_old_preview_passes_through(self):
        raw = b"\x01\x02\x03\x04"
        self.assertEqual(gemini_models.pcm24k_from_inline(_blob(raw, "audio/L16;codec=pcm;rate=24000")), raw)

    def test_wrong_rate_or_channels_is_rejected_not_played(self):
        self.assertEqual(gemini_models.pcm24k_from_inline(_blob(_wav_bytes(rate=16000), "audio/wav")), b"")
        self.assertEqual(gemini_models.pcm24k_from_inline(_blob(_wav_bytes(channels=2), "audio/wav")), b"")
        self.assertEqual(gemini_models.pcm24k_from_inline(_blob(b"\x01\x02", "audio/L16;codec=pcm;rate=16000")), b"")
        self.assertEqual(gemini_models.pcm24k_from_inline(_blob(b"\x01\x02", "audio/mpeg")), b"")

    def test_empty_or_missing_blob(self):
        self.assertEqual(gemini_models.pcm24k_from_inline(None), b"")
        self.assertEqual(gemini_models.pcm24k_from_inline(_blob(b"", "audio/wav")), b"")

    def test_odd_sized_chunk_before_data_is_skipped(self):
        frames = b"\x05\x00\x06\x00"
        wav = _wav_bytes(frames=frames)
        # 在 fmt 跟 data 中間插一個奇數長度的 LIST chunk（RIFF 規定要補一個位元組）
        fmt_end = wav.index(b"data")
        extra = b"LIST" + struct.pack("<I", 3) + b"abc" + b"\x00"
        patched = wav[:fmt_end] + extra + wav[fmt_end:]
        patched = patched[:4] + struct.pack("<I", len(patched) - 8) + patched[8:]
        self.assertEqual(gemini_models.pcm24k_from_inline(_blob(patched, "audio/wav")), frames)

    def test_defaults(self):
        self.assertEqual(gemini_models.TEXT_MODELS[0], "gemini-3.5-flash-lite")
        self.assertIn("gemini-3.1-flash-lite", gemini_models.TEXT_MODELS)
        self.assertEqual(gemini_models.TTS_MODELS[0], "gemini-3.8-flash-tts")


def _code_lines(path):
    """去掉註解與 docstring 粗略版：只看不是以 # 開頭、也不在三引號區塊裡的行。"""
    out = []
    in_doc = False
    with io.open(path, encoding="utf-8") as f:
        for no, line in enumerate(f, 1):
            stripped = line.strip()
            quotes = stripped.count('"""') + stripped.count("'''")
            if in_doc:
                if quotes % 2 == 1:
                    in_doc = False
                continue
            if stripped.startswith(('"""', "'''")) and quotes % 2 == 1:
                in_doc = True
                continue
            if stripped.startswith("#"):
                continue
            out.append((no, line.split(" #", 1)[0]))
    return out


class RetiredModelGuardTests(unittest.TestCase):
    def _engine_files(self):
        for name in sorted(os.listdir(HERE)):
            if name.endswith(".py") and not name.startswith("test_") and name not in PENDING_ELSEWHERE:
                yield name, os.path.join(HERE, name)

    def test_no_retired_model_names_in_live_code(self):
        hits = []
        for name, path in self._engine_files():
            for no, code in _code_lines(path):
                if any(r in code for r in RETIRED):
                    hits.append(f"{name}:{no}: {code.strip()[:90]}")
        self.assertEqual(hits, [], "還在用停用（或即將停用）的模型：\n" + "\n".join(hits))

    def test_no_thinking_budget_in_live_code(self):
        hits = []
        for name, path in self._engine_files():
            for no, code in _code_lines(path):
                if re.search(r"thinking_budget\s*=", code):
                    hits.append(f"{name}:{no}: {code.strip()[:90]}")
        self.assertEqual(hits, [], "3.5-flash-lite 帶 thinking_budget 會回 400，改用 thinking_level：\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main(verbosity=2)
