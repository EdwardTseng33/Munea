# -*- coding: utf-8 -*-
"""語音引擎選擇契約（2026-11-12）。

背景：Google 官方停用頁寫 gemini-3.1-flash-live-preview 最早 2026-11-17 關閉，
接替者是 gemini-3.8-live。這支測試鎖住三件事：

  ① 沒設環境變數 → 仍是 31／3.1（正式機零改變，切換要明確動手）
  ② MUNEA_VOICE_ENGINE=38 → 模型換成 gemini-3.8-live，且走開發者鑰匙那條路（不是 Vertex）
  ③ 寫錯字一律退回 31，不可以炸掉通話

模型名在模組載入時就決定，所以每個情境各開一個乾淨的子行程來驗。
跑法：python engine/test_voice_engine_select.py（不需網路或真鑰匙）
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SNIPPET = "import live_voice_server as v; print(v.VOICE_ENGINE + '|' + v.MODEL)"


def _resolve(engine=None, override=None):
    env = dict(os.environ, GEMINI_API_KEY="test", PYTHONIOENCODING="utf-8")
    env.pop("MUNEA_VOICE_ENGINE", None)
    env.pop("MUNEA_VOICE_MODEL_OVERRIDE", None)
    if engine is not None:
        env["MUNEA_VOICE_ENGINE"] = engine
    if override is not None:
        env["MUNEA_VOICE_MODEL_OVERRIDE"] = override
    out = subprocess.run([sys.executable, "-c", SNIPPET], cwd=HERE, env=env,
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-600:])
    return tuple(out.stdout.strip().splitlines()[-1].split("|"))


class VoiceEngineSelectTests(unittest.TestCase):
    def test_default_stays_31(self):
        self.assertEqual(_resolve(), ("31", "gemini-3.1-flash-live-preview"))

    def test_38_selects_gemini_38_live(self):
        for value in ("38", "live38", "3.8", " 38 "):
            self.assertEqual(_resolve(value), ("38", "gemini-3.8-live"), value)

    def test_38_model_override(self):
        self.assertEqual(_resolve("38", "gemini-3.8-live-extended-thinking"),
                         ("38", "gemini-3.8-live-extended-thinking"))

    def test_typo_falls_back_to_31(self):
        self.assertEqual(_resolve("3,8"), ("31", "gemini-3.1-flash-live-preview"))
        self.assertEqual(_resolve("gemini38"), ("31", "gemini-3.1-flash-live-preview"))

    def test_38_is_not_vertex(self):
        # 38 走開發者鑰匙；_make_client 只有 vertex25 才走 Google 雲身分。
        env = dict(os.environ, GEMINI_API_KEY="test", MUNEA_VOICE_ENGINE="38", PYTHONIOENCODING="utf-8")
        code = ("import live_voice_server as v; c = v._make_client('test'); "
                "print(bool(getattr(c, 'vertexai', False) or getattr(getattr(c, '_api_client', None), 'vertexai', False)))")
        out = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False")


if __name__ == "__main__":
    unittest.main(verbosity=2)
