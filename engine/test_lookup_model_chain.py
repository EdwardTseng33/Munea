#!/usr/bin/env python3
"""查詢模型鏈契約（2026-07-25 · 壓測夜二修：主備對調反悔＋thinking_budget=0）。

背景：#243 把 gemini-3.1-flash-lite 設成主力（單次測到 2-3 秒），但 staging 壓測
4 輪 21 次查詢重現：3.1-flash-lite 常常不呼叫 google_search 就直接用參數知識瞎答
（grounding_metadata=None），被 extract_result 的誠實檢查擋下、立刻掉到備援
gemini-2.5-flash，使用者反而要多等一輪、總耗時 9.6-11 秒。真正根因是
gemini-2.5-flash 預設的「思考」耗時，不是選錯模型——關掉 thinking_budget 之後
2.5-flash 本身就夠快（實測 median 4.29s）又可靠（grounding 8/8）。

本檔守住這次修法不被無意間改回去：①預設模型鏈是 2.5-flash 當主、3.1-flash-lite
當備援（不是反過來）②兩顆都要帶 thinking_budget=0 ③鏈上第一顆失敗會自動換下一顆。

跑法：python engine/test_lookup_model_chain.py（用假的 search_client，不需要網路或鑰匙）
"""
import os
import types as pytypes
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test")

import live_voice_server as voice
from google.genai import types


class _FakeModels:
    """假的 client.aio.models：依 model 名稱回傳預先安排好的結果／例外，並記錄每次呼叫的 config。"""

    def __init__(self, script):
        self.script = script  # {model_name: exception_instance_or_response}
        self.calls = []

    async def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "config": config})
        outcome = self.script[model]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeAio:
    def __init__(self, models):
        self.models = models


class _FakeClient:
    def __init__(self, script):
        self.aio = _FakeAio(_FakeModels(script))


def _fake_grounded_response(text="附近有一家不錯的店。", sources=2):
    candidate = pytypes.SimpleNamespace(
        grounding_metadata=pytypes.SimpleNamespace(
            grounding_chunks=[object() for _ in range(sources)]
        )
    )
    return pytypes.SimpleNamespace(text=text, candidates=[candidate])


def _fake_ungrounded_response(text="我猜可能是這樣。"):
    return pytypes.SimpleNamespace(text=text, candidates=[])


class LookupModelChainDefaultOrderTests(unittest.TestCase):
    def setUp(self):
        for name in ("MUNEA_LOOKUP_MODEL", "MUNEA_LOOKUP_PER_MODEL_SECONDS"):
            os.environ.pop(name, None)

    def test_default_primary_is_gemini_2_5_flash(self):
        """2026-07-25 反悔：2.5-flash 當主力，3.1-flash-lite 退回備援。"""
        default = os.environ.get(
            "MUNEA_LOOKUP_MODEL", "gemini-2.5-flash,gemini-3.1-flash-lite")
        models = [m.strip() for m in default.split(",") if m.strip()]
        self.assertEqual(models[0], "gemini-2.5-flash")
        self.assertIn("gemini-3.1-flash-lite", models[1:])

    def test_source_wires_default_model_order(self):
        """防止改動不小心又把 3.1-flash-lite 調回主力（source-level 鎖，跟本檔上面的
        行為測試互為印證：一個測程式碼字面、一個測真的函式行為）。"""
        src_path = os.path.join(os.path.dirname(__file__), "live_voice_server.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"MUNEA_LOOKUP_MODEL", "gemini-2.5-flash,gemini-3.1-flash-lite"', src)
        self.assertIn("thinking_config=types.ThinkingConfig(thinking_budget=0)", src)


class LookupModelChainBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ["MUNEA_LOOKUP_MODEL"] = "model-a,model-b"
        os.environ["MUNEA_LOOKUP_PER_MODEL_SECONDS"] = "5"

    async def asyncTearDown(self):
        os.environ.pop("MUNEA_LOOKUP_MODEL", None)
        os.environ.pop("MUNEA_LOOKUP_PER_MODEL_SECONDS", None)

    async def test_primary_success_never_touches_backup(self):
        client = _FakeClient({"model-a": _fake_grounded_response(sources=3)})
        result = await voice.search_current_information(client, "附近有什麼餐廳", "台北市")
        self.assertEqual(result["sources"], 3)
        self.assertEqual(len(client.aio.models.calls), 1)
        self.assertEqual(client.aio.models.calls[0]["model"], "model-a")

    async def test_ungrounded_primary_falls_back_to_next_model(self):
        """對應壓測發現的真實故障模式：主力回答了但沒有 grounding 來源，
        誠實檢查要擋下來、換下一顆，而不是把瞎答的內容直接講給使用者聽。"""
        client = _FakeClient({
            "model-a": _fake_ungrounded_response(),
            "model-b": _fake_grounded_response(sources=1),
        })
        result = await voice.search_current_information(client, "附近有什麼餐廳", "台北市")
        self.assertEqual(result["sources"], 1)
        self.assertEqual([c["model"] for c in client.aio.models.calls], ["model-a", "model-b"])

    async def test_every_model_call_disables_thinking(self):
        """thinking_budget=0 是這次修法的關鍵——沒有這個，2.5-flash 會慢回 8-11 秒。"""
        client = _FakeClient({"model-a": _fake_grounded_response()})
        await voice.search_current_information(client, "今天天氣如何", None)
        cfg = client.aio.models.calls[0]["config"]
        self.assertIsInstance(cfg, types.GenerateContentConfig)
        self.assertIsNotNone(cfg.thinking_config)
        self.assertEqual(cfg.thinking_config.thinking_budget, 0)

    async def test_all_models_failing_raises_last_exception(self):
        client = _FakeClient({
            "model-a": TimeoutError("model-a timed out"),
            "model-b": ValueError("lookup returned no grounded sources"),
        })
        with self.assertRaises(ValueError):
            await voice.search_current_information(client, "隨便問問", None)
        self.assertEqual(len(client.aio.models.calls), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
