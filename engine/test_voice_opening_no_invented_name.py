"""不知道他叫什麼就不准編一個 · 守門測試（2026-08-08）。

Edward 真機（1.0.55）：她接起來第一句叫他「伯伯」——他從來沒在個人資料裡
填過名字、暱稱或任何稱呼。

查下來跟 8/1 編奧運新聞是**同一個病**，只是換了題目：

  開場指令**寫死**一句「用他的稱呼開頭」，但沒填名字時，說明書對稱呼
  **完全沉默**（舊程式只有 `if uv:` 那一支，沒有 else）。
  沉默不是中立——模型會用最像樣的猜測把空格填滿：照年紀猜「伯伯」、
  照性別猜「先生」。而「不知道就不要加稱呼」那條規則躺在一萬七千字的另一端，
  搶不過眼前這句直接指令。

修法沿用 7/29 誠實防線學到的那條：**只寫「不准編」沒用，要讓指令本身
不再要求她做不到的事，並且給一條不必編也照樣合格的路**。

這支測試守三件事（誰把它們改回去，這裡就會紅）：
  ① 不知道名字時，開場指令裡不准再出現「用他的稱呼開頭」
  ② 不知道名字時，要明確點名禁止那些憑年紀／性別猜的叫法
  ③ 知道名字時，行為完全不變（不能為了修這個把正常情況弄壞）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import localization  # noqa: E402
import live_voice_server  # noqa: E402


GUESSED_TITLES = ("伯伯", "阿姨", "阿公", "阿嬤", "先生", "小姐", "大哥", "大姐")


def test_no_name_never_asks_her_to_use_one():
    """沒填名字時，四條開場路線都不准再叫她「用他的稱呼開頭」。"""
    for idx in range(8):
        text = localization.voice_opening_instruction(familiarity=idx, has_name=False)
        assert "用他的稱呼開頭" not in text, (
            f"第 {idx} 條開場路線仍在要求稱呼，但我們根本不知道他叫什麼——"
            "她只能自己編一個（8/8 就是這樣叫出「伯伯」的）"
        )


def test_no_name_names_the_guesses_it_must_not_use():
    """光說「不要編」不夠——要點名那些她最可能猜的叫法。"""
    for idx in range(8):
        text = localization.voice_opening_instruction(familiarity=idx, has_name=False)
        assert "不知道他叫什麼" in text, f"第 {idx} 條沒有明講「不知道」"
        hit = [t for t in GUESSED_TITLES if t in text]
        assert len(hit) >= 4, (
            f"第 {idx} 條只點名了 {hit}——憑年紀／性別猜的叫法要具體列出來，"
            "抽象的「不要亂猜」擋不住模型填空"
        )


def test_no_name_still_gives_her_a_passing_option():
    """禁止之後一定要給替代做法，否則她還是會想辦法填空（7/29 誠實防線的教訓）。"""
    for idx in range(8):
        text = localization.voice_opening_instruction(familiarity=idx, has_name=False)
        assert "直接" in text or "招呼" in text, (
            f"第 {idx} 條沒有給「不加稱呼也照樣合格」的路"
        )


def test_known_name_behaviour_unchanged():
    """知道名字時完全照舊——修這個不能把正常情況弄壞。"""
    for idx in range(8):
        text = localization.voice_opening_instruction(familiarity=idx, has_name=True)
        assert "用他的稱呼開頭" in text, f"第 {idx} 條在知道名字時反而不叫她用稱呼了"
        assert "不知道他叫什麼" not in text


def test_default_keeps_old_behaviour():
    """沒傳 has_name 的呼叫端（例如文字聊天那條）行為不變。"""
    assert "用他的稱呼開頭" in localization.voice_opening_instruction(0)


def _instruction(user):
    return live_voice_server.system_instruction(user=user, locale_profile=None)


def test_manual_says_it_does_not_know_when_no_name():
    """說明書在「沒名字」時不能沉默——沉默會被模型當成填空題。"""
    text = _instruction(None)
    assert "你不知道他叫什麼" in text, (
        "沒填名字時說明書對稱呼完全沒交代——舊版就是這個空白讓她叫出「伯伯」"
    )
    hit = [t for t in GUESSED_TITLES if t in text]
    assert len(hit) >= 4, f"說明書沒點名那些憑空猜的叫法（只找到 {hit}）"


def test_manual_unchanged_when_name_known():
    """有填名字時，說明書照舊只給那一個正確稱呼。"""
    text = _instruction("爸爸")
    assert "唯一正確的稱呼是「爸爸」" in text
    assert "你不知道他叫什麼" not in text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("不准編稱呼 · 守門全過")
