#!/usr/bin/env python3
"""中醫理解層契約（2026-07-29 · Edward「亞洲人很多人是用中醫思考」後建）。

**這一層的核心判斷**：最大的價值不是開方子，是**聽得懂他在講什麼**。
台灣長輩每天用「我最近很燥」「肝火旺」「氣虛」「冷底」描述身體，她原本完全接不住——
那是理解的缺口，不是處方的缺口。而「聽得懂」零法規風險。

這支守的是那條界線：**理解可以無限，扮演中醫師一步都不行。**
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import chat_engine as eng
import health_kb
import health_selector as hs

HERE = os.path.dirname(os.path.abspath(__file__))
TOPIC = "TW-EDU-30"


def real(birth_year):
    """正式機真的算得出來的側寫——不准手寫 audience 自欺（7/29 踩過五次）。"""
    return {"audience": hs.audience_from_birth_year(birth_year)}




def _chat_engine_and_books():
    """2026-07-31 人設書分國：⑥-TCM 那些規則從程式碼搬進 engine/persona/core.zh-TW.txt。

    這支守的東西沒變（規則被刪就亮紅燈），只是現在要把程式碼與繁中書合起來看。
    ⚠ 只看繁中版：中醫這一節是台灣專屬，其他國家的書用當地的傳統醫學（日本＝漢方）。
    """
    parts = [open(os.path.join(HERE, "chat_engine.py"), encoding="utf-8").read()]
    for kind in ("core", "red", "lookup-offline", "lookup-online"):
        path = os.path.join(HERE, "persona", kind + ".zh-TW.txt")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                parts.append(handle.read())
    return chr(10).join(parts)


class UnderstandingTest(unittest.TestCase):
    """聽得懂：長輩用體質語言描述身體時，要接得住、不裝沒聽到、也不糾正他。"""

    def test_constitution_words_reach_the_tcm_topic(self):
        for said in ("我最近很燥，嘴巴一直破", "我媽一直說她氣虛", "我是冷底的",
                     "最近肝火很旺", "濕氣很重"):
            self.assertEqual(health_kb.match_topics(said)[:1], [TOPIC], said)

    def test_she_starts_by_understanding_not_by_prescribing(self):
        first = hs.pick(TOPIC, "我最近很燥", real(1950), 20)["solutions"][0]
        self.assertEqual(first["id"], "tcm-listen")

    def test_the_prompt_tells_her_to_understand_the_language(self):
        src = _chat_engine_and_books()
        self.assertIn("⑥-TCM", src)
        self.assertIn("不要因為那是中醫用語就裝作沒聽到", src)


class RedLineTest(unittest.TestCase):
    """扮演中醫師一步都不行——這幾條紅了就是真的越線。"""

    def test_she_never_assigns_a_tcm_pattern_to_him(self):
        """「你這是腎虛」跟下西醫診斷同一條線。"""
        for s in hs.TOPICS[TOPIC]["solutions"]:
            for bad in ("你是腎虛", "你這是肝火旺", "你屬於濕熱"):
                self.assertNotIn(bad, s["say"], s["id"])

    def test_prescribing_is_blocked_entirely(self):
        blocked = next(s for s in hs.TOPICS[TOPIC]["solutions"]
                       if s["id"] == "tcm-prescribe-blocked")
        self.assertTrue(blocked["blocked"])
        for word in ("開方", "腎虛", "肝火旺", "西藥停掉"):
            self.assertIn(word, blocked["say"])

    def test_no_dosage_anywhere_in_the_pool(self):
        """幾錢、幾克、幾帖都不行。"""
        for s in hs.TOPICS[TOPIC]["solutions"]:
            for unit in ("錢", "帖", "克"):
                if unit in s["say"]:
                    self.assertNotIn(unit + "，", s["say"], s["id"])
        cap = next(s for s in hs.TOPICS[TOPIC]["solutions"]
                   if s["id"] == "tcm-herb-interaction")["dailyCap"]
        self.assertIn("我不會給任何數字", cap)

    def test_never_swap_western_medicine_for_herbs(self):
        """為了吃中藥自己停降壓藥／抗凝血藥——這是會出人命的一條。"""
        ref = hs.pick(TOPIC, "我想吃中藥", real(1950), 20)["referral"]
        self.assertIn("不要為了吃中藥自己把西藥停掉", ref["say"])
        src = _chat_engine_and_books()
        self.assertIn("絕不建議他停掉西藥改吃中藥", src)

    def test_no_brand_or_herb_shop_recommendation(self):
        src = _chat_engine_and_books()
        self.assertIn("不推薦特定中藥行、藥材品牌或坊間偏方", src)


class SafetyContentTest(unittest.TestCase):
    """幾條真的會傷人的交互作用，要講得到。"""

    def test_asking_about_dong_quai_on_blood_thinners_gets_the_warning(self):
        """他直接問了，最該回答的那條就必須排第一——不然等於答非所問。"""
        picked = hs.pick(TOPIC, "我在吃抗凝血的藥，可以吃當歸嗎", real(1950), 20)["solutions"]
        self.assertEqual(picked[0]["id"], "tcm-herb-interaction")
        self.assertIn("出血", picked[0]["say"])

    def test_licorice_and_blood_pressure_is_named(self):
        """甘草幾乎每帖中藥都有，血壓高的人要知道。"""
        sol = next(s for s in hs.TOPICS[TOPIC]["solutions"] if s["id"] == "tcm-herb-interaction")
        self.assertIn("甘草", sol["say"])
        self.assertIn("血壓", sol["say"])

    def test_tonic_food_question_gets_the_tonic_caution(self):
        picked = hs.pick(TOPIC, "冬天想吃薑母鴨進補可以嗎", real(1955), 20)["solutions"]
        self.assertEqual(picked[0]["id"], "tcm-tonic-caution")

    def test_pregnancy_still_blocks_all_herbs(self):
        """孕哺那題本來就擋草藥中藥——這裡確認沒被中醫層鬆掉。"""
        sol = next(s for s in hs.TOPICS["TW-EDU-29"]["solutions"]
                   if s["id"] == "preg-herbs-caution")
        self.assertIn("中藥", sol["say"])
        self.assertIn("純天然", sol["say"])

    def test_health_insurance_covers_tcm_is_told(self):
        """中醫門診健保有給付——很多長輩不知道，這是實用資訊。"""
        sol = next(s for s in hs.TOPICS[TOPIC]["solutions"] if s["id"] == "tcm-see-doctor")
        self.assertIn("健保", sol["say"])
        self.assertIn("執照", sol["say"])


class ProportionTest(unittest.TestCase):
    """分寸：他提中醫才走這條路，他沒提就別把話帶過去（跟不推銷保健品同一個道理）。"""

    def test_she_does_not_steer_a_plain_complaint_into_tcm(self):
        self.assertEqual(health_kb.match_topics("我睡不好")[:1], ["TW-EDU-01"])
        self.assertEqual(health_kb.match_topics("肩頸很痠想按摩")[:1], ["TW-EDU-22"])

    def test_the_prompt_states_the_proportion_rule(self):
        src = _chat_engine_and_books()
        self.assertIn("他沒提就別主動把話帶去中醫", src)


class AskedForIsGeneralTest(unittest.TestCase):
    """他點名問的東西要浮上來——這條在中醫題抓到，但已升級成所有題目通用。"""

    def test_named_item_outranks_generic_advice(self):
        first = hs.pick("TW-EDU-02", "葡萄糖胺有效嗎", real(1950), 15)["solutions"][0]
        self.assertEqual(first["id"], "knee-glucosamine")

    def test_the_bonus_lives_in_the_scorer_not_just_the_demotion_lift(self):
        """點名加分要真的加在分數上，不能只是「把陪襯層放行」。

        （2026-07-31 量法改過：原本是去 health_selector.py 裡比對一行程式碼長什麼樣，
        改一行寫法就紅——這種守門守的是「這一版怎麼寫」、不是「要守什麼」，
        7 月已經被咬過五次。改成看行為：一張**沒有被降級**的卡，他點名之後
        要真的往前排；如果加分只長在解除降級那邊，這條就會紅。）
        """
        sol = next(s for s in hs.TOPICS["TW-EDU-02"]["solutions"] if s["id"] == "knee-glucosamine")
        self.assertTrue(sol.get("secondLine"), "這題的前提是它本來是陪襯層")
        flags = hs._profile_flags(real(1950))
        plain = hs._score(sol, flags, False, "膝蓋痛怎麼辦")
        named = hs._score(sol, flags, False, "葡萄糖胺有效嗎")
        self.assertGreater(named, plain + 3.0, "點名沒有在分數上加到東西")

    def test_safety_still_wins_over_being_asked_by_name(self):
        """他點名問，也翻不了禁忌——安全永遠在最上面。"""
        prof = {"audience": "worker", "conditions": ["腎功能異常"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-01", "鎂有效嗎", prof, 23)["solutions"]]
        self.assertNotIn("sleep-magnesium-supplement", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
