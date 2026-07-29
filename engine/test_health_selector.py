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


class ThreeAgeBandsTest(unittest.TestCase):
    """三齡層（高齡／中齡／青少齡）＋代問（2026-07-29 Edward 加的線）。"""

    def test_teen_saying_tired_gets_the_teen_topic_not_the_adult_one(self):
        """真實抓到的 bug：青少年說「睡不飽」會同時命中成人失眠題，
        結果拿到「白天曬太陽對長輩特別有效」——對高中生答非所問。"""
        import health_kb
        out = health_kb.injection_for("我每天都睡不飽，早上超痛苦",
                                      profile={"audience": "teen"}, hour=8)
        self.assertIn("生理時鐘", out)          # 青少年題的內容
        self.assertNotIn("對長輩特別有效", out)  # 不可以是長輩版

    def test_parent_asking_gets_the_translation_first(self):
        """家長代問：第一句要先把「他不是懶、是生理」翻譯出來，火才會小。"""
        r = hs.pick("TW-EDU-23", "我小孩每天熬夜，早上都叫不起來", {"audience": "teen"}, 8)
        self.assertTrue(r["proxy"])
        self.assertIsNotNone(r["reframe"])
        self.assertIn("不是懶", r["reframe"])

    def test_teen_asking_for_self_is_not_treated_as_proxy(self):
        r = hs.pick("TW-EDU-23", "我每天都睡不飽", {"audience": "teen"}, 8)
        self.assertFalse(r["proxy"])
        self.assertNotIn("teen-explain-biology", ids(r))   # 那句是講給家長聽的

    def test_parent_only_solutions_never_reach_the_teen(self):
        r = hs.pick("TW-EDU-23", "我每天都睡不飽", {"audience": "teen"}, 8)
        for s in r["solutions"]:
            self.assertNotEqual(s.get("forWhom"), "parent")

    def test_teen_referral_carries_the_crisis_line(self):
        """青少年這條線最危險的是情緒——轉介卡必須帶危機專線。"""
        r = hs.pick("TW-EDU-23", "我每天都睡不飽", {"audience": "teen"}, 8)
        self.assertIn("1925", r["referral"]["say"])


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


class TcmAndCrossTopicTest(unittest.TestCase):
    """中醫（項目7）與跨題連結（項目8）——2026-07-29 Edward 指定的兩項。"""

    def test_acupressure_is_offered_when_he_mentions_tcm(self):
        """他自己提中醫＝願意走調理路線，中醫類要真的浮上來（不是只給西方那套）。"""
        r = hs.pick("TW-EDU-01", "我睡不好，想說看中醫調理", WORKER, 22)
        self.assertTrue(any(s["solutionType"] == "中醫調理" for s in r["solutions"]))

    def test_herbal_medicine_is_never_pushed(self):
        """中藥要中醫師把脈開方——屬處方級，任何情況都不主動推。"""
        for text in ("我睡不好，想吃中藥", "我睡不好", "中醫可以調嗎"):
            r = hs.pick("TW-EDU-01", text, WORKER, 22)
            self.assertNotIn("sleep-tcm-herbs", ids(r))

    def test_herbal_entry_carries_the_real_safety_fact(self):
        """關鍵安全事實：中西藥隔一兩小時仍算併用，不是錯開時間就沒事。"""
        herb = next(s for s in hs.TOPICS["TW-EDU-01"]["solutions"] if s["id"] == "sleep-tcm-herbs")
        self.assertIn("隔一兩個小時吃就沒事", herb["say"])
        self.assertIn("還是算一起吃", herb["say"])

    def test_cross_topic_link_only_when_he_raises_it(self):
        """睡不好＋壓力常是同一件事——但只在他自己也提到時才連，不硬拉話題。"""
        self.assertIsNotNone(hs.pick("TW-EDU-01", "我睡不好，壓力又大", WORKER, 23).get("related"))
        self.assertIsNone(hs.pick("TW-EDU-01", "我睡不好", WORKER, 23).get("related"))


class StressTopicTest(unittest.TestCase):
    """工作壓力／情緒耗竭（項目5）——Edward 最初的例子就是工作壓力。"""

    def test_caregiver_saying_tired_is_not_treated_as_proxy(self):
        """「我照顧我媽照顧到好累」句子裡有「我媽」，但主角是他自己。"""
        r = hs.pick("TW-EDU-25", "我照顧我媽照顧到好累", CAREGIVER, 22)
        self.assertFalse(r["proxy"])
        self.assertIsNotNone(r["reframe"])
        self.assertIn("沒有下班時間", r["reframe"])

    def test_caregiver_gets_respite_worker_does_not(self):
        c = ids(hs.pick("TW-EDU-25", "我照顧到快撐不住", CAREGIVER, 22))
        w = ids(hs.pick("TW-EDU-25", "我工作壓力好大", WORKER, 22))
        self.assertIn("stress-caregiver-respite", c)
        self.assertNotIn("stress-caregiver-respite", w)

    def test_stress_referral_carries_two_week_rule_and_crisis_line(self):
        r = hs.pick("TW-EDU-25", "我壓力好大", WORKER, 22)
        self.assertIn("兩個禮拜", r["referral"]["say"])
        self.assertIn("1925", r["referral"]["say"])


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


class SecondLineTest(unittest.TestCase):
    """陪襯層：可以講、但不准當主力（2026-07-29 搬膝蓋題時抓到）。

    當初的設計是「潑保健品冷水的同一句一定要帶更有效的替代」，
    結果排序把證據最弱的葡萄糖胺頂到第一個——設計整個反過來。
    """

    def test_weak_evidence_supplement_never_leads(self):
        first = hs.pick("TW-EDU-02", "膝蓋痛，爬樓梯特別酸", ELDER, 15)["solutions"][0]
        self.assertNotEqual(first["id"], "knee-glucosamine",
                            "證據偏弱的保健品排到第一個＝把最弱的當主力")

    def test_stronger_alternative_leads_instead(self):
        picked = hs.pick("TW-EDU-02", "膝蓋痛，爬樓梯特別酸", ELDER, 15)["solutions"]
        self.assertIn(picked[0]["id"], ("knee-thigh-strength", "knee-weight"),
                      "實證更明確的肌力訓練／體重控制沒排在前面")

    def test_comfort_lines_do_not_take_an_action_slot(self):
        """「這很普遍、不是你特別差」是配菜，不該吃掉行動建議的位子。"""
        ids = [s["id"] for s in hs.pick("TW-EDU-03", "我血壓又高了", ELDER, 8)["solutions"]]
        self.assertNotEqual(ids[0], "bp-normalize")

    def test_what_he_asked_about_by_name_is_answered_not_buried(self):
        """他點名問的東西被降級切掉＝問了不答，比排序難看得多。"""
        picked = hs.pick("TW-EDU-02", "葡萄糖胺到底有沒有效？我膝蓋不好", ELDER, 15)["solutions"]
        self.assertEqual(picked[0]["id"], "knee-glucosamine")

    def test_answering_the_supplement_still_offers_a_better_path(self):
        ids = [s["id"] for s in hs.pick("TW-EDU-02", "葡萄糖胺有效嗎", ELDER, 15)["solutions"]]
        self.assertTrue({"knee-thigh-strength", "knee-weight"} & set(ids),
                        "潑了冷水卻沒給更有效的替代路")


class MigratedTopicsTest(unittest.TestCase):
    """2026-07-29 第二批搬進方案池的四題，各自最要命的那條要守住。"""

    def test_reflux_always_carries_the_heart_attack_red_line(self):
        ref = hs.pick("TW-EDU-11", "我火燒心", WORKER, 22)["referral"]
        self.assertIsNotNone(ref)
        self.assertIn("心", ref["say"])

    def test_blood_pressure_never_touches_medication(self):
        for prof in (ELDER, CAREGIVER, WORKER):
            for s in hs.pick("TW-EDU-03", "我血壓高，是不是要加藥", prof, 9)["solutions"]:
                self.assertNotEqual(s.get("riskLevel"), "L4", "把調藥端上桌了")

    def test_red_yeast_interaction_surfaces_when_he_mentions_it(self):
        ids = [s["id"] for s in hs.pick("TW-EDU-16", "我在吃紅麴", ELDER, 14)["solutions"]]
        self.assertIn("supp-red-yeast", ids, "紅麴配降血脂藥是這題最重要的一條，沒講到")

    def test_kidney_trouble_removes_the_potassium_advice(self):
        prof = {"audience": "elder", "conditions": ["腎功能異常"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-03", "我血壓高", prof, 9)["solutions"]]
        self.assertNotIn("bp-dash-diet", ids, "腎功能不好還叫他補鉀")

    def test_worker_and_elder_get_different_reflux_advice(self):
        w = [s["id"] for s in hs.pick("TW-EDU-11", "我火燒心", WORKER, 23)["solutions"]]
        e = [s["id"] for s in hs.pick("TW-EDU-11", "我火燒心", ELDER, 9)["solutions"]]
        self.assertNotEqual(w, e, "上班族跟長輩拿到一模一樣的答案＝因人而異沒生效")


class CaregiverProxyTest(unittest.TestCase):
    """照顧者替家人問時，方案是要給**被照顧的那位**用的（2026-07-29 骨鬆題抓到）。

    「我媽有骨鬆，怕她跌倒」原本只比對 caregiver，專為長輩寫的「練肌力跟平衡」
    拿不到專屬度加分、被通用建議擠掉——防跌實證最明確的那條反而沒端出去。
    """

    def test_elder_specific_advice_surfaces_when_a_caregiver_asks_for_a_parent(self):
        ids = [s["id"] for s in hs.pick("TW-EDU-17", "我媽有骨鬆，怕她跌倒",
                                        {"audience": "caregiver"}, 14)["solutions"]]
        self.assertIn("osteo-strength-balance", ids, "防跌實證最明確的那條沒端出去")

    def test_caregivers_own_needs_are_not_crowded_out(self):
        """兩個齡層都算數——照顧者自己的喘息方案照樣要浮得上來。"""
        ids = [s["id"] for s in hs.pick("TW-EDU-18", "照顧我媽照顧到快崩潰了",
                                        {"audience": "caregiver"}, 22)["solutions"]]
        self.assertIn("mood-caregiver-respite", ids)

    def test_a_caregiver_complaining_about_himself_is_not_treated_as_proxy(self):
        """「我媽三點要起來，我根本睡不飽」講的是他自己——不能當成替媽媽問。"""
        res = hs.pick("TW-EDU-01", "我媽三點要起來，我根本睡不飽",
                      {"audience": "caregiver", "constraints": ["照顧者夜間需起身"]}, 2)
        self.assertFalse(res["proxy"])
        self.assertIsNotNone(res["reframe"], "沒接住「你不是失眠、是沒得睡」")


class Batch3Test(unittest.TestCase):
    """第三批五題：便秘／腳抽筋／骨鬆防跌／情緒低落／記性變差。"""

    def test_burnt_out_caregiver_is_caught_at_all(self):
        """「照顧到快崩潰」原本一個關鍵字都沒命中——最需要接住的人漏接。"""
        self.assertTrue(health_kb_match("照顧我媽照顧到快崩潰了"))

    def test_suicidal_signals_always_reach_the_hotline(self):
        for prof in ({"audience": "elder"}, {"audience": "caregiver"}, {"audience": "teen"}):
            ref = hs.pick("TW-EDU-18", "覺得活著沒什麼意思", prof, 23)["referral"]
            self.assertIsNotNone(ref)
            self.assertIn("1925", ref["say"], "沒給安心專線")

    def test_evidence_backed_stretch_beats_the_folk_remedy(self):
        first = hs.pick("TW-EDU-15", "半夜小腿一直抽筋", ELDER, 23)["solutions"][0]
        self.assertEqual(first["id"], "cramp-stretch-before-bed")

    def test_exercise_beats_brain_supplements(self):
        """池子自己就寫了「運動的證據比補腦品強」——排序不能把自己的話講反。"""
        first = hs.pick("TW-EDU-14", "我最近記性變差", ELDER, 11)["solutions"][0]
        self.assertNotEqual(first["id"], "mci-brain-supp")

    def test_sudden_confusion_is_flagged_as_delirium_not_dementia(self):
        ref = hs.pick("TW-EDU-14", "我媽突然認不得人", {"audience": "caregiver"}, 20)["referral"]
        self.assertIn("譫妄", ref["say"])

    def test_immunocompromised_never_gets_probiotics(self):
        prof = {"audience": "worker", "conditions": ["免疫功能低下"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-06", "我便秘", prof, 10)["solutions"]]
        self.assertNotIn("consti-probiotics", ids)

    def test_kidney_trouble_never_gets_magnesium_for_cramps(self):
        prof = {"audience": "worker", "conditions": ["腎功能異常"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-15", "我一直抽筋，鎂有用嗎", prof, 23)["solutions"]]
        self.assertNotIn("cramp-magnesium", ids)

    def test_kidney_stones_never_gets_calcium_supplement(self):
        prof = {"audience": "women", "conditions": ["有腎結石病史"]}
        ids = [s["id"] for s in hs.pick("TW-EDU-17", "骨鬆要吃鈣片嗎", prof, 14)["solutions"]]
        self.assertNotIn("osteo-calcium-vitd-supp", ids)


def health_kb_match(text):
    import health_kb
    return health_kb.match_topics(text)


class Batch4Test(unittest.TestCase):
    """最後一批十題：糖尿病／痛風／頭暈／眼睛／皮膚癢／夜尿／疫苗／吞嚥／感冒／心悸。

    TW-EDU-21 LINE 謠言查證刻意不搬——那題是「三級判斷程序」（權威已闢謠→只轉述／
    查不到→給懷疑線索＋教他自己查／涉停藥→一律加提醒），不是一組可互相替換的方案。
    硬塞進池子會把程序拆散。方案池不是萬用結構。
    """

    def test_low_blood_sugar_always_says_sugar_and_119_together(self):
        """只講「趕快吃糖」不講「叫不醒要打119」＝把人留在最危險的那一步。"""
        ref = hs.pick("TW-EDU-04", "我有糖尿病", ELDER, 10)["referral"]
        self.assertIn("119", ref["say"])
        self.assertIn("糖", ref["say"])

    def test_an_active_gout_flare_is_treated_as_urgent(self):
        res = hs.pick("TW-EDU-05", "痛風又發作了，腳趾頭腫起來", WORKER, 20)
        self.assertTrue(res["urgent"], "正在發作卻不算急，今晚能做的排不到前面")
        self.assertEqual(res["solutions"][0]["id"], "gout-avoid-triggers")

    def test_dizziness_always_carries_the_stroke_red_line(self):
        ref = hs.pick("TW-EDU-07", "我站起來就會暈", ELDER, 8)["referral"]
        for word in ("119", "無力", "嘴歪"):
            self.assertIn(word, ref["say"])

    def test_lutein_never_claims_to_reverse_cataract(self):
        sol = next(s for s in hs.TOPICS["TW-EDU-08"]["solutions"] if s["id"] == "eye-lutein")
        self.assertIn("沒有逆轉的證據", sol["say"])

    def test_choking_gets_119_not_chew_slowly(self):
        ref = hs.pick("TW-EDU-13", "我媽最近常嗆到", {"audience": "caregiver"}, 12)["referral"]
        self.assertIn("119", ref["say"])
        self.assertIn("哈姆立克", ref["say"])

    def test_cold_medicine_advice_leads_with_the_interaction_warning(self):
        first = hs.pick("TW-EDU-19", "我感冒了，可以吃家裡的感冒藥嗎", ELDER, 15)["solutions"][0]
        self.assertEqual(first["id"], "cold-ask-pharmacist")

    def test_palpitations_never_get_judged_benign_or_dangerous(self):
        for s in hs.pick("TW-EDU-20", "最近心跳很快", WORKER, 23)["solutions"]:
            self.assertNotEqual(s.get("riskLevel"), "L4")

    def test_vaccine_is_the_one_topic_we_may_nudge(self):
        """疫苗是唯一該主動推一把的題——公費資格要講出來。"""
        ids = [s["id"] for s in hs.pick("TW-EDU-12", "要不要去打疫苗",
                                        {"audience": "caregiver"}, 10)["solutions"]]
        self.assertIn("vax-free-eligibility", ids)

    def test_itchy_skin_survives_an_inserted_character(self):
        """「皮膚**一直**癢」——插一個字就整組叫不出來，這個漏洞已經咬過三次。"""
        import health_kb
        for said in ("冬天皮膚一直癢", "身體好癢", "癢到睡不著"):
            self.assertTrue(health_kb.match_topics(said), said)

    def test_rumor_check_deliberately_stays_on_fixed_text(self):
        self.assertNotIn("TW-EDU-21", hs.TOPICS,
                         "謠言查證被搬進池子了——那是判斷程序、不是可替換的方案")


class TypeDiversityTest(unittest.TestCase):
    """多樣性只是偏好，不該把「我不會主動推」的東西推上桌（2026-07-29 夜尿題抓到）。"""

    def test_diversity_never_promotes_a_second_line_item_over_a_real_one(self):
        ids = [s["id"] for s in hs.pick("TW-EDU-10", "晚上要起來尿好幾次", ELDER, 22)["solutions"]]
        self.assertNotIn("noct-saw-palmetto", ids,
                         "自己說「證據弱、不主動推」的東西被主動端出來了")

    def test_diversity_still_applies_among_normal_solutions(self):
        """正規方案夠多時，同類型仍不該連上三個。"""
        picked = hs.pick("TW-EDU-01", "我睡不好", WORKER, 14)["solutions"]
        types = [s.get("solutionType") for s in picked]
        self.assertLess(max(types.count(t) for t in set(types)), 3)


class DataIntegrityTest(unittest.TestCase):
    """資料本身的紀律——內容寫壞了這裡先亮紅燈。"""

    def test_migrated_topics_no_longer_carry_fixed_text(self):
        """搬進方案池的題目若 inject 還留舊固定稿＝兩份真相打架。"""
        import json
        with open(os.path.join(HERE, "health_topics.json"), encoding="utf-8") as f:
            topics = json.load(f)["topics"]
        for t in topics:
            if t["id"] in hs.TOPICS:
                self.assertIn("方案池", t.get("inject", ""),
                              f"{t['id']} 已有方案池，inject 卻還是舊固定稿")

    def test_every_pool_has_a_referral_card(self):
        for tid, topic in hs.TOPICS.items():
            self.assertTrue(any(s.get("riskLevel") == "L5" for s in topic["solutions"]),
                            f"{tid} 沒有轉介卡——出事沒有出口")

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
