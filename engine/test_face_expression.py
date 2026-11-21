"""表情訊號守門（2026-11-21 草稿）：開關預設關、每輪最多一次、關心優先於微笑、三語關鍵字。"""

from pathlib import Path

import pytest

import face_expression as fe


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("MUNEA_FACE_EXPRESSIONS", "1")


def test_default_off_sends_nothing(monkeypatch):
    monkeypatch.delenv("MUNEA_FACE_EXPRESSIONS", raising=False)
    st = {}
    assert fe.enabled() is False
    assert fe.next_event(st, "阿姨早安，昨天睡得好嗎？", True) is None
    assert "face_expr_sent" not in st


@pytest.mark.parametrize("text,expr", [
    ("阿姨早安，昨天晚上有睡好嗎？", "smile"),
    ("你上次說膝蓋會痠，今天有好一點嗎？", "concern"),
    ("聽起來你最近睡不著，一定很辛苦。", "concern"),
    ("嗯嗯，我在聽，你慢慢說。", "listen"),
    ("Good morning! Did you sleep well?", "smile"),
    ("I'm sorry your knee hurts.", "concern"),
    ("おはようございます。", "smile"),
    ("膝が痛いんですね、心配です。", "concern"),
    ("十點要吃血壓的藥。", None),
])
def test_classify(text, expr):
    assert fe.classify(text) == expr


def test_concern_wins_over_smile():
    # 同一句裡有打招呼也有不舒服：寧可關心，不要笑
    assert fe.classify("早安，聽說你頭痛？") == "concern"


def test_once_per_turn(on):
    st = {}
    assert fe.next_event(st, "早安", True) == {"type": "face_expression", "expr": "smile"}
    # 同一輪後面又出現關心字：不再送第二次
    assert fe.next_event(st, "早安，你膝蓋還痛嗎", False) is None
    # 下一輪重新算
    assert fe.next_event(st, "膝蓋還痛嗎", True) == {"type": "face_expression", "expr": "concern"}


def test_neutral_after_enough_text_without_keywords(on):
    st = {}
    short = "對了，十點要吃藥"
    assert fe.next_event(st, short, True) is None          # 還太短，先不判
    longer = short + "，我會在時間到的時候再提醒你一次喔"
    assert len(longer) >= fe.NEUTRAL_AFTER_CHARS
    assert fe.next_event(st, longer, False) == {"type": "face_expression", "expr": "neutral"}
    assert fe.next_event(st, longer + "，好不好", False) is None


def test_only_known_expressions():
    for text in ("早安", "好痛", "我在聽"):
        assert fe.classify(text) in fe.EXPRESSIONS


def test_voice_server_sends_through_gate():
    """語音主機只能透過 next_event 送表情（開關與每輪一次都在那裡把關），而且接在她的字幕後面。"""
    src = (Path(__file__).resolve().parent / "live_voice_server.py").read_text(encoding="utf-8")
    assert "import face_expression" in src
    assert src.count('"face_expression"') == 0, "不要在語音主機裡自己拼表情事件，一律走 face_expression.next_event"
    i_caption = src.index('{"type": "caption", "who": "nening", "text": caption_text}')
    i_face = src.index("face_expression.next_event(")
    assert 0 < i_face - i_caption < 1200
