# -*- coding: utf-8 -*-
"""套件版本釘選守門（2026-11-12 事故後新增）。

事故：engine/requirements.txt 原本寫 google-genai>=2.10。11/8 重建正式語音機時自動裝到
11/6 剛出的 3.0 大改版，一連 Gemini Live 就被拒（HTTP 404）——正式聊聊整條打不通四天。
這支測試鎖住一件事：google-genai 必須「==」釘死某一版，不可以再用 >= 這種會自己長大的寫法。

跑法：python engine/test_requirements_pins.py（不需網路）
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _requirement_lines():
    with open(os.path.join(HERE, "requirements.txt"), encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


class RequirementsPinTests(unittest.TestCase):
    def test_google_genai_is_pinned_to_one_exact_version(self):
        lines = [ln for ln in _requirement_lines() if re.match(r"google-genai\b", ln)]
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], r"^google-genai==\d+\.\d+\.\d+$",
                         "google-genai 要用 == 釘死版本，不可以用 >=（會在重建時自動升到沒驗過的版本）")

    def test_google_genai_is_not_the_broken_major(self):
        line = next(ln for ln in _requirement_lines() if ln.startswith("google-genai"))
        major = int(line.split("==")[1].split(".")[0])
        self.assertLess(major, 3, "3.x 在 2026-11-12 實測連 Gemini Live 會被拒（HTTP 404）；要升先實測真連線")


if __name__ == "__main__":
    unittest.main(verbosity=2)
