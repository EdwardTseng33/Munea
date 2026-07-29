#!/usr/bin/env python3
"""捏造天氣來源的出口攔截（2026-07-29 考卷 S03 抓到）。

**她真的犯規了**：劇本完全沒給天氣，她卻說「今天的天氣是晴時多雲喔，應該不會下雨」，
被追問還加碼「今天氣象報告說會是晴時多雲的好天氣」。

說明書早就寫了「不准捏造數字或事件」——她避開了數字，卻編了一個**狀態**跟一個**來源**，
自認沒違規。這正是「為了把話接圓滿而憑空填空」那個病的又一次發作。

兩層防護，這支守程式層：
  說明書層：講明白「沒有數字也算捏造」「引用你沒有的來源比講錯天氣更嚴重」
  程式層（這裡）：沒有今日簡報卻引用氣象來源＝可以確定判斷的假話，整句換掉

天氣**狀態**本身不硬擋——使用者自己說「外面在下雨」時她跟著講是對的，
那條靠說明書。程式層只擋「引用一個不存在的來源」這種怎麼看都是假的情形。
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import chat_engine as eng

HERE = os.path.dirname(os.path.abspath(__file__))


class GuardTest(unittest.TestCase):
    def test_citing_a_forecast_without_a_briefing_is_replaced(self):
        out, dropped = eng.strip_unbacked_forecast_source(
            "今天氣象報告說會是晴時多雲的好天氣。", has_briefing=False)
        self.assertEqual(dropped, ["今天氣象報告說會是晴時多雲的好天氣。"])
        self.assertIn("沒拿到天氣", out)

    def test_the_honest_line_comes_first(self):
        """先問「你要去菜市場嗎」才補一句沒拿到天氣，聽起來像答非所問。"""
        out, _ = eng.strip_unbacked_forecast_source(
            "今天氣象報告說不會下雨。您要去菜市場嗎？", has_briefing=False)
        self.assertTrue(out.startswith("我今天沒拿到天氣"))
        self.assertIn("菜市場", out, "把她關心他的那句一起砍掉了")

    def test_a_real_briefing_lets_her_talk_about_weather(self):
        text = "今天氣象報告說會下雨喔，記得帶傘。"
        self.assertEqual(eng.strip_unbacked_forecast_source(text, has_briefing=True), (text, []))

    def test_unknown_briefing_state_never_strips(self):
        """不知道有沒有簡報時寧可漏擋——把正確的話砍掉比漏擋更傷。"""
        text = "今天氣象報告說會下雨喔。"
        self.assertEqual(eng.strip_unbacked_forecast_source(text), (text, []))

    def test_weather_the_user_mentioned_is_not_touched(self):
        """使用者自己說在下雨，她跟著講是對的——程式層不碰狀態、只碰假來源。"""
        text = "外面在下雨喔，那你別出門，等雨停我再叫你。"
        self.assertEqual(eng.strip_unbacked_forecast_source(text, has_briefing=False), (text, []))

    def test_all_the_common_source_words_are_covered(self):
        for word in ("氣象報告", "氣象局", "氣象署", "天氣預報", "中央氣象"):
            out, dropped = eng.strip_unbacked_forecast_source(
                "聽說%s講今天會很熱。" % word, has_briefing=False)
            self.assertTrue(dropped, word)

    def test_empty_input_is_safe(self):
        self.assertEqual(eng.strip_unbacked_forecast_source("", has_briefing=False), ("", []))


class WiringTest(unittest.TestCase):
    """接線鎖：做了但沒接上正式線＝白做（2026-07-29 已經犯過五次）。"""

    def _read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_it_runs_inside_the_shared_exit(self):
        src = self._read("chat_engine.py")
        self.assertIn("strip_unbacked_forecast_source(cleaned, has_briefing=has_briefing)", src)

    def test_the_text_line_tells_it_whether_a_briefing_exists(self):
        """不傳 has_briefing＝永遠 None＝這道防護等於沒開。"""
        src = self._read("server.py")
        self.assertIn('has_briefing=bool((context or {}).get("dailyBriefing"))', src)

    def test_the_prompt_layer_also_names_the_failure_mode(self):
        src = self._read("chat_engine.py")
        self.assertIn("沒有數字也算捏造", src)
        self.assertIn("引用一個你沒有的來源比講錯天氣更嚴重", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
