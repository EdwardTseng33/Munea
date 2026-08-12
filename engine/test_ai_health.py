#!/usr/bin/env python3
"""「她還講不講得出話」契約（2026-07-29 · 當晚事故後立刻補）。

**這支為什麼存在**：今晚模型鑰匙的預付額度用完，正式機的大腦跟聊聊**兩台都啞了**——
真的用戶打不通、也聊不了。而八個服務的巡邏燈**全是綠的**。

因為巡邏只問「機器有沒有回應」，不問「她還講不講得出話」。
機器活著、程式沒壞、網頁回 200——但她一個字都吐不出來。
**服務看起來健康、用戶其實被晾在那裡，這比壞掉更可怕：沒有人會知道。**

這支釘住的核心判斷：**「不知道」不等於「沒事」。**
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import ai_health

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = 1_800_000_000.0


class VerdictTest(unittest.TestCase):
    def setUp(self):
        ai_health.reset_for_test()

    def test_never_called_is_unknown_not_ok(self):
        """從來沒叫過模型＝不知道。回 ok 就是今晚那個錯。"""
        st = ai_health.status(now=NOW, allow_probe=False)
        self.assertEqual(st["state"], ai_health.STATE_UNKNOWN)
        self.assertFalse(st["ok"], "「不知道」被當成「沒事」——這正是今晚沒人發現的原因")

    def test_a_real_successful_reply_counts_as_alive(self):
        ai_health.record_success(now=NOW)
        st = ai_health.status(now=NOW + 60, allow_probe=False)
        self.assertTrue(st["ok"])
        self.assertEqual(st["lastOkAgoS"], 60)

    def test_one_failure_is_not_yet_down(self):
        """單次網路抖動不算倒——誤報幾次以後就沒人理告警了。"""
        ai_health.record_success(now=NOW)
        ai_health.record_failure("429 一次", now=NOW + 10)
        self.assertNotEqual(ai_health.status(now=NOW + 20, allow_probe=False)["state"],
                            ai_health.STATE_DOWN)

    def test_repeated_failures_are_down(self):
        for i in range(ai_health.DOWN_AFTER_FAILURES):
            ai_health.record_failure("429 RESOURCE_EXHAUSTED", now=NOW + i)
        st = ai_health.status(now=NOW + 30, allow_probe=False)
        self.assertEqual(st["state"], ai_health.STATE_DOWN)
        self.assertFalse(st["ok"])
        self.assertIn("RESOURCE_EXHAUSTED", st["lastError"])

    def test_success_clears_the_failure_streak(self):
        ai_health.record_failure("x", now=NOW)
        ai_health.record_failure("x", now=NOW + 1)
        ai_health.record_success(now=NOW + 2)
        self.assertTrue(ai_health.status(now=NOW + 3, allow_probe=False)["ok"])

    def test_going_quiet_for_too_long_is_unknown_not_ok(self):
        """太久沒有真流量就不能再拿舊的成功當保證。"""
        ai_health.record_success(now=NOW)
        st = ai_health.status(now=NOW + ai_health.CHECK_IDLE_S + 60, allow_probe=False)
        self.assertEqual(st["state"], ai_health.STATE_UNKNOWN)
        self.assertFalse(st["ok"])

    def test_error_detail_is_truncated_not_dumped(self):
        ai_health.record_failure("x" * 999, now=NOW)
        self.assertLessEqual(len(ai_health.status(now=NOW, allow_probe=False)["lastError"]), 200)


class CostTest(unittest.TestCase):
    """巡邏每 5 分鐘一輪——這道檢查不可以每輪都燒錢。"""

    def setUp(self):
        ai_health.reset_for_test()

    def test_real_traffic_means_no_probe_at_all(self):
        """有人在用的時候搭便車就好，零成本。"""
        ai_health.record_success(now=NOW)
        self.assertFalse(ai_health.status(now=NOW + 60)["probed"])

    def test_probe_result_is_cached_between_rounds(self):
        calls = []
        original = ai_health._probe
        ai_health._probe = lambda: (calls.append(1), ai_health.record_failure("測試"))[0]
        try:
            ai_health.status(now=NOW)                                   # 探一次
            ai_health.status(now=NOW + 300, allow_probe=True)           # 5 分鐘後：吃快取
            ai_health.status(now=NOW + 600, allow_probe=True)           # 10 分鐘後：吃快取
        finally:
            ai_health._probe = original
        self.assertEqual(len(calls), 1, "巡邏每一輪都去燒一次錢")


class WiringTest(unittest.TestCase):
    """接線鎖：做了但沒接上＝白做（2026-07-29 已經犯過六次）。"""

    def _read(self, path):
        with open(os.path.join(HERE, path), encoding="utf-8") as f:
            return f.read()

    def test_brain_reports_it_in_healthz(self):
        src = self._read("server.py")
        self.assertIn("import ai_health", src)
        self.assertIn('"ai": ai_health.status()', src)

    def test_a_real_reply_records_success(self):
        self.assertIn("ai_health.record_success()", self._read("server.py"))

    def test_model_failures_are_recorded(self):
        src = self._read("server.py")
        self.assertIn("ai_health.record_failure(", src)

    def test_the_watchdog_actually_looks_at_it(self):
        """巡邏燈沒去看那一格＝這整支白做，今晚的事會再發生一次。"""
        src = self._read(os.path.join("..", "scripts", "service-watchdog.mjs"))
        self.assertIn('check: "ai-alive"', src)
        self.assertIn("ai.ok !== true", src)

    def test_being_mute_wakes_someone_up(self):
        """她講不出話＝使用者現在打不通，告警必須穿得透手機免打擾。"""
        src = self._read(os.path.join("..", "scripts", "service-watchdog.mjs"))
        block = src.split('check: "ai-alive"', 1)[1][:200]
        self.assertIn("userFacing: true", block)

    def test_an_old_deployment_without_the_field_is_not_a_false_alarm(self):
        """升級期間舊版沒有 ai 那格，不能因此亂叫。"""
        self.assertIn("沒有 ai 這格＝跑的是舊版",
                      self._read(os.path.join("..", "scripts", "service-watchdog.mjs")))



class RecoveryIsReportedTest(unittest.TestCase):
    """壞掉會講、**好了也要會講**（2026-08-12 · Edward 儲值後儀表仍卡在 down 16 小時）。

    原本只有 unknown 才自己探一次，判成 down 之後就再也不探——所以額度補回來、
    鑰匙實測也通了，儀表還是寫著 down。只會報壞消息的儀表，跟壞掉的儀表一樣不能信。
    """

    def setUp(self):
        ai_health.reset_for_test()

    def test_a_down_verdict_still_probes_and_can_recover(self):
        for _ in range(ai_health.DOWN_AFTER_FAILURES):
            ai_health.record_failure("額度用完")
        self.assertEqual(ai_health.status(allow_probe=False)["state"], "down")

        calls = []
        real = ai_health._probe
        def fake_probe():
            calls.append(1)
            ai_health.record_success()
            return True
        ai_health._probe = fake_probe
        try:
            out = ai_health.status()
        finally:
            ai_health._probe = real
        self.assertTrue(calls, "判成 down 之後就不再探了——永遠不會知道已經好了")
        self.assertTrue(out["probed"])
        self.assertEqual(out["state"], "ok")
        self.assertTrue(out["ok"])

    def test_still_down_when_the_probe_also_fails(self):
        for _ in range(ai_health.DOWN_AFTER_FAILURES):
            ai_health.record_failure("額度用完")
        real = ai_health._probe
        ai_health._probe = lambda: (ai_health.record_failure("還是不行"), False)[1]
        try:
            out = ai_health.status()
        finally:
            ai_health._probe = real
        self.assertEqual(out["state"], "down", "探了還是失敗就該繼續說壞")
        self.assertFalse(out["ok"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
