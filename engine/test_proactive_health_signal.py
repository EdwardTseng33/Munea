#!/usr/bin/env python3
"""會看變化的主動關心（2026-07-31 · 調研排第一的那一項）。

**為什麼**：三路調研的結論——「主動關懷由數據觸發」是唯一有真實規模部署＋
正向實證的方向（韓國 CareCall 近三千人、Sensi.AI 讓住院率降 22%），
而且照顧者買的是「有東西幫我盯著」的安心，不是數據本身。

**但這一版刻意只做一半**：身體數據跟平常不一樣時，她多關心一點、語氣放輕——
**不講原因、不報數字**。這守的是 2026-07-17 Edward 拍的「檔位2 知道但不多嘴」：
身體數據異常是家人在看的，不是她拿來嚇長輩的。

要讓她講出「因為你血壓連三天偏高所以我打來」是另一件事，要 Edward 重新定調。
這支測試就是那條界線的守衛——哪天有人讓她開口報數字，這裡要先紅。
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import server

HERE = os.path.dirname(os.path.abspath(__file__))


class ScoringTest(unittest.TestCase):
    """訊號要真的影響「要不要主動開口」，不是做了沒接上。"""

    def _run(self, notable, health_ctx_error=False):
        """只驗計分那一段——周邊資料來源與模型呼叫全部隔離，測試不碰網路。"""
        ctx = (mock.patch.object(server, "load_health_context", side_effect=RuntimeError("boom"))
               if health_ctx_error else
               mock.patch.object(server, "load_health_context",
                                 return_value={"facts": [], "notable": notable}))
        with ctx,              mock.patch.object(server, "load_wellbeing_signals", return_value=[]),              mock.patch.object(server, "_latest_daily_briefing", return_value={}),              mock.patch.object(server, "today_care_items", return_value=[]),              mock.patch.object(server, "count_today_proactive_opens", return_value=0,
                               create=True),              mock.patch.object(server.eng, "open_chat", return_value="（測試用開場）"):
            return server.proactive_opening_response({"personId": "p-test"})

    def test_notable_signal_raises_the_score(self):
        quiet = self._run([])
        noisy = self._run(["bpSys"])
        self.assertGreater(noisy["score"], quiet["score"],
                           "身體數據跑掉了，主動關心的分數卻沒動＝這條沒接上")

    def test_notable_signal_softens_the_tone(self):
        self.assertEqual(self._run(["bpSys"])["style"], "gentle")

    def test_the_reason_is_recorded_for_the_operator(self):
        reasons = " ".join(self._run(["bpSys"])["reasons"])
        self.assertIn("身體數據跟平常不太一樣", reasons)

    def test_a_broken_health_context_never_blocks_the_opener(self):
        """讀不到身體資料就當沒有——絕不能因此讓她整個不開口。"""
        res = self._run([], health_ctx_error=True)
        self.assertTrue(res.get("ok"))


class QuietDisciplineTest(unittest.TestCase):
    """檔位2 的界線：知道，但不多嘴。"""

    def test_the_operator_reason_promises_not_to_say_why(self):
        reasons = " ".join(ScoringTest()._run(["bpSys"])["reasons"])
        self.assertIn("不點破原因", reasons)

    def test_the_wiring_comment_names_the_july_17_ruling(self):
        """這條界線是拍板來的，不是我隨手定的——註解要留住那個出處，
        免得日後有人「順手」讓她開口報數字。"""
        with open(os.path.join(HERE, "server.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("只調頻率與語氣、不講原因、\n    # 不報數字", src)
        self.assertIn("檔位2 知道但不多嘴", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
