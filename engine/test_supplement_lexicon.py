#!/usr/bin/env python3
"""保健品百科契約（2026-07-31 · Edward「推進優化」）。

**為什麼這一批存在**：庫存清點後保健品只有 12 條、每條綁死一個症狀——台灣人
最常買的雞精、B群、Q10、薑黃、蔓越莓一條都沒有。問到沒蓋的，她退回通用常識：
安全，但沒有查證品質、沒有保鮮期保護。

這支守三件事：
1. **點名問就答得到**（觸發字＝產品名，不搶「保健品跟藥」那題的通用流量）
2. **證據講實話**——雞精蛋白不如一顆蛋、綜合維他命防慢性病幾乎沒差。
   不順著市場話術，是這一批的靈魂；哪天有人把這些話改軟，這裡要先紅。
3. **交互作用是硬的**——吃抗凝血藥的人，會出血的那幾樣整個消失、不是降權。
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_kb
import health_selector as hs

TOPIC = "TW-EDU-31"


def real(birth_year):
    """正式機真的算得出來的側寫——不准手寫 audience 自欺（7/29 的教訓）。"""
    return {"audience": hs.audience_from_birth_year(birth_year)}


class RoutingTest(unittest.TestCase):
    def test_named_supplements_reach_the_lexicon(self):
        for said in ("雞精對身體有沒有幫助", "B群可以天天吃嗎", "魚油護心臟嗎",
                     "Q10 要不要吃", "牛樟芝很貴有效嗎", "薑黃有用嗎"):
            self.assertEqual(health_kb.match_topics(said)[:1], [TOPIC], said)

    def test_the_named_one_leads(self):
        """點名問哪個，主推就是哪個——端出別的等於答非所問。"""
        for said, lead in (("雞精對身體有沒有幫助", "lex-essence-chicken"),
                           ("B群可以天天吃嗎", "lex-b-complex"),
                           ("蔓越莓可以治尿道發炎嗎", "lex-cranberry")):
            picked = hs.pick(TOPIC, said, real(1950), 15)["solutions"]
            self.assertEqual(picked[0]["id"], lead, said)

    def test_generic_supplement_talk_still_goes_to_the_management_topic(self):
        """「保健品跟藥一起管」那題的地盤不能被搶。

        2026-08-12 分地盤：新開了 TW-EDU-43「處方藥怎麼吃、吃太多種怎麼辦」。
        兩題的分工是——**有保健品味道的歸 16，純處方藥的歸 43**。
        所以「家裡藥太多了」改由 43 帶頭（那題就是在講多重用藥），但 16 仍會
        一起被帶上（一輪最多帶兩題），保健品配藥的知識不會消失。
        守的東西沒變：只要句子裡有保健品，16 就必須是第一個。
        """
        for said in ("我在吃紅麴", "保健品跟藥一起吃會不會怎樣", "葡萄柚不能配什麼藥"):
            self.assertEqual(health_kb.match_topics(said)[:1], ["TW-EDU-16"], said)
        # 純處方藥的講法讓給專門那題，但 16 不能整個消失
        self.assertIn("TW-EDU-16", health_kb.match_topics("家裡藥太多了"))

    def test_melatonin_by_name_gets_the_prescription_answer(self):
        """他點名問，答案本身就是「台灣是處方藥」——不能因為不推薦就整條沉掉、
        端出不相干的維他命C（首次接線實測踩到）。"""
        picked = hs.pick(TOPIC, "褪黑激素哪裡買", real(1950), 15)["solutions"]
        self.assertEqual(picked[0]["id"], "lex-melatonin")
        self.assertTrue("處方藥" in picked[0]["say"] or "當「藥」管理" in picked[0]["say"],
                        "「台灣是當藥管理」這個事實不見了")


class HonestyTest(unittest.TestCase):
    """證據講實話是這一批的靈魂——話被改軟，這裡先紅。"""

    def _say(self, sid):
        return next(s for s in hs.TOPICS[TOPIC]["solutions"] if s["id"] == sid)["say"]

    def test_chicken_essence_tells_the_egg_truth(self):
        say = self._say("lex-essence-chicken")
        self.assertTrue("不如一顆蛋" in say or "比不上一顆蛋" in say,
                        "「雞精蛋白質比不上一顆蛋」這句不見了")

    def test_multivitamin_does_not_oversell(self):
        self.assertIn("幾乎沒有差", self._say("lex-multivitamin"))

    def test_fish_oil_reflects_the_big_trials(self):
        say = self._say("lex-fish-oil")
        self.assertTrue("大多沒看到效果" in say or "並沒有減少" in say,
                        "「大型試驗沒看到效果」這個事實不見了")
        self.assertIn("每週吃兩次魚", say)

    def test_b_complex_is_not_sold_as_an_energy_drink(self):
        self.assertIn("不是提神劑", self._say("lex-b-complex"))

    def test_lingzhi_and_antrodia_still_call_out_the_cancer_marketing(self):
        """靈芝、牛樟芝 2026-08-12 併進人蔘那張——**話不准跟著消失**。
        （守的是「抗癌那種話沒有人體實證、貴得不值得」這兩個事實，不是卡片編號。）"""
        say = self._say("lex-ginseng")
        self.assertIn("靈芝", say)
        self.assertIn("牛樟芝", say)
        self.assertTrue("沒有人體實證" in say or "沒有實證" in say, "抗癌那句被拿掉了")


class InteractionTest(unittest.TestCase):
    """交互作用是硬的：禁忌＝整個拿掉，不是降權。"""

    ANTICOAG = {"audience": "elder", "conditions": ["正在吃抗凝血劑"]}

    def test_blood_thinner_users_are_never_offered_the_bleeding_risks(self):
        """**沒問就不提**——怕的是「你不提他還不知道，一提他就去買」。"""
        for said in ("有什麼保健品可以顧心臟", "我想買個保健品", "有什麼推薦的"):
            ids = [s["id"] for s in hs.pick(TOPIC, said, self.ANTICOAG, 15)["solutions"]]
            for banned in ("lex-q10", "lex-turmeric", "lex-ginseng", "lex-nattokinase"):
                self.assertNotIn(banned, ids, said)

    def test_but_if_he_names_it_himself_he_must_get_the_warning(self):
        """**問了就一定要答**（2026-08-12 改的量法）。

        原本這條寫成「吃抗凝血藥的人永遠看不到這幾張」，連他自己點名問都一樣。
        但那等於：他已經知道納豆激酶了、開口問我們，我們卻因為它危險而不講它危險
        ——他大概率就去買了。跟 7/31「blocked 卡他點名就要答」是同一條規則。
        守的東西沒變（不主動端出去），改的是「他自己問」那一格。
        """
        for said, want in (("Q10 要不要吃", "lex-q10"),
                           ("薑黃有用嗎", "lex-turmeric"),
                           ("靈芝可以吃嗎", "lex-ginseng"),
                           ("納豆激酶有效嗎", "lex-nattokinase")):
            ids = [s["id"] for s in hs.pick(TOPIC, said, self.ANTICOAG, 15)["solutions"]]
            self.assertIn(want, ids, f"他自己問「{said}」，我們卻不警告他")

    def test_gout_removes_chicken_essence(self):
        prof = {"audience": "elder", "conditions": ["痛風／尿酸過高"]}
        ids = [s["id"] for s in hs.pick(TOPIC, "雞精有沒有幫助", prof, 15)["solutions"]]
        self.assertNotIn("lex-essence-chicken", ids)

    def test_diabetes_meds_never_get_offered_bitter_melon(self):
        prof = {"audience": "elder", "conditions": ["正在吃降血糖藥"]}
        ids = [s["id"] for s in hs.pick(TOPIC, "有什麼保健品可以吃", prof, 15)["solutions"]]
        self.assertNotIn("lex-bitter-melon", ids)

    def test_but_naming_bitter_melon_gets_the_warning(self):
        """他自己問苦瓜胜肽，那張「不能取代血糖藥」就是他最該聽到的一句。"""
        prof = {"audience": "elder", "conditions": ["正在吃降血糖藥"]}
        ids = [s["id"] for s in hs.pick(TOPIC, "苦瓜胜肽有效嗎", prof, 15)["solutions"]]
        self.assertIn("lex-bitter-melon", ids)

    def test_q10_say_warns_it_weakens_warfarin(self):
        say = next(s for s in hs.TOPICS[TOPIC]["solutions"] if s["id"] == "lex-q10")["say"]
        self.assertIn("變弱", say)

    def test_nattokinase_explains_the_two_way_trap(self):
        """納豆激酶抗凝血、納豆食物的維生素K又反向——兩頭都要講。"""
        say = next(s for s in hs.TOPICS[TOPIC]["solutions"]
                   if s["id"] == "lex-nattokinase")["say"]
        self.assertIn("出血", say)
        self.assertIn("相反", say)


class GrapefruitTest(unittest.TestCase):
    """葡萄柚／柚子×藥——台灣中秋限定地雷，最常見也最少人知道。"""

    def test_asking_about_pomelo_with_meds_gets_the_warning(self):
        picked = hs.pick("TW-EDU-16", "柚子可以配藥嗎", real(1950), 15)["solutions"]
        self.assertEqual(picked[0]["id"], "supp-grapefruit")

    def test_the_warning_says_timing_does_not_help(self):
        say = next(s for s in hs.TOPICS["TW-EDU-16"]["solutions"]
                   if s["id"] == "supp-grapefruit")["say"]
        self.assertIn("錯開時間吃也沒用", say)

    def test_bp_topic_bridges_to_grapefruit_when_pomelo_is_mentioned(self):
        """「我有在吃血壓藥，可以吃柚子嗎」會被血壓題接走——跨題連結要把橋搭上。"""
        res = hs.pick("TW-EDU-03", "中秋節可以吃柚子嗎？我有在吃血壓藥", real(1950), 15)
        self.assertIsNotNone(res.get("related"))
        self.assertIn("柚子", res["related"])


class FrameworkTest(unittest.TestCase):
    def test_one_at_a_time_ties_into_the_flywheel(self):
        say = next(s for s in hs.TOPICS[TOPIC]["solutions"]
                   if s["id"] == "lex-one-at-a-time")["say"]
        self.assertIn("一次只加一種", say)
        self.assertIn("幫你記著", say)

    def test_referral_card_forbids_swapping_meds_for_supplements(self):
        ref = hs.pick(TOPIC, "雞精有沒有幫助", real(1950), 15)["referral"]
        self.assertIn("不要為了吃保健品", ref["say"])
        self.assertIn("把醫師開的藥停掉", ref["say"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
