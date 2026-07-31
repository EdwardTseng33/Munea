#!/usr/bin/env python3
"""代謝五題契約（2026-07-31 · Edward 問「三高、內臟脂肪、飲食法、減肥、過敏能不能解決」）。

**盤點發現**：三高只做了兩高——血脂整題不存在，而紅麴、魚油那些卡都在講「跟降血脂藥
的交互作用」，卻沒有一題講血脂本身。體重／內臟脂肪是慢性病的上游，也同樣是零。

這支守的三條，都是這一批特有、別題沒有的：
1. **長輩變瘦不是好消息**——癌症、甲狀腺、失智前期都會讓人瘦。講到瘦要先問是不是自己想瘦的
2. **降血脂藥不能自己停**——血脂高沒感覺，數字好正是因為在吃
3. **嚴重過敏會壓迫呼吸道**——這是急症，不是「忌口就好」
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_kb
import health_selector as hs


def real(birth_year):
    """正式機真的算得出來的側寫——不准手寫 audience 自欺。"""
    return {"audience": hs.audience_from_birth_year(birth_year)}


class RoutingTest(unittest.TestCase):
    def test_each_new_topic_is_reachable(self):
        for said, tid in (("我膽固醇有點高", "TW-EDU-33"),
                          ("肚子越來越大怎麼辦", "TW-EDU-34"),
                          ("168斷食有效嗎", "TW-EDU-35"),
                          ("我吃海鮮會過敏", "TW-EDU-36"),
                          ("我最近手沒力氣、瓶蓋轉不開", "TW-EDU-37")):
            self.assertEqual(health_kb.match_topics(said)[:1], [tid], said)

    def test_phrasing_with_inserted_words_still_lands(self):
        """插一個字就整組叫不出來的漏洞，這批建立時又踩到三次。"""
        for said in ("我最近瘦了好多", "喝牛奶會拉肚子", "健檢說我有脂肪肝",
                     "褲子都鬆了", "我想減肥"):
            self.assertTrue(health_kb.match_topics(said), said)


class WeightLossSafetyTest(unittest.TestCase):
    """這一批最要緊的一條：長輩變瘦不是好消息。"""

    def test_mentioning_weight_loss_asks_whether_it_was_intended(self):
        for said in ("我最近瘦了好多", "褲子都鬆了"):
            first = hs.pick("TW-EDU-34", said, real(1945), 15)["solutions"][0]
            self.assertEqual(first["id"], "wt-unintended-loss", said)

    def test_the_card_treats_unexplained_loss_as_a_warning_not_a_win(self):
        say = next(s for s in hs.TOPICS["TW-EDU-34"]["solutions"]
                   if s["id"] == "wt-unintended-loss")["say"]
        self.assertIn("不是好消息", say)

    def test_referral_covers_the_scary_causes(self):
        ref = hs.pick("TW-EDU-34", "我想減肥", real(1945), 15)["referral"]
        self.assertIn("不明原因變瘦", ref["say"])

    def test_diet_pills_are_blocked_and_black_market_is_named(self):
        sol = next(s for s in hs.TOPICS["TW-EDU-34"]["solutions"]
                   if s["id"] == "wt-diet-pills-blocked")
        self.assertTrue(sol["blocked"])
        self.assertIn("來路不明", sol["say"])

    def test_losing_weight_never_means_losing_muscle_silently(self):
        ids = [s["id"] for s in hs.pick("TW-EDU-34", "我想減肥", real(1950), 15)["solutions"]]
        self.assertTrue({"wt-slow-is-right", "wt-muscle-not-just-diet"} & set(ids))


class LipidTest(unittest.TestCase):
    def test_never_stop_your_statin_leads(self):
        first = hs.pick("TW-EDU-33", "我膽固醇有點高", real(1950), 15)["solutions"][0]
        self.assertEqual(first["id"], "lipid-statin-dont-stop")
        self.assertIn("不要自己停", first["say"])

    def test_reading_my_numbers_is_blocked(self):
        for s in hs.pick("TW-EDU-33", "我的膽固醇 240 算高嗎", real(1950), 15)["solutions"]:
            self.assertNotEqual(s.get("riskLevel"), "L4")

    def test_red_yeast_double_dosing_is_spelled_out(self):
        say = next(s for s in hs.TOPICS["TW-EDU-33"]["solutions"]
                   if s["id"] == "lipid-red-yeast-caution")["say"]
        self.assertIn("同一種東西吃兩份", say)

    def test_referral_carries_rhabdo_and_the_cardiac_line(self):
        ref = hs.pick("TW-EDU-33", "我血脂高", real(1950), 15)["referral"]
        self.assertIn("橫紋肌溶解", ref["say"])
        self.assertIn("119", ref["say"])


class DietHonestyTest(unittest.TestCase):
    """飲食法最容易變成推銷流行——這裡守住「講證據、不推流行」。"""

    def test_the_one_you_can_keep_leads(self):
        first = hs.pick("TW-EDU-35", "哪種飲食法最好", real(1980), 15)["solutions"][0]
        self.assertEqual(first["id"], "diet-pick-what-you-can-keep")

    def test_low_carb_is_told_honestly(self):
        say = next(s for s in hs.TOPICS["TW-EDU-35"]["solutions"]
                   if s["id"] == "diet-low-carb-honest")["say"]
        self.assertIn("一兩年後跟其他方法差不多", say)

    def test_fasting_warns_the_people_who_must_not_do_it(self):
        prof = {"audience": "worker", "conditions": ["正在吃降血糖藥"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-35", "168斷食有效嗎", prof, 15)["solutions"]]
        self.assertNotIn("diet-fasting-honest", ids, "吃血糖藥的人還端出斷食")

    def test_detox_is_blocked(self):
        sol = next(s for s in hs.TOPICS["TW-EDU-35"]["solutions"]
                   if s["id"] == "diet-detox-blocked")
        self.assertTrue(sol["blocked"])
        self.assertIn("沒有這回事", sol["say"])

    def test_dash_is_removed_for_kidney_trouble(self):
        prof = {"audience": "elder", "conditions": ["腎功能異常"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-35", "得舒飲食好嗎", prof, 15)["solutions"]]
        self.assertNotIn("diet-dash", ids)


class AllergyTest(unittest.TestCase):
    def test_allergy_versus_intolerance_leads(self):
        first = hs.pick("TW-EDU-36", "我吃海鮮會過敏", real(1975), 15)["solutions"][0]
        self.assertEqual(first["id"], "allergy-vs-intolerance")

    def test_anaphylaxis_gets_an_ambulance_not_a_diet_tip(self):
        ref = hs.pick("TW-EDU-36", "我吃了會癢", real(1975), 15)["referral"]
        self.assertIn("119", ref["say"])
        self.assertIn("呼吸道", ref["say"])

    def test_igg_testing_is_blocked(self):
        sol = next(s for s in hs.TOPICS["TW-EDU-36"]["solutions"]
                   if s["id"] == "allergy-test-blocked")
        self.assertTrue(sol["blocked"])
        self.assertIn("並不建議", sol["say"])

    def test_wide_self_elimination_is_warned_against(self):
        say = next(s for s in hs.TOPICS["TW-EDU-36"]["solutions"]
                   if s["id"] == "allergy-no-self-elimination")["say"]
        self.assertIn("長輩尤其危險", say)


class SarcopeniaTest(unittest.TestCase):
    def test_the_everyday_signals_lead(self):
        first = hs.pick("TW-EDU-37", "我最近沒什麼力氣", real(1945), 15)["solutions"][0]
        self.assertEqual(first["id"], "sarco-what-it-looks-like")

    def test_protein_is_spread_across_meals_not_dumped_at_dinner(self):
        say = next(s for s in hs.TOPICS["TW-EDU-37"]["solutions"]
                   if s["id"] == "sarco-protein-每餐")["say"]
        self.assertIn("每一餐都有一份", say)

    def test_protein_powder_is_removed_for_kidney_trouble(self):
        prof = {"audience": "elder", "conditions": ["腎功能異常"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-37", "乳清有用嗎", prof, 15)["solutions"]]
        self.assertNotIn("sarco-protein-supp", ids)

    def test_powder_alone_is_not_sold_as_enough(self):
        say = next(s for s in hs.TOPICS["TW-EDU-37"]["solutions"]
                   if s["id"] == "sarco-protein-supp")["say"]
        self.assertIn("單吃不動效果有限", say)


if __name__ == "__main__":
    unittest.main(verbosity=2)
