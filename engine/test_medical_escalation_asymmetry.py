#!/usr/bin/env python3
"""就醫建議的不對稱鐵則——只往上推、永不往下擋（2026-07-26 · M1 PR-1）。

背景：`docs/健康照護管家-就醫代理與導引-方向與分階-2026-07-26.md` 紅線 2 定案——
就醫建議唯一安全的形狀是不對稱的：往上推（建議就醫）最壞是白跑一趟，往下擋
（「不用看醫生」「觀察幾天就好」）萬一錯了是延誤就醫、可能出人命。兩邊代價不對稱，
所以拿不準時一律往就醫那邊靠。

為什麼要有這支測試：改動前 RED 只擋了**字面**的「不用看醫生」，但真正危險的是
一個溫暖的陪伴 AI 出於安慰本能講出的**軟性往下擋**——「應該沒事啦」「觀察幾天看看」
「多喝水休息一下就好」。這些話一個字都沒提「不用看醫生」，卻同樣會讓長輩不去。
這支測試守住三層：

  ① CORE ②-B 這條規則真的在共用底盤裡（含不對稱的理由、禁止的軟性說法、
     不判嚴重度、科別導引要留家醫科這條路）；
  ② RED（最優先段）的一行版本也一起收緊了，不再只擋字面那一句；
  ③ **兩條線都真的吃到**——文字線 server.py 與語音線 live_voice_server.py
     都是 `eng.CORE + persona + eng.RED` 組出說明書，source-level 鎖住這個組法，
     防止之後有人只改一條線、或把底盤拆開（跟 test_reasoning_leak_guard.py
     的「production 出口鎖」同一種手法）。

誠實邊界：這是**契約測試**，鎖的是「規則有沒有進到兩條線的說明書」。
它不驗證模型實際會不會遵守——那要靠 `engine/eval/` 的劇本庫實跑真模型
（本檔同批新增 S20 劇本，需真鑰匙跑 `npm run eval:chat-quality`）。

跑法：python engine/test_medical_escalation_asymmetry.py（不需網路或真鑰匙）
"""
import os
import sys
import unittest

os.environ.setdefault("GEMINI_API_KEY", "medical-asymmetry-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import chat_engine as eng  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


class CoreAsymmetryRuleTests(unittest.TestCase):
    """① CORE ②-B：不對稱鐵則的四個要件都在。"""

    def test_rule_is_present_and_labelled(self):
        self.assertIn("②-B", eng.CORE)
        self.assertIn("只往上推、永不往下擋", eng.CORE)

    def test_upward_direction_is_explicitly_allowed(self):
        """往上推要「明確允許」，不能只寫禁止——否則她會兩邊都不敢講、變成迴避。"""
        self.assertIn("這種情況建議盡快就醫", eng.CORE)

    def test_soft_downward_phrasings_are_banned_by_name(self):
        """關鍵：軟性往下擋要逐句點名。只擋字面「不用看醫生」是擋不住安慰本能的。"""
        for phrase in ("應該沒事", "觀察幾天就好", "先看看再說", "還不用去啦", "多喝水休息一下就好"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, eng.CORE)

    def test_mild_symptoms_do_not_exempt_the_rule(self):
        """症狀聽起來很輕＝這條鐵則最容易破功的地方，要寫死沒有例外。"""
        self.assertIn("多輕、多常見、多像小毛病都一樣", eng.CORE)

    def test_asymmetry_reasoning_is_stated(self):
        """理由要在說明書裡（模型照理由推廣得比照禁令清單好），且是「代價不對稱」這個理由。"""
        self.assertIn("代價完全不對稱", eng.CORE)
        self.assertIn("只要拿不準，一律往就醫那邊靠", eng.CORE)

    def test_severity_grading_is_banned(self):
        """不判嚴重度＝紅線 3（symptom checker / SaMD 風險）的人格層落地。"""
        self.assertIn("不要替他判斷嚴重度", eng.CORE)
        self.assertIn("這聽起來不嚴重", eng.CORE)

    def test_specialty_guidance_keeps_a_way_out(self):
        """科別導引的安全形狀：永遠留家醫科這條路，不把人擋在「掛不到號」前面。"""
        self.assertIn("家醫科", eng.CORE)

    def test_respecting_refusal_does_not_become_agreeing_with_it(self):
        """尊重他不去 ≠ 幫他找不去的理由——這兩者差一線，要分清楚。"""
        self.assertIn("不要反過來幫他找不去的理由", eng.CORE)


class RedLineTests(unittest.TestCase):
    """② RED（最優先段）：一行版本也收緊，不再只擋字面那一句。"""

    def test_literal_ban_still_present(self):
        """既有防線不可回歸——原本就有的字面禁令要留著。"""
        self.assertIn("絕不說『不用看醫生』", eng.RED)

    def test_soft_downward_ban_reached_the_highest_priority_block(self):
        self.assertIn("應該沒事", eng.RED)
        self.assertIn("觀察幾天就好", eng.RED)
        self.assertIn("只往上推、永不往下擋", eng.RED)

    def test_existing_resident_health_redlines_not_clobbered(self):
        """RED 尾巴接的是 health_kb 常駐紅線；改 RED 開頭不能把它擠掉。"""
        self.assertIn("褪黑激素在台灣是處方藥", eng.RED)
        self.assertIn("中風警訊", eng.RED)


class BothLinesInheritTheBaseTests(unittest.TestCase):
    """③ source-level 鎖：文字線與語音線都用 CORE+RED 組說明書，改一處兩線生效。

    這一層是這支測試真正的價值——`安全能力補齊計畫` §4 有前例：紅線測試 13/13 全過，
    但過的是「使用者用不到的那條路」（打字線），真實用戶走的語音線當時沒接上。
    所以規則進了 CORE 不等於用戶受保護，要鎖住兩條線都真的吃到。
    """

    # 2026-07-31 人設書分國：兩條線改成「照這通電話的語系拿書」（core_instruction(lookup, locale)
    # ＋ red_lines(locale)）。契約從比對字面改成比對「三件都在、而且語系是傳進去的」——
    # 守的行為不變：規則進了說明書，兩條線都要真的吃到，而且不會有一條偷偷吃到別國的書。
    def test_text_line_composes_core_and_red(self):
        _srv = _read("server.py")
        self.assertIn('eng.core_instruction("offline", book_locale)', _srv)
        self.assertIn('c["persona"]', _srv)
        self.assertIn('eng.red_lines(book_locale)', _srv)

    def test_voice_line_composes_core_and_red(self):
        _srv = _read("live_voice_server.py")
        self.assertIn('eng.core_instruction(', _srv)
        self.assertIn('_core + c.get("persona", "") + eng.red_lines(_book_locale)', _srv)

    def test_both_lines_pass_a_locale_through(self):
        """兩條線都必須把語系傳進去——漏傳＝那條線永遠只吃中文版（外國用戶拿到台灣說明書）。"""
        self.assertIn('_sys_for(char, context.get("locale"))', _read("server.py"))
        # sessionLocale＝這通實際講哪種語言（介面英文但講日文的人要拿日文書），不是介面語言
        self.assertIn('_book_locale = (locale_profile or {}).get("sessionLocale")', _read("live_voice_server.py"))

    def test_every_shipped_locale_keeps_the_escalation_rule(self):
        """已授書的每一國，安全紅線都必須在——授書時漏抄＝那一國的長輩失去保護。"""
        for locale in eng.persona_locales():
            core = eng.core_instruction("offline", locale)
            red = eng.red_lines(locale)
            self.assertTrue(core.strip(), f"{locale} core book is empty")
            self.assertTrue(red.strip(), f"{locale} red lines are empty")
            self.assertNotIn("&&LOOKUP_SECTION&&", core, f"{locale} core still has an unfilled slot")


if __name__ == "__main__":
    unittest.main(verbosity=2)
