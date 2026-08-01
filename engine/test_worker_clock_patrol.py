#!/usr/bin/env python3
"""顯卡時鐘巡邏（Edward 2026-08-01 拍板 A 案）

為什麼有這支：tw-06 的時鐘從 2026-07-23 起快了 257 秒，通話證被誤判過期＝整條通話全滅。
歪了 9 天沒人發現，最後是 Edward 自己看到打不通才追出來。7/24 其實就寫好了警報
（deploy/gateway/monitor.py），但那是要有人定時叫起來的巡邏，排程從沒建過。

這支驗的是輕量版巡邏的三件事：
  ① 時鐘歪超過警戒線一定要叫，而且是 critical（使用者當下打不進來）
  ② 「問不到時間」不可以當成「時鐘正常」——舊版的卡沒有回報欄位，那是量不到、不是沒事
  ③ 正常的時候要安靜，不能每次巡邏都洗版（狼來了幾次就沒人理了）
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "clock-patrol-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
os.environ["MUNEA_APP_KEY"] = "test-app-key"
os.environ["MUNEA_GATEWAY_ADMIN_KEY"] = "test-gateway-key"
os.environ["MUNEA_CALL_CONTROL_URL"] = "https://gateway.example"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402


def gateway_with(workers):
    return {"snapshot": {"workers": workers}}


class WorkerClockPatrolTests(unittest.TestCase):
    def setUp(self):
        self.alerts = []
        patcher = patch.object(
            server.notify, "alert",
            side_effect=lambda kind, where, detail="", critical=None: self.alerts.append(
                {"kind": kind, "where": where, "detail": detail, "critical": critical}
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, workers, skews):
        """skews: worker_id -> (差幾秒, 錯誤訊息)"""
        with patch.object(server, "_worker_clock_skew", side_effect=lambda url, key, timeout=8.0: skews[url]), \
             patch.object(server.urllib.request, "urlopen") as fake:
            fake.return_value.__enter__.return_value.read.return_value = json.dumps(
                gateway_with(workers)
            ).encode("utf-8")
            return server.worker_clock_patrol_response({})

    def test_quiet_when_every_clock_is_fine(self):
        out = self._run(
            [{"worker_id": "tw-06", "url": "https://tw-06.example"}],
            {"https://tw-06.example": (0.8, "")},
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["checked"], 1)
        self.assertEqual(out["offenders"], [])
        self.assertEqual(self.alerts, [], "時鐘正常還發警報＝洗版，幾次以後就沒人理了")

    def test_alerts_when_a_clock_is_too_far_off(self):
        out = self._run(
            [{"worker_id": "tw-06", "url": "https://tw-06.example"}],
            {"https://tw-06.example": (257.0, "")},
        )
        self.assertEqual(len(out["offenders"]), 1)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(self.alerts[0]["kind"], "gpu_down", "時鐘歪到通話證會過期＝使用者現在打不進來，要走 critical")
        self.assertIn("tw-06", self.alerts[0]["detail"])
        self.assertIn("257", self.alerts[0]["detail"])

    def test_alerts_when_the_clock_runs_slow_too(self):
        # 慢的一樣會讓憑證驗不過，方向不可以只擋一邊
        out = self._run(
            [{"worker_id": "tw-06", "url": "https://tw-06.example"}],
            {"https://tw-06.example": (-300.0, "")},
        )
        self.assertEqual(len(out["offenders"]), 1)
        self.assertEqual(len(self.alerts), 1)

    def test_just_under_the_line_stays_quiet(self):
        out = self._run(
            [{"worker_id": "tw-06", "url": "https://tw-06.example"}],
            {"https://tw-06.example": (89.0, "")},
        )
        self.assertEqual(out["offenders"], [])
        self.assertEqual(self.alerts, [])

    def test_unreadable_clock_is_not_treated_as_healthy(self):
        """舊版的卡沒有回報時間的欄位——那是「量不到」，不是「時鐘正常」。
        全部都問不到的時候要叫，不然這支巡邏會安靜地什麼都沒在巡。"""
        out = self._run(
            [{"worker_id": "tw-06", "url": "https://tw-06.example"}],
            {"https://tw-06.example": (None, "這張卡沒有回報自己的時間（舊版程式，重啟後才會有）")},
        )
        self.assertEqual(out["checked"], 0)
        self.assertEqual(len(out["unreadable"]), 1)
        self.assertEqual(len(self.alerts), 1)

    def test_one_unreadable_among_healthy_ones_does_not_cry_wolf(self):
        out = self._run(
            [
                {"worker_id": "tw-06", "url": "https://a.example"},
                {"worker_id": "tw-07", "url": "https://b.example"},
            ],
            {"https://a.example": (1.0, ""), "https://b.example": (None, "舊版")},
        )
        self.assertEqual(out["checked"], 1)
        self.assertEqual(len(out["unreadable"]), 1)
        self.assertEqual(self.alerts, [], "還有卡量得到就不必叫；那一台的狀況留在報告裡")

    def test_alerts_when_the_gateway_itself_is_unreachable(self):
        with patch.object(server.urllib.request, "urlopen", side_effect=OSError("boom")):
            out = server.worker_clock_patrol_response({})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "gateway_unreachable")
        self.assertEqual(len(self.alerts), 1)

    def test_threshold_matches_the_full_monitor(self):
        """完整版巡邏（deploy/gateway/monitor.py）的警戒線改了，這裡要一起改，
        否則兩支對同一件事會給出不同的答案。"""
        monitor = os.path.join(os.path.dirname(__file__), "..", "deploy", "gateway", "monitor.py")
        with open(monitor, encoding="utf-8") as source:
            text = source.read()
        self.assertIn(
            "DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS = %.1f" % server.WORKER_CLOCK_SKEW_THRESHOLD_SECONDS,
            text,
            "兩支巡邏的警戒線對不上了",
        )


if __name__ == "__main__":
    unittest.main()


class BrainKnowsTheGatewayTests(unittest.TestCase):
    """大腦要巡工作卡的時鐘，就得知道總機在哪。

    2026-08-01 首次掛巡邏時踩到：這個變數原本只設在語音那台，大腦沒有，
    接口回 gateway_or_key_missing——鬧鐘準時響、巡邏卻什麼都沒巡。

    ⚠ 一定要寫在部署腳本的清單裡，不能只在雲端手動加：下次部署會把手動加的清掉
    （2026-07-12 staging 全掛、07-29 租卡管家少三格，都是這個坑）。
    """

    def _deploy_script(self, name):
        path = os.path.join(os.path.dirname(__file__), "..", "deploy", "cloudrun", name)
        with open(path, encoding="utf-8") as source:
            return source.read()

    def test_uses_the_gateway_key_not_the_app_key(self):
        """兩把鑰匙不一樣：問總機要清單用 MUNEA_GATEWAY_ADMIN_KEY（Bearer），
        直接問某張卡用 MUNEA_APP_KEY（?key=）。2026-08-01 首掛時拿錯，
        被總機回 valid bearer token or client key required。"""
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(gateway_with([])).encode("utf-8")

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(getattr(request, "headers", {}) or {})
            return FakeResponse()

        with patch.object(server.urllib.request, "urlopen", side_effect=fake_urlopen):
            server.worker_clock_patrol_response({})
        auth = captured["headers"].get("Authorization", "")
        self.assertIn("test-gateway-key", auth, "問總機要用總機的鑰匙")
        self.assertNotIn("test-app-key", auth, "拿錯鑰匙會被總機擋在門外")

    def test_both_deploy_scripts_hand_the_brain_the_gateway_key(self):
        for name in ("canary-deploy.sh", "prod-deploy.sh"):
            path = os.path.join(os.path.dirname(__file__), "..", "deploy", "cloudrun", name)
            with open(path, encoding="utf-8") as source:
                text = source.read()
            brain_secrets = next(
                (l for l in text.splitlines() if "--update-secrets" in l and "MUNEA_ADMIN_PASSWORD" in l),
                "",
            )
            self.assertTrue(brain_secrets, "%s 找不到大腦的保險箱那一行" % name)
            self.assertIn(
                "MUNEA_GATEWAY_ADMIN_KEY=munea-gateway-admin-key", brain_secrets,
                "%s 的大腦拿不到總機鑰匙——巡邏會被總機擋下" % name,
            )

    def test_both_deploy_scripts_give_the_brain_the_gateway_url(self):
        for name, env_marker in (
            ("canary-deploy.sh", "MUNEA_ENV_NAME=staging"),
            ("prod-deploy.sh", "MUNEA_ENV_NAME=production"),
        ):
            text = self._deploy_script(name)
            brain_line = next(
                (line for line in text.splitlines() if env_marker in line and "MUNEA_APP_KEY" in line),
                "",
            )
            self.assertTrue(brain_line, "%s 找不到大腦的環境變數那一行" % name)
            self.assertIn(
                "MUNEA_CALL_CONTROL_URL=", brain_line,
                "%s 的大腦沒帶總機網址——時鐘巡邏會變成啞的" % name,
            )
