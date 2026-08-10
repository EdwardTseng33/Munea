"""每日巡錢 · 守門測試（2026-08-10）。

這支工具只有兩個性質不能壞，其他都是細節：

  ① 查不到的帳，**絕不可以**變成一份乾淨的「沒事」報告。
     2026-08-06 踩過：GLOWS 認證失敗回 HTTP 200 加 code=176，程式讀成「一張卡都沒有」
     ——「通行碼壞了」跟「真的沒有卡」長得一模一樣（PR #532）。
     這支工具存在的理由就是抓漏，看漏了比不看更糟：會給人「已經在管了」的錯覺。

  ② 沒人用卻在收錢的東西要被標出來、而且要換算成錢。
     8/7 我沒有任何數字，所以講得出「修好了」。有數字就講不出來。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "spend_audit", os.path.join(HERE, "spend-audit.py"))
spend_audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spend_audit)


class UnavailableMustBeLoud(unittest.TestCase):
    def test_report_says_it_is_incomplete(self):
        text, waste, rows = spend_audit.render(
            reports=[{"source": "RunPod", "balance_usd": 10.0, "items": [], "note": ""}],
            unavailable=["GLOWS 每一把通行碼都問不到"],
        )
        self.assertIn("這份報告不完整", text,
                      "有帳查不到卻沒警告——會被當成沒事，那正是這支工具要防的")
        self.assertNotIn("✅", text, "查不到的時候不可以出現全綠的結論")

    def test_exit_code_for_unavailable_is_worse_than_waste(self):
        """查不到要比「有浪費」更嚴重——因為報告本身不可信。"""
        self.assertEqual(spend_audit.EXIT_OK, 0)
        self.assertEqual(spend_audit.EXIT_WASTE, 1)
        self.assertEqual(spend_audit.EXIT_UNAVAILABLE, 2)
        self.assertGreater(spend_audit.EXIT_UNAVAILABLE, spend_audit.EXIT_WASTE)

    def test_all_green_only_when_nothing_missing(self):
        text, _, _ = spend_audit.render(
            reports=[{"source": "RunPod", "balance_usd": 10.0, "items": [], "note": ""}],
            unavailable=[],
        )
        self.assertIn("✅", text)


class WasteMustCarryANumber(unittest.TestCase):
    def test_idle_item_is_flagged_and_priced(self):
        text, waste, rows = spend_audit.render(
            reports=[{
                "source": "RunPod", "balance_usd": -0.05, "note": "",
                "items": [
                    {"kind": "硬碟", "name": "空櫃子", "detail": "120 GB · US-WA-1",
                     "usd_per_month": 7.92, "wasteful": True},
                    {"kind": "機器", "name": "在用的", "detail": "執行中",
                     "usd_per_month": 100.0, "wasteful": False},
                ],
            }],
            unavailable=[],
        )
        self.assertIn("🔴 沒人用", text)
        self.assertEqual(len(rows), 1, "把「有人在用」的也算成浪費了")
        self.assertAlmostEqual(waste, 7.92, places=2,
                               msg="金額算錯——沒有數字就沒有人會去處理")
        self.assertIn("NT$", text, "只寫美金，Edward 看不出有多痛")

    def test_no_pods_means_every_volume_is_idle(self):
        """一台機器都沒有的時候，硬碟必定沒人用——那正是 8/10 漏掉的那一類。"""
        idle = spend_audit._classify_volumes_idle(pods=[])
        self.assertTrue(idle)
        self.assertFalse(spend_audit._classify_volumes_idle(pods=[{"id": "x"}]))


class KeyLookupQuirks(unittest.TestCase):
    def test_bom_prefixed_env_file_still_yields_key(self):
        """Windows 上編輯過的設定檔開頭有看不見的記號，用一般讀法會整把鑰匙漏掉。"""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            with open(p, "w", encoding="utf-8-sig") as fh:
                fh.write('SOME_KEY="abc123"\n')
            got = spend_audit._find_keys("SOME_KEY", None, [p])
            self.assertEqual([v for v, _ in got], ["abc123"],
                             "開頭有隱形記號就讀不到鑰匙——會謊報成「找不到鑰匙」")

    def test_every_candidate_is_returned_not_just_the_first(self):
        """保險箱那把過期、本機那把是活的——只取第一把會讓整份報告變成查不到。"""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.env"), os.path.join(d, "b.env")
            open(a, "w", encoding="utf-8").write("K=old\n")
            open(b, "w", encoding="utf-8").write("export K=new\n")
            got = [v for v, _ in spend_audit._find_keys("K", None, [a, b])]
            self.assertEqual(got, ["old", "new"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
