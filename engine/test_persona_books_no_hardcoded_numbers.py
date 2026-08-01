"""四本人設書都不准寫死急難號碼（2026-08-01 守門）。

Edward 2026-07-31 已立憲法級規矩：「她不准憑空講急難號碼——號碼唯一來源＝核定的
當地指引，書裡不准寫死。」但四本書當時都還留著自己那一國的號碼（中 119／英 911／
日 119、110／西 112、024）。書是照**語言**分的、號碼是照**國家**走的——講西班牙文
的人可能在墨西哥（911 不是 112），講英文的可能在英國（999）。書裡寫死＝語言對了
國家錯了就給錯號碼，只能靠另一段長警告去抵銷。

正解是把號碼整個拿出書本，改成每通從 localization 的「核定的當地指引」拿。
這支測試守兩件事：①書裡真的一個號碼都沒有 ②每個安全區的指引真的有號碼可拿。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import localization  # noqa: E402

# 各國急難／求助號碼；書裡出現任何一個都算違規。
_NUMBERS = re.compile(r"(?<!\d)(119|911|112|999|110|024|988|1925|7119|0120-279-338)(?!\d)")
_LOCALES = ("zh-TW", "en", "ja", "es")


def test_no_persona_book_hardcodes_an_emergency_number():
    for locale in _LOCALES:
        path = os.path.join(HERE, "persona", f"core.{locale}.txt")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        found = sorted(set(_NUMBERS.findall(text)))
        assert not found, f"core.{locale}.txt 又寫死了號碼：{found}（號碼只能放核定的當地指引）"


def test_every_safety_region_still_supplies_a_number():
    """書裡拿掉之後，指引那邊一定要接得住——否則變成她誰都不知道要打幾號。"""
    for region, guidance in localization._REGIONAL_EMERGENCY_GUIDANCE.items():
        for locale in _LOCALES:
            line = guidance.get(locale, "")
            assert line, f"{region} 缺 {locale} 的當地指引"
            assert _NUMBERS.search(line), f"{region}／{locale} 的指引裡沒有任何號碼可以唸"


def test_the_books_tell_her_to_read_the_number_out_loud():
    """只說「打當地的急救電話」不夠——慌的時候要的是可以直接按的數字。"""
    for locale in _LOCALES:
        path = os.path.join(HERE, "persona", f"core.{locale}.txt")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        marker = {
            "zh-TW": "一定要把號碼唸出來",
            "en": "say the number out loud",
            "ja": "番号を必ず声に出して",
            "es": "diga el número en voz alta",
        }[locale]
        assert marker in text, f"core.{locale}.txt 少了「要把號碼唸出來」這條"


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  PASS {name}")
    print(f"人設書不寫死號碼守門 {passed} 項全過")
