# -*- coding: utf-8 -*-
"""後台登入提速（2026-10-26）的守門：讀接口 60 秒快取、寫入清快取、gzip 與保鮮標籤。

為什麼要守：快取這種東西「壞了沒聲音」——數字舊了沒人會發現，直到 Edward 發完點數畫面不動。
所以這裡釘死四件事：① 雲端環境才開、本機／測試永遠現算 ② 同參數才算同一份 ③ 任何 /admin/ 寫入
動作之後一定重算 ④ 按重新整理（fresh）一定重算。
"""
import gzip
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("GEMINI_API_KEY", "test-key")  # server 載入時要有、這裡不會真的打 AI
import server  # noqa: E402


class _Counter:
    def __init__(self):
        self.calls = 0

    def produce(self):
        self.calls += 1
        return {"ok": True, "value": self.calls}


class ReadCacheTests(unittest.TestCase):
    def setUp(self):
        server.admin_read_cache_clear()

    def test_local_and_test_environments_never_cache(self):
        counter = _Counter()
        with patch.dict(os.environ, {"MUNEA_ENV_NAME": "", "MUNEA_ADMIN_READ_CACHE_SECONDS": ""}):
            first = server.admin_cached_read("munea.admin.usage.v1", {"days": 30}, counter.produce)
            second = server.admin_cached_read("munea.admin.usage.v1", {"days": 30}, counter.produce)
        self.assertEqual(counter.calls, 2)
        self.assertNotIn("cache", first)
        self.assertNotIn("cache", second)

    def test_cloud_environment_serves_same_params_from_cache(self):
        counter = _Counter()
        with patch.dict(os.environ, {"MUNEA_ENV_NAME": "production", "MUNEA_ADMIN_READ_CACHE_SECONDS": ""}):
            first = server.admin_cached_read("munea.admin.usage.v1", {"days": 30}, counter.produce)
            second = server.admin_cached_read("munea.admin.usage.v1", {"days": 30}, counter.produce)
            other = server.admin_cached_read("munea.admin.usage.v1", {"days": 7}, counter.produce)
        self.assertEqual(counter.calls, 2, "同參數第二次要吃快取、不同參數要現算")
        self.assertEqual(first["value"], second["value"])
        self.assertTrue(second["cache"]["hit"])
        self.assertNotIn("cache", other)
        # 快取回的是拷貝：呼叫端改了不會污染下一位
        second["value"] = "污染"
        third = server.admin_cached_read("munea.admin.usage.v1", {"days": 30}, counter.produce)
        self.assertEqual(third["value"], 1)

    def test_fresh_flag_bypasses_cache_and_is_not_part_of_key(self):
        counter = _Counter()
        with patch.dict(os.environ, {"MUNEA_ENV_NAME": "staging"}):
            server.admin_cached_read("munea.admin.usage.v1", {"days": 30}, counter.produce)
            refreshed = server.admin_cached_read("munea.admin.usage.v1", {"days": 30, "fresh": True}, counter.produce)
            again = server.admin_cached_read("munea.admin.usage.v1", {"days": 30}, counter.produce)
        self.assertEqual(counter.calls, 2)
        self.assertNotIn("cache", refreshed)
        self.assertEqual(again["value"], 2, "fresh 現算的那份要取代舊快取")

    def test_admin_write_clears_cache(self):
        counter = _Counter()
        with patch.dict(os.environ, {"MUNEA_ENV_NAME": "production"}):
            server.admin_cached_read("munea.admin.accounts.v1", {"limit": 50}, counter.produce)
            server.admin_read_cache_clear()
            server.admin_cached_read("munea.admin.accounts.v1", {"limit": 50}, counter.produce)
        self.assertEqual(counter.calls, 2)

    def test_failed_payload_is_not_cached(self):
        calls = []

        def failing():
            calls.append(1)
            return {"ok": False, "error": "boom"}

        with patch.dict(os.environ, {"MUNEA_ENV_NAME": "production"}):
            server.admin_cached_read("munea.admin.usage.v1", {}, failing)
            server.admin_cached_read("munea.admin.usage.v1", {}, failing)
        self.assertEqual(len(calls), 2)

    def test_every_console_read_path_is_in_cache_set(self):
        # EP_LIST（web/src/admin.js）列的 15 支讀接口都要在快取名單裡，否則登入後那幾支還是每次現算
        here = os.path.dirname(os.path.abspath(__file__))
        js = open(os.path.join(here, "..", "web", "src", "admin.js"), encoding="utf-8").read()
        block = js.split("const EP_LIST = {", 1)[1].split("};", 1)[0]
        paths = {line.split('"')[1] for line in block.splitlines() if '["/admin/' in line}
        self.assertEqual(paths, set(server.ADMIN_READ_CACHE_PATHS))


class _FakeHandler(server.H):
    """只借 _send，不開真的 socket。"""

    def __init__(self, path, headers):
        self.path = path
        self.headers = headers
        self.wfile = io.BytesIO()
        self.sent_headers = {}
        self.status = None

    def send_response(self, code):
        self.status = code

    def send_header(self, name, value):
        self.sent_headers.setdefault(name, []).append(str(value))

    def end_headers(self):
        pass


class SendHeadersTests(unittest.TestCase):
    def test_gzip_when_browser_accepts_and_body_is_text(self):
        body = ("x" * 4000).encode()
        h = _FakeHandler("/admin/usage", {"Accept-Encoding": "gzip, deflate, br"})
        h._send(200, "application/json; charset=utf-8", body)
        self.assertEqual(h.sent_headers["Content-Encoding"], ["gzip"])
        self.assertIn("Accept-Encoding", h.sent_headers["Vary"])
        self.assertEqual(gzip.decompress(h.wfile.getvalue()), body)
        self.assertEqual(h.sent_headers["Content-Length"], [str(len(h.wfile.getvalue()))])

    def test_no_gzip_for_small_bodies_images_or_clients_without_support(self):
        small = _FakeHandler("/admin/usage", {"Accept-Encoding": "gzip"})
        small._send(200, "application/json; charset=utf-8", b'{"ok":true}')
        self.assertNotIn("Content-Encoding", small.sent_headers)
        image = _FakeHandler("/icons/x.png", {"Accept-Encoding": "gzip"})
        image._send(200, "image/png", b"\x89PNG" * 2000)
        self.assertNotIn("Content-Encoding", image.sent_headers)
        plain = _FakeHandler("/admin/usage", {})
        plain._send(200, "application/json; charset=utf-8", b"x" * 4000)
        self.assertNotIn("Content-Encoding", plain.sent_headers)
        self.assertEqual(plain.wfile.getvalue(), b"x" * 4000)

    def test_cache_control_only_relaxed_for_versioned_admin_assets(self):
        self.assertEqual(server.static_cache_control("/src/admin.js?v=ops105-login-speed"), "public, max-age=3600")
        self.assertEqual(server.static_cache_control("/src/i18n/admin-en.json?v=1"), "public, max-age=3600")
        # 沒帶版本號／後台首頁／App 本體／接口：一律維持每次回源頭驗
        for path in ("/src/admin.js", "/admin.html?v=1", "/src/app.js?v=1", "/admin/usage", "/index.html", ""):
            self.assertEqual(server.static_cache_control(path), "no-cache, must-revalidate", path)


if __name__ == "__main__":
    unittest.main()
