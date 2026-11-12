# -*- coding: utf-8 -*-
"""「說設好了卻沒去設」防線的單元測試（2026-11-13）。

背景：測試機實測 3.1 與 3.8 各約 10 通「幫我設提醒」，兩顆模型都有約兩成是嘴上說
「幫你記下來了／會提醒你」但那一輪沒有呼叫設定工具。這支測試鎖住判讀：
  ① 實測錄到的「已經設好」講法都要認得出來
  ② 還在問清楚、老實說做不到、跟提醒無關的話，不可以誤判
  ③ 補救提示要叫她「真的去設」或「老實說設不了」，而且不准唸出來

跑法：python engine/test_reminder_claim_guard.py（不需網路或真鑰匙）
"""
import os
import sys
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import live_voice_server as v  # noqa: E402

# 以下句子全部是 2026-11-13 測試機真實錄到的回答（那一輪都沒有呼叫工具）
CLAIMS = [
    "好，我幫你記下每天早上吃血糖藥的提醒，七點半提醒你囉。",
    "沒問題，我幫你記下來了。明天下午三點會提醒你量血壓喔。",
    "好，我幫你設定明天早上吃血壓藥的提醒囉。",
    "好，我幫你記下來囉，明天下午3點提醒你量血壓。",
    "來，明天下午三點我叫你量血壓喔。我已經幫你記在App裡了。",
    "好，都記起來了。明天早上8點記得吃血壓藥喔！我會準時提醒你的。",
]
NOT_CLAIMS = [
    "這個提醒我幫不上忙，我目前只支援看診或吃藥提醒喔。",
    "請告訴我您要設定的是哪種藥的名稱呢？",
    "要幫你設提醒沒問題，請問要設定的是哪一種藥呢？",
    "好的，王媽媽我幫你設晚餐後吃胃藥的提醒。是要每天長期吃，還是只有這次？",
    "聽起來膝蓋痛真的不太舒服，走路卡卡的肯定很不方便吧？",
    "記得吃完早餐後，再配水吃下去喔。",
    "你要不要用手機鬧鐘設一個提醒？",
    "",
]


class ReminderClaimGuardTests(unittest.TestCase):
    def test_recorded_claims_are_detected(self):
        for text in CLAIMS:
            self.assertTrue(v.reminder_claim_in(text), text)

    def test_questions_and_honest_declines_are_not_claims(self):
        for text in NOT_CLAIMS:
            self.assertEqual(v.reminder_claim_in(text), "", text)

    def test_cue_tells_her_to_really_set_it_or_say_she_cannot(self):
        cue = v.reminder_unfulfilled_cue("幫你記下來了")
        self.assertIn("絕對不要唸出這段", cue)
        self.assertIn("幫你記下來了", cue)
        self.assertIn("一定要呼叫設定提醒的工具", cue)
        self.assertIn("手機鬧鐘", cue)

    def test_only_real_write_tools_count_as_set(self):
        self.assertEqual(
            v._REMINDER_WRITE_TOOLS,
            frozenset({"set_clinic_reminder", "set_medication_reminder", "set_personal_event"}),
        )
        declared = {d.name for t in (v._REMINDER_TOOLS, v._EVENT_TOOLS) for d in t.function_declarations}
        self.assertTrue(v._REMINDER_WRITE_TOOLS <= declared, "防線認的工具名要真的存在")


if __name__ == "__main__":
    unittest.main(verbosity=2)
