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
    # 強制測試（不給她設提醒的工具）錄到的三句
    "好，明天早上八點吃血壓藥的時間，我已經幫你設好囉。",
    "好，我記下來了，明天下午三點會提醒您量血壓。",
    "沒問題，我會幫你記下每天早上七點半吃血糖藥的這件事，時間到我會提醒你喔。",
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
    # 2026-11-13 測試機誤判過的詢問／提議句——這些不是「已經做了」
    "血壓藥千萬不能自己停掉喔！這要請醫師或藥師評估，我幫妳記下來，回診時再問他們好嗎？",
    "您要不要我幫您記著，下次回診時問清楚呢？",
    "要不要我幫你記下這個問題，下次回診時問醫生呢？",
    "如果你有這方面的疑問，我們可以先記下來，下次回診時問醫生，你覺得好嗎？",
    "需不需要我幫你設個提醒，提醒自己記得熱敷休息呢？",
    "一定要先請教醫師或藥師，我也可以幫你記下來下次問醫生。",
]


class ReminderClaimGuardTests(unittest.TestCase):
    def test_recorded_claims_are_detected(self):
        for text in CLAIMS:
            self.assertTrue(v.reminder_claim_in(text), text)

    def test_questions_and_honest_declines_are_not_claims(self):
        for text in NOT_CLAIMS:
            self.assertEqual(v.reminder_claim_in(text), "", text)
            self.assertEqual(v.note_claim_in(text), "", text)

    def test_cue_tells_her_to_really_set_it_or_say_she_cannot(self):
        cue = v.reminder_unfulfilled_cue("幫你記下來了")
        self.assertIn("絕對不要唸出這段", cue)
        self.assertIn("幫你記下來了", cue)
        self.assertIn("一定要呼叫設定提醒的工具", cue)
        self.assertIn("記錄問題的工具", cue)
        self.assertIn("手機鬧鐘", cue)

    def test_note_claims_cover_non_reminder_writes(self):
        # 考卷 S59：要問醫生的清單滿了，她卻說「我會幫你記著喔」
        self.assertTrue(v.note_claim_in("下次看診確實可以問問醫生的建議，我會幫你記著喔。"))
        self.assertTrue(v.note_claim_in("好，我幫你記下來了。"))
        self.assertEqual(v.note_claim_in("醫生要問的問題清單目前滿了喔。要不要先拿掉其中一題？"), "")
        self.assertEqual(v.note_claim_in("你記得要吃完早餐再吃藥喔。"), "")

    def test_write_failed_cue_asks_for_honesty_and_a_next_step(self):
        cue = v.write_failed_cue("我會幫你記著")
        self.assertIn("絕對不要唸出這段", cue)
        self.assertIn("沒有存成功", cue)
        self.assertIn("做得到的下一步", cue)

    def test_turn_end_queues_one_correction_and_resets(self):
        st = {"turn_ai_text": "好，明天早上八點吃血壓藥的時間，我已經幫你設好囉。"}
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=100.0), "reminder")
        self.assertIn("還沒有任何東西真的存成功", st["pending_promise_cue"])
        self.assertEqual(st["turn_ai_text"], "")
        # 更正那一輪她又只說不做：20 秒內不再追
        st["pending_promise_cue"] = None
        st["turn_ai_text"] = "好，我已經幫你設好囉。"
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=108.0), "")
        self.assertIsNone(st["pending_promise_cue"])
        # 隔夠久的另一件事可以再更正
        st["turn_ai_text"] = "明天下午三點會提醒你量血壓喔。"
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=140.0), "reminder")

    def test_turn_end_does_nothing_when_something_was_really_written(self):
        st = {"turn_ai_text": "好，我已經幫你設好囉。", "turn_reminder_written": True}
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=1.0), "")
        self.assertFalse(st.get("pending_promise_cue"))
        # 記問題的工具寫成功了，她說「幫你記下來了」是真的
        st = {"turn_ai_text": "好，我幫你記下來了，下次回診問醫生。", "turn_any_write_ok": True}
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=1.0), "")
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", {}, now=1.0), "")

    def test_turn_end_ignores_offers_and_questions(self):
        st = {"turn_ai_text": "血壓藥千萬不能自己停掉喔！這要請醫師或藥師評估，我幫妳記下來，回診時再問他們好嗎？"}
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=1.0), "")
        self.assertFalse(st.get("pending_promise_cue"))

    def test_turn_end_catches_note_claim_without_any_write(self):
        st = {"turn_ai_text": "這個藥能不能停，一定要請醫生決定喔。我幫你記下來，下次看診的時候問醫生，這樣比較安全。"}
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=1.0), "note")
        self.assertIn("記錄問題的工具", st["pending_promise_cue"])

    def test_turn_end_prefers_failed_write_explanation(self):
        st = {"turn_ai_text": "下次看診確實可以問問醫生的建議，我會幫你記著喔。", "turn_write_failed": "add_care_question"}
        self.assertEqual(v.queue_unfulfilled_claim_cue("t", st, now=1.0), "write_failed")
        self.assertIn("沒有存成功", st["pending_promise_cue"])

    def test_both_turn_endings_call_the_guard(self):
        src = open(os.path.join(HERE, "live_voice_server.py"), encoding="utf-8").read()
        self.assertEqual(src.count("queue_unfulfilled_claim_cue(cid, st)"), 2,
                         "正常收尾與「替遲到的結束訊號收尾」兩條路都要接，少一條等於沒做")

    def test_tool_response_always_carries_status_and_no_retry(self):
        ok = v.tool_response_for_model({"status": "ok", "id": "r1"})
        self.assertEqual((ok["status"], ok["retryable"], ok["id"]), ("ok", False, "r1"))
        self.assertNotIn("message", ok)
        err = v.tool_response_for_model({"status": "error", "error": "care_question_list_full"})
        self.assertEqual((err["status"], err["retryable"], err["error"]), ("error", False, "care_question_list_full"))
        self.assertIn("不要再呼叫同一個工具重試", err["message"])
        self.assertIn("不可以說已經設好", err["message"])
        empty = v.tool_response_for_model({})
        self.assertEqual((empty["status"], empty["retryable"]), ("error", False))

    def test_only_real_write_tools_count_as_set(self):
        self.assertEqual(
            v._REMINDER_WRITE_TOOLS,
            frozenset({"set_clinic_reminder", "set_medication_reminder", "set_personal_event"}),
        )
        declared = {d.name for t in (v._REMINDER_TOOLS, v._EVENT_TOOLS) for d in t.function_declarations}
        self.assertTrue(v._REMINDER_WRITE_TOOLS <= declared, "防線認的工具名要真的存在")


if __name__ == "__main__":
    unittest.main(verbosity=2)
