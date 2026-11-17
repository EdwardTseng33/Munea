#!/usr/bin/env python3
"""自我檢查門 /selftest/live 的守門測試（不連網路）。

背景：2026-11-08 重建時工具包自動升版，Gemini Live 連線被拒，正式聊聊四天打不通沒人知道。
這個門讓上線關卡與每日巡邏「真的接一次 Google」。這裡守住：
  - 沒帶對鑰匙一律 404，而且不會開線（不讓陌生人燒通話費）
  - 過＝200、不過＝503（上線工具靠狀態碼擋）
  - 60 秒內只真的跑一次
  - 連線被拒／沒聲音／卡住，都回報成失敗而不是丟例外，錯誤訊息不外洩鑰匙
  - 正式門口掛的是帶自我檢查的那一個
"""

import asyncio
import contextlib
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "selftest-unit-key")
os.environ.setdefault("MUNEA_DATABASE_PROVIDER", "json")


class _DummyClient:
    pass


with mock.patch("google.genai.Client", return_value=_DummyClient()):
    import live_voice_server as v


def _request(path, key=None, upgrade=None):
    headers = {}
    if key is not None:
        headers["X-Munea-Selftest-Key"] = key
    if upgrade:
        headers["Upgrade"] = upgrade
    return SimpleNamespace(path=path, headers=headers)


def _fake_connect(messages=None, raises=None, hang=False):
    class _Session:
        def __init__(self):
            self.sent = []

        async def send_client_content(self, **kwargs):
            self.sent.append(kwargs)

        async def receive(self):
            if hang:
                await asyncio.sleep(3600)
            for message in messages or []:
                yield message

    @contextlib.asynccontextmanager
    async def connect(model=None, config=None):
        if raises is not None:
            raise raises
        yield _Session()

    return connect


def _audio():
    return SimpleNamespace(data=b"\x01\x02", server_content=None)


def _turn_complete():
    return SimpleNamespace(data=None, server_content=SimpleNamespace(turn_complete=True))


class SelftestGateTests(unittest.TestCase):
    def setUp(self):
        v._selftest_cache.clear()
        v._selftest_lock = None

    def _call(self, request, runner_result=None):
        calls = []

        async def runner(mode):
            calls.append(mode)
            return dict(runner_result or {"ok": True, "mode": mode})

        async def go():
            with mock.patch.object(v, "run_live_selftest", runner), \
                    mock.patch.dict(os.environ, {"MUNEA_APP_KEY": "right-key"}):
                return await v.process_request_with_selftest(None, request)

        return asyncio.run(go()), calls

    def test_missing_or_wrong_key_is_404_and_never_opens_a_line(self):
        for key in (None, "", "wrong-key"):
            response, calls = self._call(_request("/selftest/live", key=key))
            self.assertEqual(response.status_code, 404)
            self.assertEqual(calls, [])

    def test_no_app_key_configured_means_closed(self):
        async def go():
            with mock.patch.dict(os.environ, {"MUNEA_APP_KEY": ""}):
                return await v.process_request_with_selftest(None, _request("/selftest/live", key=""))
        self.assertEqual(asyncio.run(go()).status_code, 404)

    def test_pass_is_200_and_fail_is_503(self):
        response, calls = self._call(_request("/selftest/live", key="right-key"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ["full"])
        self.assertTrue(json.loads(response.body.decode("utf-8"))["ok"])

        v._selftest_cache.clear()
        response, _ = self._call(_request("/selftest/live", key="right-key"),
                                 runner_result={"ok": False, "error": "InvalidStatus"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body.decode("utf-8"))["error"], "InvalidStatus")

    def test_light_mode_is_selected_by_query(self):
        _, calls = self._call(_request("/selftest/live?mode=light", key="right-key"))
        self.assertEqual(calls, ["light"])

    def test_other_paths_and_websocket_upgrades_are_untouched(self):
        response, calls = self._call(_request("/version"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [])
        response, calls = self._call(_request("/selftest/live", key="right-key", upgrade="websocket"))
        self.assertIsNone(response)
        self.assertEqual(calls, [])

    def test_repeat_within_a_minute_reuses_the_last_result(self):
        clock = {"t": 1000.0}
        calls = []

        async def runner(mode):
            calls.append(mode)
            return {"ok": True, "n": len(calls)}

        async def go():
            first = await v.live_selftest_cached("light", now=lambda: clock["t"], runner=runner)
            clock["t"] += 30
            second = await v.live_selftest_cached("light", now=lambda: clock["t"], runner=runner)
            clock["t"] += 31
            third = await v.live_selftest_cached("light", now=lambda: clock["t"], runner=runner)
            other = await v.live_selftest_cached("full", now=lambda: clock["t"], runner=runner)
            return first, second, third, other

        first, second, third, other = asyncio.run(go())
        self.assertNotIn("cached", first)
        self.assertTrue(second.get("cached"))
        self.assertEqual(second["n"], 1)
        self.assertEqual(third["n"], 2)
        self.assertEqual(other["n"], 3)          # full 與 light 各算各的
        self.assertEqual(calls, ["light", "light", "full"])


class SelftestRunTests(unittest.TestCase):
    def _run(self, **kwargs):
        timeout = kwargs.pop("timeout_s", 2.0)
        return asyncio.run(v.run_live_selftest("light", timeout_s=timeout, connect=_fake_connect(**kwargs)))

    def test_first_audio_means_pass(self):
        result = self._run(messages=[SimpleNamespace(data=None, server_content=None), _audio()])
        self.assertTrue(result["ok"])
        self.assertIn("first_audio_ms", result)
        self.assertEqual(result["model"], v.MODEL)

    def test_turn_finished_without_audio_is_a_failure(self):
        result = self._run(messages=[_turn_complete()])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_audio")

    def test_rejected_connection_is_reported_not_raised(self):
        boom = RuntimeError("server rejected WebSocket connection: HTTP 404 url=wss://x/?key=SECRETVALUE&alt=1")
        result = self._run(raises=boom)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "RuntimeError")
        self.assertIn("HTTP 404", result["detail"])
        self.assertNotIn("SECRETVALUE", result["detail"])

    def test_hanging_line_times_out(self):
        result = self._run(hang=True, timeout_s=0.2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "timeout")

    def test_slow_setup_runs_off_the_event_loop_and_inside_the_timeout(self):
        """整份設定會讀資料庫；讀慢了不可以卡住同一台主機上的通話，也不可以拖過逾時。"""
        import threading
        import time as _time
        seen = {}

        def slow_config(mode):
            seen["thread"] = threading.get_ident()
            _time.sleep(1.0)
            return object()

        async def go():
            loop_thread = threading.get_ident()
            ticks = 0

            async def heartbeat():
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.02)
                    ticks += 1

            beat = asyncio.create_task(heartbeat())
            started = _time.monotonic()
            with mock.patch.object(v, "_selftest_config", slow_config):
                result = await v.run_live_selftest("full", timeout_s=0.3, connect=_fake_connect(messages=[_audio()]))
            elapsed = _time.monotonic() - started
            beat.cancel()
            return result, elapsed, ticks, loop_thread

        result, elapsed, ticks, loop_thread = asyncio.run(go())
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "timeout")
        self.assertLess(elapsed, 0.8)                 # 沒有等滿那 1 秒
        self.assertGreaterEqual(ticks, 5)             # 等的時候事件迴圈照常在跑
        self.assertNotEqual(seen["thread"], loop_thread)

    def test_full_mode_uses_the_real_call_setup(self):
        config = v._selftest_config("full")
        self.assertTrue(config.system_instruction)
        self.assertTrue(config.tools)
        light = v._selftest_config("light")
        self.assertFalse(light.system_instruction)


class SelftestWiringTests(unittest.TestCase):
    def test_the_front_door_serves_the_selftest_aware_handler(self):
        source = Path(v.__file__).read_text(encoding="utf-8")
        self.assertIn("process_request=process_request_with_selftest", source)
        self.assertNotIn("process_request=process_request)", source)


if __name__ == "__main__":
    unittest.main()
