#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三題常見症狀的契約（2026-08-13）：拉肚子、手麻、耳鳴。

**為什麼這三題存在**：93 句真人問法的量尺跑下來，只剩這三句完全接不到——
她沒有我們審過的話可講，只能讓通用模型自由發揮。

這支守四件事：
1. **叫得出來**——真人怎麼講都要接得到（觸發字是詞根、不是整句）
2. **誠實的話不准被改軟**——益生菌大型試驗沒效、銀杏對耳鳴沒效、咖啡因不用勉強戒。
   這三句是最容易被「寫得好聽一點」磨掉的，磨掉了這裡先紅。
3. **急症那條不准鈍化**——突然一邊聽不見的七十二小時、突然單側麻的中風、
   兩腳麻加大小便失禁的脊髓壓迫。
4. **拒絕卡照舊規矩**——不主動端出去，他自己點名就一定要答，而且不當第一句。
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_kb
import health_selector as hs

DIARRHEA = "TW-EDU-49"
NUMBNESS = "TW-EDU-50"
TINNITUS = "TW-EDU-51"


def elder():
    return {"audience": hs.audience_from_birth_year(1950)}


def say_of(topic, sid):
    return next(s for s in hs.TOPICS[topic]["solutions"] if s["id"] == sid)["say"]


class RoutingTest(unittest.TestCase):
    def test_real_phrasings_reach_the_right_topic(self):
        for said, want in (
            ("一直拉肚子", DIARRHEA), ("腸胃炎", DIARRHEA), ("上吐下瀉", DIARRHEA),
            ("拉肚子可以吃什麼", DIARRHEA),
            ("手一直麻", NUMBNESS), ("半夜麻醒", NUMBNESS), ("腳底麻麻的", NUMBNESS),
            ("耳鳴很吵", TINNITUS), ("耳朵嗡嗡叫", TINNITUS), ("耳朵一直有聲音", TINNITUS),
        ):
            self.assertEqual(health_kb.match_topics(said)[:1], [want], said)

    def test_ordinary_words_do_not_drag_these_topics_in(self):
        """「麻煩」「麻油雞」不可以叫出手麻題——觸發字太短會到處誤觸。"""
        for said in ("麻煩你幫我一下", "我想吃麻油雞", "今天天氣很好"):
            self.assertNotIn(NUMBNESS, health_kb.match_topics(said), said)


class LeadsWithTheRightThingTest(unittest.TestCase):
    def test_diarrhea_leads_with_rehydration(self):
        """拉肚子真正會出事的是脫水——補水一定要是第一句。"""
        picked = hs.pick(DIARRHEA, "一直拉肚子怎麼辦", elder(), 15)["solutions"]
        self.assertEqual(picked[0]["id"], "diar-rehydrate")

    def test_numbness_leads_with_sudden_versus_gradual(self):
        """先分「突然」還是「慢慢」——分錯了後面全錯。"""
        picked = hs.pick(NUMBNESS, "手一直麻", elder(), 15)["solutions"]
        self.assertEqual(picked[0]["id"], "numb-sudden-red-flag")

    def test_tinnitus_leads_with_the_one_ear_question(self):
        picked = hs.pick(TINNITUS, "耳鳴很吵", elder(), 15)["solutions"]
        self.assertEqual(picked[0]["id"], "tin-sudden-red-flag")


class HonestyTest(unittest.TestCase):
    """這三句是這一批的靈魂：明講不值得花錢、明講不用勉強戒。"""

    def test_probiotics_card_reports_the_two_big_trials(self):
        say = say_of(DIARRHEA, "diar-probiotics")
        self.assertIn("沒有差別", say)
        self.assertTrue("白花" in say or "不值得" in say, "「錢會白花」這句被拿掉了")
        finding = next(s for s in hs.TOPICS[DIARRHEA]["solutions"]
                       if s["id"] == "diar-probiotics")["evidence"]["finding"]
        self.assertIn("NEJM 2018", finding)

    def test_ginkgo_card_says_it_is_not_worth_the_money(self):
        say = say_of(TINNITUS, "tin-ginkgo")
        self.assertIn("幾乎沒有差別", say)
        self.assertTrue("白花" in say or "不值得" in say)

    def test_caffeine_card_does_not_repeat_the_folk_advice(self):
        """「耳鳴要戒咖啡」沒有證據——我們不跟著講，而且要明講不用勉強戒。"""
        say = say_of(TINNITUS, "tin-caffeine-honest")
        self.assertIn("沒有證據", say)
        self.assertIn("不用勉強戒", say)

    def test_sports_drink_is_not_offered_as_rehydration(self):
        """運動飲料當補液是最常見的錯，這句不能消失。"""
        say = say_of(DIARRHEA, "diar-rehydrate")
        self.assertIn("運動飲料", say)
        self.assertIn("愈喝愈拉", say)

    def test_brat_diet_is_called_out_as_not_better(self):
        self.assertIn("並沒有比正常清淡飲食好", say_of(DIARRHEA, "diar-eat"))

    def test_diabetic_neuropathy_does_not_promise_a_cure(self):
        say = say_of(NUMBNESS, "numb-diabetes")
        self.assertIn("沒有藥可以把已經傷到的神經修回去", say)

    def test_tinnitus_habituation_does_not_promise_silence(self):
        say = say_of(TINNITUS, "tin-habituation")
        self.assertIn("沒有辦法讓那個聲音消失", say)


class EmergencyTest(unittest.TestCase):
    """急症那條不准鈍化。"""

    def test_sudden_hearing_loss_keeps_the_72_hour_window(self):
        for sid in ("tin-sudden-red-flag", "tin-refer"):
            self.assertIn("七十二小時", say_of(TINNITUS, sid), sid)

    def test_sudden_one_sided_numbness_is_treated_as_stroke(self):
        say = say_of(NUMBNESS, "numb-sudden-red-flag")
        self.assertIn("中風", say)
        self.assertIn("119", say)

    def test_cauda_equina_red_flag_is_present(self):
        flags = next(s for s in hs.TOPICS[NUMBNESS]["solutions"]
                     if s["id"] == "numb-refer")["escalateWhen"]
        self.assertTrue(any("大小便" in f for f in flags),
                        "兩腳麻＋大小便失禁這條紅旗不見了")

    def test_each_topic_has_exactly_one_referral_card(self):
        for topic in (DIARRHEA, NUMBNESS, TINNITUS):
            refer = [s for s in hs.TOPICS[topic]["solutions"]
                     if s.get("riskLevel") == "L5"]
            self.assertEqual(len(refer), 1, topic)
            self.assertGreaterEqual(len(refer[0]["escalateWhen"]), 3, topic)

    def test_no_invented_phone_numbers(self):
        """只准 119／1966／1925／110——別國的號碼絕不能出現在台灣正本。"""
        import re
        allowed = {"119", "1966", "1925", "110"}
        for topic in (DIARRHEA, NUMBNESS, TINNITUS):
            for s in hs.TOPICS[topic]["solutions"]:
                for m in re.finditer(r"打\s*(\d{3,4})", s["say"]):
                    self.assertIn(m.group(1), allowed, f"{topic}/{s['id']}")


class BlockedCardTest(unittest.TestCase):
    """拒絕卡的老規矩：不主動端、點名必答、永遠不當第一句。"""

    BLOCKED = ((DIARRHEA, "diar-antidiarrheal", "止瀉藥可以吃嗎"),
               (NUMBNESS, "numb-blocked", "我這個要不要開刀"),
               (TINNITUS, "tin-meds-blocked", "是不是我吃的藥的副作用"))

    def test_not_volunteered(self):
        for topic, sid, _ in self.BLOCKED:
            ids = [s["id"] for s in hs.pick(topic, "怎麼辦", elder(), 15)["solutions"]]
            self.assertNotIn(sid, ids, sid)

    def test_answered_when_he_names_it(self):
        for topic, sid, said in self.BLOCKED:
            ids = [s["id"] for s in hs.pick(topic, said, elder(), 15)["solutions"]]
            self.assertIn(sid, ids, f"他問「{said}」我們卻整個不講")

    def test_never_the_first_line(self):
        for topic, sid, said in self.BLOCKED:
            picked = hs.pick(topic, said, elder(), 15)["solutions"]
            self.assertNotEqual(picked[0]["id"], sid, sid)

    def test_refusal_cards_still_hand_over_something_doable(self):
        """只拒絕不給做法＝無用 AI。三張都要接上「那你現在可以做什麼」。"""
        self.assertIn("不用問任何人", say_of(DIARRHEA, "diar-antidiarrheal"))
        self.assertIn("五件", say_of(NUMBNESS, "numb-blocked"))
        self.assertIn("拍照", say_of(TINNITUS, "tin-meds-blocked"))


class SupplementRulesTest(unittest.TestCase):
    """L3 三件事一件都不能少，而且警告要送到該聽的人耳裡。"""

    ANTICOAG = {"audience": "elder", "conditions": ["正在吃抗凝血劑"]}

    def test_l3_cards_carry_the_three_required_things(self):
        for topic, sid in ((DIARRHEA, "diar-probiotics"), (TINNITUS, "tin-ginkgo")):
            card = next(s for s in hs.TOPICS[topic]["solutions"] if s["id"] == sid)
            self.assertTrue(card.get("dailyCap"), sid)
            self.assertTrue(card.get("verifiedAt"), sid)
            self.assertTrue(card.get("evidence", {}).get("finding"), sid)
            self.assertTrue(card.get("contraindications") or card.get("warnsAbout"), sid)

    def test_blood_thinner_users_are_not_offered_ginkgo(self):
        ids = [s["id"] for s in hs.pick(TINNITUS, "耳鳴有什麼可以吃",
                                        self.ANTICOAG, 15)["solutions"]]
        self.assertNotIn("tin-ginkgo", ids)

    def test_but_naming_ginkgo_gets_the_bleeding_warning(self):
        """他已經知道銀杏了、開口問我們，卻因為它危險就不講它危險——他就去買了。"""
        picked = hs.pick(TINNITUS, "銀杏有效嗎", self.ANTICOAG, 15)["solutions"]
        ids = [s["id"] for s in picked]
        self.assertIn("tin-ginkgo", ids)
        self.assertIn("出血", say_of(TINNITUS, "tin-ginkgo"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
