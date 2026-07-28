#!/usr/bin/env python3
"""因人因時因地挑選契約（2026-07-29 · Edward「同一題三個人要三種答案」）。

驗收尺（設計文件寫死的）：同一句「我睡不好」，對不同的人給出的方案
**互相不能替換**——任何一段換到另一個人身上會顯得答非所問。

這支釘住的是**程式層**行為（誰能拿到什麼方案），不是模型講話的品質——
所以它是確定性的、不會今天對明天錯，這正是安全類該有的防線。
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_selector as hs

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = {"audience": "worker"}
ELDER = {"audience": "elder"}
CAREGIVER = {"audience": "caregiver", "constraints": ["照顧者夜間需起身"]}


def ids(result):
    return [s["id"] for s in result["solutions"]]


class SafetyFirstTest(unittest.TestCase):
    """安全過濾是硬性的——排序翻不了、偏好也翻不了。"""

    def test_kidney_condition_removes_magnesium_entirely(self):
        """腎功能異常 → 鎂整個拿掉，不是排到後面。"""
        r = hs.pick("TW-EDU-01", "我睡不好，快受不了", {"audience": "worker", "conditions": ["腎功能異常"]}, 23)
        self.assertNotIn("sleep-magnesium-supplement", ids(r))

    def test_prescription_only_option_never_enters_the_pool(self):
        """褪黑激素在台灣是處方藥——不管誰問、幾點問，都不可以進推薦池。"""
        for prof, hour in ((WORKER, 23), (ELDER, 10), (CAREGIVER, 2)):
            r = hs.pick("TW-EDU-01", "我睡不好", prof, hour)
            self.assertNotIn("sleep-melatonin-blocked", ids(r))

    def test_referral_card_always_travels_alongside(self):
        """什麼時候該看醫生：永遠帶著、而且不佔一般方案的名額。"""
        r = hs.pick("TW-EDU-01", "我睡不好", WORKER, 23)
        self.assertIsNotNone(r["referral"])
        self.assertEqual(r["referral"]["riskLevel"], "L5")
        self.assertNotIn(r["referral"]["id"], ids(r))


class ThreePeopleThreeAnswersTest(unittest.TestCase):
    """驗收尺：三個人的方案組合互相不能相同。"""

    def test_the_three_answer_sets_are_not_interchangeable(self):
        a = ids(hs.pick("TW-EDU-01", "我最近都睡不好，快受不了了", WORKER, 23))
        b = ids(hs.pick("TW-EDU-01", "我最近攏睡不太好", ELDER, 10))
        c = ids(hs.pick("TW-EDU-01", "我媽三點要起來上廁所，我根本睡不飽", CAREGIVER, 2))
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, c)
        self.assertNotEqual(a, c)

    def test_urgent_worker_gets_tonight_first_and_reaches_the_supplement(self):
        """急的上班族：今晚能做的排前面，而且拿得到那個有新證據的保健品選項。"""
        r = hs.pick("TW-EDU-01", "我最近都睡不好，快受不了了", WORKER, 23)
        self.assertTrue(r["urgent"])
        self.assertEqual(r["solutions"][0]["timeToEffect"], "今晚")
        self.assertIn("sleep-magnesium-supplement", ids(r))

    def test_unhurried_elder_gets_food_first_not_a_supplement_pitch(self):
        """不急的長輩：食補優先；不主動把保健品推給可能同時吃多種藥的人。"""
        r = hs.pick("TW-EDU-01", "我最近攏睡不太好", ELDER, 10)
        self.assertFalse(r["urgent"])
        self.assertEqual(r["solutions"][0]["solutionType"], "食補")
        self.assertNotIn("sleep-magnesium-supplement", ids(r))

    def test_caregiver_problem_is_reframed_before_any_advice(self):
        """照顧者不是失眠、是沒得睡——先重新定義問題，主推也要對症。"""
        r = hs.pick("TW-EDU-01", "我媽三點要起來上廁所，我根本睡不飽", CAREGIVER, 2)
        self.assertIsNotNone(r["reframe"])
        self.assertIn("沒得睡", r["reframe"])
        self.assertEqual(r["solutions"][0]["id"], "sleep-split-rest")


class DoableAndPreferenceTest(unittest.TestCase):
    """正確但做不到的建議比不給更傷；偏好也要被尊重。"""

    def test_shift_worker_does_not_get_fixed_waketime(self):
        r = hs.pick("TW-EDU-01", "我睡不好", {"audience": "worker", "constraints": ["輪班工作"]}, 23)
        self.assertNotIn("sleep-fixed-waketime", ids(r))

    def test_caregiver_does_not_get_fixed_waketime_either(self):
        """她半夜一定會被叫起來，「固定時間起床」對她是做不到的正確答案。"""
        r = hs.pick("TW-EDU-01", "我根本睡不飽", CAREGIVER, 2)
        self.assertNotIn("sleep-fixed-waketime", ids(r))

    def test_saying_you_do_not_want_pills_drops_the_supplement(self):
        r = hs.pick("TW-EDU-01", "我睡不好，不想吃藥", WORKER, 23)
        self.assertNotIn("sleep-magnesium-supplement", ids(r))

    def test_low_mobility_deprioritises_exercise(self):
        r = hs.pick("TW-EDU-01", "我睡不太好", {"audience": "elder", "lowMobility": True}, 10)
        self.assertNotEqual(r["solutions"][0]["solutionType"], "運動")


class OutputShapeTest(unittest.TestCase):
    def test_at_most_three_and_not_all_the_same_kind(self):
        """最多三個（再多長輩記不住）；且不會三個都同一招。"""
        for prof, hour in ((WORKER, 23), (ELDER, 10), (CAREGIVER, 2)):
            r = hs.pick("TW-EDU-01", "我睡不好", prof, hour)
            self.assertLessEqual(len(r["solutions"]), 3)
            kinds = [s["solutionType"] for s in r["solutions"]]
            self.assertLessEqual(max(kinds.count(k) for k in set(kinds)), 2)

    def test_supplement_line_always_carries_cap_and_contraindications(self):
        """L3 三件事：成熟度、每日上限、誰不能吃且要問專業——少一件就不合格。"""
        text = hs.render("TW-EDU-01", "我最近都睡不好，快受不了了", WORKER, 23)
        self.assertIn("250 毫克", text)
        self.assertIn("腎功能異常", text)
        self.assertIn("問醫師或營養師", text)

    def test_render_is_empty_when_topic_unknown(self):
        self.assertEqual(hs.render("NO-SUCH-TOPIC", "隨便問", WORKER, 12), "")

    def test_render_never_names_a_brand(self):
        for prof, hour in ((WORKER, 23), (ELDER, 10), (CAREGIVER, 2)):
            text = hs.render("TW-EDU-01", "我睡不好", prof, hour)
            self.assertIn("絕不推薦品牌", text)


class DataIntegrityTest(unittest.TestCase):
    """資料本身的紀律——內容寫壞了這裡先亮紅燈。"""

    def test_every_supplement_declares_cap_and_contraindications(self):
        for topic in hs.TOPICS.values():
            for s in topic["solutions"]:
                if s.get("riskLevel") == "L3":
                    self.assertTrue(s.get("dailyCap"), f"{s['id']} 缺每日上限")
                    self.assertTrue(s.get("contraindications"), f"{s['id']} 缺禁忌族群")
                    self.assertTrue(s.get("evidence"), f"{s['id']} 缺證據出處")
                    self.assertTrue(s.get("verifiedAt"), f"{s['id']} 缺查證日期")

    def test_no_simplified_characters_in_anything_she_says(self):
        bad = "个没发药风见问长张护记忆疗诊断压检说话请谢"
        for topic in hs.TOPICS.values():
            for s in topic["solutions"]:
                for ch in bad:
                    self.assertNotIn(ch, s["say"], f"{s['id']} 含簡體字「{ch}」")


if __name__ == "__main__":
    unittest.main(verbosity=2)
