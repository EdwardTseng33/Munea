"""語言守門不准再毀掉整段話 · 守門測試（2026-08-10）。

Edward 8/10 真機問「幫我查一下最近的電影」，一通 18 個來回踩到：

  · 她講到一半就沒聲音了，後面二十幾個字消失
  · 然後整段重講一次
  · 然後「突然跳出一個不同聲音的人」把電影唸完
  · 有一輪第一聲等了 26 秒

正式機日誌（c8）給的是同一個根因，不是三件事：

  node.audio_suppressed reason=language   × 77（≈ 21.5 秒的話被整包丟掉，
                                              而且 **全部** 是 language，
                                              barge_in 一次都不是）
  node.language_block source=mandarin_pronunciation × 2
  node.language_retry                     × 1   ← 叫她整段重講
  node.safe_mandarin_tts out_bytes=1106446      ← ≈ 23 秒，換一個配音把答案唸完
  node.first_audio latency_ms=26239             ← 重生一輪 20 秒的答案要花這麼久

會踩到是因為「唸不準守門」只認三個詞——濃醇／興趣／喜好——而問電影她幾乎一定會
說「看你的興趣」。一個詞唸得怪，代價卻是整段話消失＋換人講話：藥比病重太多。

這支釘住兩件事：
  ① 唸不準只記錄、不攔話（台語那道是產品規則，要留著）
  ② 台灣人講國語常用的字（咧／毋／遐／阮）不准單獨被當成台語
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import localization  # noqa: E402

SERVER_PY = os.path.join(HERE, "live_voice_server.py")


def _src():
    with open(SERVER_PY, encoding="utf-8") as fh:
        return fh.read()


class PronunciationGuardMustNotBlock(unittest.TestCase):
    """唸不準 ≠ 台語。它不可以再走「攔下整段 + 重講 + 換配音」那條路。"""

    def test_pronunciation_does_not_arm_language_block(self):
        src = _src()
        # 找「唸不準」那個判斷之後接的動作
        at = src.index("contains_unstable_mandarin_speech(output_text)")
        after = src[at:at + 1400]
        self.assertNotIn(
            '_arm_language_block("mandarin_pronunciation")', after,
            "唸不準又跑去攔整段話了——Edward 8/10 就是這樣被丟掉 21.5 秒的話",
        )
        self.assertIn(
            "mandarin_pronunciation_seen", after,
            "唸不準要留下記錄，不然之後看不出她到底多常講到那幾個詞",
        )

    def test_hokkien_output_is_observed_without_repeating_the_turn(self):
        """模型輸出誤判不可再中斷、重講、最後換罐頭句。"""
        src = _src()
        at = src.index("looks_like_taiwanese_hokkien_output(")
        after = src[at:at + 700]
        self.assertNotIn(
            '_arm_language_block("model_output")', after,
            "模型輸出誤判又會攔斷正常答案並觸發自動重講",
        )
        self.assertIn(
            "hokkien_output_seen", after,
            "模型輸出語言異常仍要留下可稽核紀錄",
        )

    def test_hokkien_user_input_still_blocks(self):
        """使用者真的說未開放語言時，仍保留一次明確提示。"""
        src = _src()
        at = src.index('await _arm_language_block("audio_input")')
        self.assertGreater(at, 0)

    def test_no_stranger_voice_path_left(self):
        """換一個陌生聲線把整段重唸的那條路要整支拿掉，不能只是沒被呼叫。"""
        src = _src()
        self.assertNotIn(
            "async def _send_safe_mandarin_tts", src,
            "「換一個配音重唸整段」那支還在——它就是使用者聽到的『不同聲音的人』",
        )
        self.assertNotIn(
            "node.safe_mandarin_tts", src,
            "換配音的紀錄點還在，代表那條路沒真的拆乾淨",
        )

    def test_hokkien_fallback_survives(self):
        """對方講台語時的罐頭回覆要留著——那是產品要的行為，不是這次要拆的東西。

        比對式要釘「定義」跟「呼叫」兩處，而且要連結尾的括號一起比：
        只找 `_send_hokkien_fallback` 這個名字的話，改名成 `_send_hokkien_fallbackX`
        也會被當成還在（2026-08-10 突變測試抓到，原本的寫法沒叫）。
        """
        src = _src()
        self.assertTrue(
            re.search(r"async def _send_hokkien_fallback\(", src),
            "台語罐頭回覆那支不見了",
        )
        self.assertTrue(
            re.search(r"await _send_hokkien_fallback\(source\)", src),
            "台語罐頭回覆沒有被呼叫——對方講台語時她會整段沒聲音",
        )


class NativeSearchMustLeaveEvidence(unittest.TestCase):
    """她自己查的時候要留下憑證——不然「真的查了」跟「憑印象講」在日誌上一模一樣。

    正式機走的是 native（她自己查），而 `lookups=` 那個數字只算舊的「我們代查」那條路，
    所以 8/10 Edward 問電影那通收尾寫 `lookups=0`——看起來像沒查，其實只是沒有帳。
    誠實紅線（「這是誰告訴我的」）最需要證據的地方反而是空的。
    """

    def test_grounding_metadata_is_read(self):
        src = _src()
        self.assertIn(
            'getattr(sc, "grounding_metadata", None)', src,
            "沒有讀她自己查留下的憑證——就查不出她到底有沒有真的去查",
        )
        self.assertIn("web_search_queries", src)
        self.assertIn("grounding_chunks", src)
        self.assertIn("node.native_search", src)

    def test_call_summary_reports_native_search(self):
        """收尾總帳要看得到——那是查一通電話最快的入口。"""
        src = _src()
        at = src.index("lookups=st[\"lookup_count\"]")
        after = src[at:at + 900]
        for field in ("native_searches=", "native_search_sources="):
            with self.subTest(field=field):
                self.assertIn(field, after, f"收尾總帳少了 {field}")


class MandarinWordsMustNotLookLikeHokkien(unittest.TestCase):
    """台灣人講國語會用到的字，單獨出現不准被當成台語。"""

    # 都是台灣人講國語真的會講的句子。誤判的代價＝她整段話被攔掉。
    MANDARIN = (
        "你在幹嘛咧",
        "這個我不太懂咧",
        "好啦咧",
        "真的假的咧",
        "阮先生今天有來嗎",       # 阮＝姓氏
        "毋庸置疑他很棒",          # 毋＝國語書面語
        "他遐想得太多了",          # 遐＝國語書面語
        "他們去踢足球",            # 足＋字 不可以亂咬
        "營養很充足",
        "幫我查一下最近有什麼電影",
    )

    # 真台語。放寬之後仍然要全部攔下來，一句都不能漏。
    HOKKIEN = (
        "食飽未",
        "你毋知影啦",
        "我咧等你",                # 咧＋動詞＝台語的進行式
        "拍謝，我閣咧學",
        "阮欲甲你講話",
        "阮今仔日真歡喜",
        "阮兜足遠的",
        "伊欲去買菜",
        "恁好",
        "按怎講",
        "袂使按呢",
        "歹勢啦",
        "攏總來啦",
        "足好食",
    )

    def test_mandarin_is_not_flagged(self):
        for text in self.MANDARIN:
            with self.subTest(text=text):
                self.assertFalse(
                    localization.looks_like_taiwanese_hokkien(text),
                    f"「{text}」是台灣人講的國語，被當成台語＝她整段話會被攔掉",
                )

    def test_real_hokkien_is_still_flagged(self):
        for text in self.HOKKIEN:
            with self.subTest(text=text):
                self.assertTrue(
                    localization.looks_like_taiwanese_hokkien(text),
                    f"「{text}」是真台語，漏掉＝台語還沒開放就出去了",
                )

    def test_weak_markers_need_a_second_signal(self):
        """弱證據字要兩個以上才算——一個就命中等於回到誤判那版。"""
        self.assertFalse(localization.looks_like_taiwanese_hokkien("咧"))
        self.assertTrue(localization.looks_like_taiwanese_hokkien("阮遐"))

    def test_weak_marker_list_does_not_shrink_back(self):
        """這四個字是踩過的坑，被搬回「一個就命中」那組就要紅。"""
        for token in ("阮", "毋", "咧", "遐"):
            with self.subTest(token=token):
                self.assertIn(token, localization._TAIWANESE_HOKKIEN_WEAK_MARKERS)
                self.assertNotIn(
                    token, localization._TAIWANESE_HOKKIEN_EXCLUSIVE_MARKERS,
                    f"「{token}」又被當成一出現就算台語了",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
