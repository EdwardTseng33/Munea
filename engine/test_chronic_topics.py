#!/usr/bin/env python3
"""慢性病三題契約（2026-07-31 · 代謝五題之後，把 Edward 問的「相關慢性病」補完）。

**盤點發現的三個洞**：
  · 慢性腎臟病：台灣洗腎人口密度世界第一，而我們的方案池到處拿「腎功能異常」
    當禁忌把東西剔掉，卻沒有一題告訴他「那你該怎麼吃」。只擋不教＝半套。
  · 氣喘／慢性阻塞性肺病：整個庫零筆「吸入劑」。最常見的錯是只用救急那支。
  · 中風後：再中風率高，而台灣還在流行「通血路」的點滴與活血補品。

**順手抓到的系統性問題**（這支下半部在守）：`blocked` 在挑選層是「整條剔除」，
所以主庫裡三十幾張 blocked 卡——褪黑激素、換藥、瘦瘦針、排毒、IgG 檢測——
**一次都沒被講出來過**。它們每一張都是寫給用戶聽的誠實回話。現在的規則是：
不主動端出去（不變），但他自己點名了就要回答，而且不當第一句。
"""
import io
import json
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_kb
import health_selector as hs

HERE = os.path.dirname(os.path.abspath(__file__))


def real(birth_year):
    """正式機真的算得出來的側寫——不准手寫 audience 自欺。"""
    return {"audience": hs.audience_from_birth_year(birth_year)}


def ids(topic_id, said, birth_year=1945, hour=15, profile=None):
    prof = profile or real(birth_year)
    return [s["id"] for s in hs.pick(topic_id, said, prof, hour)["solutions"]]


def card(topic_id, sol_id):
    return next(s for s in hs.TOPICS[topic_id]["solutions"] if s["id"] == sol_id)


class RoutingTest(unittest.TestCase):
    def test_each_new_topic_is_reachable(self):
        for said, tid in (("我腎不好", "TW-EDU-38"),
                          ("我有氣喘", "TW-EDU-39"),
                          ("我爸中風過", "TW-EDU-40")):
            self.assertEqual(health_kb.match_topics(said)[:1], [tid], said)

    def test_the_way_people_actually_say_it(self):
        """插一個字就整組叫不出來的漏洞，這批建立時又踩到四次。"""
        for said in ("醫生說我腎功能不好", "尿蛋白有加號", "肌酸酐有點高",
                     "走幾步就會喘", "吸入劑要怎麼用", "我痰很多又黃",
                     "中風之後手抬不起來", "小中風", "通血路的點滴有效嗎"):
            self.assertTrue(health_kb.match_topics(said), said)

    def test_the_kidney_topic_does_not_hijack_chinese_medicine(self):
        """中醫的「腎虛」「補腎」不是解剖學的腎——搶過來會答非所問。"""
        for said in ("我氣虛腎虛", "補腎要吃什麼"):
            self.assertEqual(health_kb.match_topics(said)[:1], ["TW-EDU-30"], said)

    def test_breathlessness_does_not_land_on_the_knee(self):
        """「爬樓梯就喘」被膝蓋題接走過——喘不是膝蓋的事。"""
        self.assertEqual(health_kb.match_topics("爬樓梯就喘")[0], "TW-EDU-39")
        self.assertEqual(health_kb.match_topics("我膝蓋爬樓梯會痛")[0], "TW-EDU-02")

    def test_salt_substitute_question_lands_on_blood_pressure(self):
        """會去買薄鹽的人幾乎都是為了血壓——問題該落在血壓題，不是腎臟題。"""
        for said in ("薄鹽可以用嗎", "低鈉鹽比較健康嗎"):
            self.assertEqual(health_kb.match_topics(said)[:1], ["TW-EDU-03"], said)


class KidneyTest(unittest.TestCase):
    def test_stage_decides_everything_leads(self):
        first = ids("TW-EDU-38", "我腎不好")[0]
        self.assertEqual(first, "ckd-stage-decides-everything")
        self.assertIn("相反", card("TW-EDU-38", "ckd-stage-decides-everything")["say"])

    def test_salt_substitute_is_named_as_dangerous_for_them(self):
        """薄鹽是拿鉀代替鈉——腎友用了會出事。這句在兩題都要在。"""
        self.assertIn("ckd-salt-substitute-danger", ids("TW-EDU-38", "薄鹽可以用嗎"))
        bp = card("TW-EDU-03", "bp-salt-substitute-caution")["say"]
        self.assertIn("鉀", bp)
        self.assertIn("腎", bp)

    def test_the_warning_card_carries_no_contraindications(self):
        """帶警告的卡不准帶禁忌——不然它會被自己的禁忌從最該聽的人面前濾掉
        （7 月青草茶顧腎那張就是這樣消失的）。"""
        for tid, sid in (("TW-EDU-38", "ckd-salt-substitute-danger"),
                         ("TW-EDU-03", "bp-salt-substitute-caution")):
            self.assertFalse(card(tid, sid).get("contraindications"), sid)

    def test_painkiller_habit_is_named(self):
        say = card("TW-EDU-38", "ckd-painkillers")["say"]
        self.assertIn("我腎功能不好", say, "要給他一句真的講得出口的話")

    def test_unknown_herbs_not_chinese_medicine_itself(self):
        """守住分別：危險的是沒來路的藥粉，不是中醫。"""
        say = card("TW-EDU-38", "ckd-unknown-herbs")["say"]
        self.assertIn("馬兜鈴酸", say)
        self.assertIn("合格", say)

    def test_protein_is_not_told_to_go_to_zero(self):
        """『顧腎不敢吃肉』會瘦到跌倒——這條要跟肌少症題不打架。"""
        c = card("TW-EDU-38", "ckd-protein-ask-dietitian")
        self.assertIn("不敢吃肉", c["say"], "要點出『少蛋白』被做過頭的那個失敗樣子")
        self.assertIn("營養師", c["say"], "要給他一個真的找得到人的下一步")

    def test_referral_covers_fluid_overload_and_high_potassium(self):
        ref = hs.pick("TW-EDU-38", "我腎不好", real(1945), 15)["referral"]
        self.assertIn("水腫", ref["say"])
        self.assertIn("119", ref["say"])


class LungTest(unittest.TestCase):
    def test_the_two_inhalers_lead(self):
        self.assertEqual(ids("TW-EDU-39", "我有氣喘", 1950)[0],
                         "lung-controller-vs-reliever")

    def test_describing_phlegm_surfaces_the_exacerbation_card(self):
        self.assertIn("lung-exacerbation-three-signs",
                      ids("TW-EDU-39", "我爸痰變多又變黃", 1985))

    def test_comfort_remedies_never_lead_and_never_replace_the_inhaler(self):
        c = card("TW-EDU-39", "lung-comfort-remedies")
        self.assertTrue(c["secondLine"])
        self.assertIn("不能拿來代替吸入劑", c["say"])
        self.assertNotEqual(ids("TW-EDU-39", "我有氣喘", 1950)[0], "lung-comfort-remedies")

    def test_quitting_smoking_is_told_straight(self):
        say = card("TW-EDU-39", "lung-quit-smoking")["say"]
        self.assertIn("唯一", say)

    def test_referral_is_an_airway_emergency(self):
        ref = hs.pick("TW-EDU-39", "我一直喘", real(1945), 15)["referral"]
        self.assertIn("119", ref["say"])
        self.assertIn("發紫", ref["say"])


class StrokeTest(unittest.TestCase):
    def test_recognising_the_next_one_leads_with_the_clock(self):
        first = card("TW-EDU-40", "stroke-fast-recognize")
        self.assertTrue(first["leadWith"])
        self.assertIn("119", first["say"])
        self.assertIn("時間", first["say"])

    def test_blood_thinners_are_never_stopped_alone(self):
        say = card("TW-EDU-40", "stroke-dont-stop-antiplatelet")["say"]
        self.assertIn("自己停", say)
        self.assertIn("拔牙", say, "要講他真的會遇到的那個場合")

    def test_folk_blood_clearing_is_answered_when_he_asks(self):
        got = ids("TW-EDU-40", "通血路的點滴有效嗎")
        self.assertIn("stroke-blocked-remedies", got)
        self.assertIn("出血", card("TW-EDU-40", "stroke-blocked-remedies")["say"])

    def test_the_caregiver_gets_the_respite_line(self):
        got = ids("TW-EDU-40", "我照顧我爸很累", profile={"audiences": ["caregiver"]})
        self.assertIn("stroke-caregiver-support", got)
        self.assertIn("1966", card("TW-EDU-40", "stroke-caregiver-support")["say"])


class BlockedCardsAreAnswersNotDeadWeightTest(unittest.TestCase):
    """三十幾張寫好卻從來沒出過場的誠實回話——這一節守它們真的接上了。"""

    @staticmethod
    def _all_blocked():
        with io.open(os.path.join(HERE, "health_solutions.json"), encoding="utf-8") as f:
            topics = json.load(f)["topics"]
        for tid, topic in topics.items():
            for sol in topic["solutions"]:
                if sol.get("blocked"):
                    yield tid, sol

    def test_every_blocked_card_can_be_reached_by_naming_it(self):
        """沒有點名字＝這張卡生下來就是死的，永遠不會被講出來。"""
        for tid, sol in self._all_blocked():
            self.assertTrue(sol.get("askedFor"), f"{tid}/{sol['id']} 沒有點名字")

    def test_naming_it_actually_serves_it(self):
        for tid, sol in self._all_blocked():
            said = sol["askedFor"][0]
            got = ids(tid, said, profile={"audience": "elder", "audiences": ["elder"]})
            self.assertIn(sol["id"], got, f"{tid}：他講了「{said}」還是沒回答")

    def test_it_is_never_the_first_thing_said(self):
        """「我不能建議」當第一句像打發人——做得到的事要先講。"""
        for tid, sol in self._all_blocked():
            got = ids(tid, sol["askedFor"][0],
                      profile={"audience": "elder", "audiences": ["elder"]})
            if len(got) > 1:
                self.assertNotEqual(got[0], sol["id"], f"{tid}/{sol['id']} 當了第一句")

    def test_it_stays_quiet_when_he_did_not_bring_it_up(self):
        quiet = (("TW-EDU-01", "我睡不好"), ("TW-EDU-03", "我血壓有點高"),
                 ("TW-EDU-34", "我想減肥"), ("TW-EDU-38", "我腎不好"),
                 ("TW-EDU-40", "我爸中風過"))
        for tid, said in quiet:
            for sid in ids(tid, said):
                self.assertFalse(card(tid, sid).get("blocked"),
                                 f"{tid}：他沒問，我們卻主動講起 {sid}")

    def test_a_short_stem_does_not_drag_it_in(self):
        """「瘦」一個字會把「我想瘦一點」也算進來——那對想減重的人是刺耳的。"""
        self.assertNotIn("wt-unintended-loss", ids("TW-EDU-34", "我想瘦一點", 1980))
        self.assertIn("wt-unintended-loss", ids("TW-EDU-34", "我最近瘦了好多", 1945))
        self.assertNotIn("preg-med-blocked",
                         ids("TW-EDU-29", "懷孕能不能吃木瓜",
                             profile={"audience": "women", "audiences": ["women"]}))

    def test_the_injected_text_does_not_dress_it_up_as_a_recommendation(self):
        """render 不准把「這個沒有用」掛上主推的頭銜，也不准接保健品那段上限話術。"""
        out = hs.render("TW-EDU-38", "顧腎的保健品有用嗎", real(1945), 15)
        self.assertIn("他自己問到這個", out)
        self.assertNotIn("主推·慢養檔·保健品", out)
        self.assertNotIn("一天上限", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
