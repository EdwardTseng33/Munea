"""證據測試：各國安全題組的接線是通的、判準沒漏（不花錢、不呼叫模型）。

為什麼需要這支：考卷分國之後，最容易發生的不是「考不過」，而是**考卷根本沒在考那一國**——
劇本裡寫了 locale 但沒傳到工作程序，於是日文題其實是用繁中說明書答的、看起來還全過。
這種假綠比紅燈危險得多。

所以這裡檢查四件事（全部靜態、不跑模型）：
  ① 每一題都有語系、對話、以及自己的判準（各國正確答案不同，不能吃全域的中文鐵律）
  ② 每一國的題目都涵蓋最會出人命的那條：就醫不對稱（②-B）
  ③ 判準裡的急難號碼跟該國一致，而且沒有別國的號碼
  ④ 接線真的通：語系從劇本 → 工作程序 → 評審，三段都在

執行：python scripts/test_locale_safety_exam.py（也掛在 npm run test:launch 底下）
"""
import io
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVAL_DIR = os.path.join(ROOT, "engine", "eval")
BANK_PATH = os.path.join(EVAL_DIR, "chat_quality", "scenarios_locale_safety.json")

# 每一國的急難號碼：出現別國的號碼＝那一本書漏抄了，或判準抄錯國家
EXPECTED_NUMBERS = {"ja": "119", "en": "911", "es": "112"}
FOREIGN_NUMBERS = {"1925", "1995", "113"}   # 台灣專屬，不該出現在他國判準裡


def _read(relative_path):
    with io.open(os.path.join(EVAL_DIR, relative_path), encoding="utf-8") as handle:
        return handle.read()


class LocaleSafetyExamTests(unittest.TestCase):
    def setUp(self):
        with io.open(BANK_PATH, encoding="utf-8") as handle:
            self.bank = json.load(handle)
        self.scenarios = self.bank["scenarios"]

    def test_every_scenario_is_self_contained(self):
        for item in self.scenarios:
            sid = item.get("id", "<no id>")
            self.assertTrue(item.get("locale"), f"{sid}：沒寫是哪一國，會用繁中說明書作答")
            self.assertTrue(item.get("turns"), f"{sid}：沒有對話")
            self.assertTrue(
                item.get("hardRules"),
                f"{sid}：沒有自己的判準——會吃全域的中文鐵律，判不出這一國的正確答案",
            )

    def test_every_locale_covers_the_escalation_rule(self):
        """②-B 就醫不對稱是安全面最重的一條，每一國都必須有題在考它。"""
        by_locale = {}
        for item in self.scenarios:
            by_locale.setdefault(item["locale"], []).append(item)
        for locale, items in by_locale.items():
            has_escalation = any("escalation" in (i.get("categories") or []) for i in items)
            self.assertTrue(has_escalation, f"{locale}：沒有一題在考就醫不對稱（②-B）")

    def test_criteria_carry_the_right_country_numbers(self):
        for item in self.scenarios:
            locale = item["locale"]
            rules = " ".join(item["hardRules"])
            expected = EXPECTED_NUMBERS.get(locale)
            if expected and "escalation" in (item.get("categories") or []):
                self.assertIn(
                    expected, rules,
                    f"{item['id']}：判準裡沒有 {locale} 的急難號碼 {expected}",
                )
            for foreign in FOREIGN_NUMBERS:
                if expected and foreign == expected:
                    continue
                # 台灣號碼只能以「不得出現」的形式被提到（那是反向守門，允許）
                if foreign in rules:
                    self.assertTrue(
                        any(word in rules for word in ("出ていない", "do not appear", "No aparecen")),
                        f"{item['id']}：判準裡出現了台灣號碼 {foreign}，而且不是反向守門",
                    )

    def test_locale_actually_reaches_the_worker_and_the_judge(self):
        """接線鎖：劇本寫了語系卻沒傳下去＝日文題其實用繁中說明書作答（假綠）。"""
        runner = _read("run_chat_quality_eval.py")
        self.assertIn('gen_payload["locale"] = item["locale"]', runner,
                      "跑卷程式沒把語系傳給工作程序")
        self.assertIn('"locale": item.get("locale")', runner,
                      "跑卷程式沒把語系傳給評審")
        self.assertIn('item.get("hardRules") or HARD_RULE_CRITERIA', runner,
                      "跑卷程式沒有優先採用劇本自帶的判準")

        worker = _read("gen_reply.py")
        self.assertIn('data["locale"] = case["locale"]', worker,
                      "文字線工作程序沒把語系傳進說明書組裝")
        self.assertIn("locale_profile=_profile", worker,
                      "單輪路徑沒把語系傳進說明書組裝")

        live_worker = _read("gen_reply_live.py")
        self.assertIn("locale_profile=_profile", live_worker,
                      "真語音線工作程序沒把語系傳進說明書組裝")

        judge = _read("judge.py")
        self.assertIn("locale=case.get(\"locale\")", judge, "評審沒收到語系")
        self.assertIn("_judge_system(locale)", judge, "評審沒有依語系調整判卷說明")

    def test_the_bank_is_switchable_from_the_command_line(self):
        runner = _read("run_chat_quality_eval.py")
        self.assertIn('parser.add_argument("--scenarios"', runner,
                      "沒辦法從指令換題庫，這份題組永遠跑不到")
        self.assertIn("load_scenarios(args.scenarios)", runner,
                      "--scenarios 沒有真的接到讀題庫那一步")


if __name__ == "__main__":
    unittest.main(verbosity=2)
