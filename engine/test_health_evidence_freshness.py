#!/usr/bin/env python3
"""保健品證據保鮮期契約（2026-07-29）。

守的是一件很安靜的事：**過期的健康建議不會報錯，它只會一直用篤定的語氣講下去。**
營養學的說法兩三年就翻盤一次；鎂那條引的是 2025 年的新試驗，明年可能就不是最新的了。
沒有人在看那個日期＝她會拿著三年前的文獻對長輩講「最近的研究說」。

原本該掛定時任務，但 7/16 定時任務已經全刪。所以掛在出貨閘門上——不需要任何人記得。
"""
import datetime
import json
import os
import tempfile
import unittest

import health_evidence_freshness as fresh

HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = datetime.date(2026, 7, 29)


def _pool(verified_at, risk="L3"):
    """寫一份只有一條保健品的假池子，日期可控。"""
    doc = {"topics": {"T": {"title": "測試", "solutions": [
        {"id": "s1", "label": "某保健品", "riskLevel": risk, "verifiedAt": verified_at,
         "say": "x", "maturity": "emerging", "timeToEffect": "慢養",
         "solutionType": "保健品", "effortCost": "低"}]}}}
    path = os.path.join(tempfile.mkdtemp(prefix="munea-fresh-"), "pool.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return path


class ThresholdTest(unittest.TestCase):
    def test_fresh_evidence_passes(self):
        expired, aging, undated = fresh.audit(TODAY, _pool("2026-07-01"))
        self.assertEqual((expired, aging, undated), ([], [], []))

    def test_one_year_old_warns_but_does_not_block(self):
        expired, aging, _ = fresh.audit(TODAY, _pool("2025-07-01"))
        self.assertEqual(expired, [])
        self.assertEqual(len(aging), 1)

    def test_eighteen_months_old_blocks(self):
        expired, _, _ = fresh.audit(TODAY, _pool("2024-12-01"))
        self.assertEqual(len(expired), 1)
        self.assertGreater(expired[0]["ageDays"], fresh.FAIL_DAYS)

    def test_missing_date_counts_as_never_checked(self):
        """沒寫日期不能當成「還新」——不知道多久沒查就是沒查過。"""
        _, _, undated = fresh.audit(TODAY, _pool(None))
        self.assertEqual(len(undated), 1)

    def test_garbage_date_is_not_silently_ignored(self):
        _, _, undated = fresh.audit(TODAY, _pool("去年"))
        self.assertEqual(len(undated), 1)

    def test_only_supplements_are_audited(self):
        """生活建議（少吃鹽、多走路）不會過期，別拿去吵。"""
        expired, aging, undated = fresh.audit(TODAY, _pool("2020-01-01", risk="L1"))
        self.assertEqual((expired, aging, undated), ([], [], []))


class LiveKnowledgeBaseTest(unittest.TestCase):
    """對真正的方案池跑——這條紅了就是真的有建議過期了。"""

    def test_every_supplement_in_the_real_pool_is_still_in_date(self):
        expired, _, undated = fresh.audit()
        self.assertEqual(undated, [], "有保健品沒寫查證日期")
        self.assertEqual(
            [r["solutionId"] for r in expired], [],
            "這些保健品建議超過一年半沒重查文獻——要重查、更新 evidence 與 verifiedAt，"
            "不是把門檻調鬆")

    def test_the_gate_actually_runs_this(self):
        """做了但沒接上出貨閘門＝白做（今天已經犯過三次）。"""
        with open(os.path.join(HERE, "..", "package.json"), encoding="utf-8") as f:
            pkg = json.load(f)
        self.assertIn("test_health_evidence_freshness.py", pkg["scripts"]["test:launch"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
