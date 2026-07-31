"""兩支通話儀表的守門測試（2026-08-01）。

背景：Edward 7/31 深夜回報「聊聊變得斷斷續續、反應也慢很多」，翻正式機紀錄卻查無實據——
因為當時三支表全在量別的東西：
  ①「反應多快」從「上一格麥克風封包」起算（每格都刷新、含全靜音）→ 永遠報 7-38 毫秒
  ②「聲音抖不抖」拿整通共用的時間點比 → 每輪第一塊都量到「他在想事情那段安靜」（報過 45 秒）
  ③ 手機端「斷續」把「臉機這輪還沒開口」也算成斷流（在 web/src/app.js，另一支表）

這支測試把①②的**起點**釘死。誰要是把起點改回去，這裡會紅。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from live_voice_server import note_turn_gap, reply_latency_ms  # noqa: E402


def test_reply_latency_starts_from_user_voice():
    """他 2 秒前講完最後一聲、0.02 秒前還在送靜音封包 → 要報 2000，不是 20。"""
    now = 100.0
    ms, basis = reply_latency_ms(now, last_voice_at=98.0, last_packet_at=99.98)
    assert basis == "user_voice", basis
    assert ms == 2000, ms


def test_reply_latency_falls_back_when_no_voice_yet():
    """開場招呼、純文字輸入這種沒聽過人聲的情況：退回封包時間，而且要標明。"""
    ms, basis = reply_latency_ms(100.0, last_voice_at=0.0, last_packet_at=99.5)
    assert basis == "last_packet", basis
    assert ms == 500, ms

    ms, basis = reply_latency_ms(100.0, last_voice_at=0.0, last_packet_at=None)
    assert ms is None and basis == "unknown", (ms, basis)


def test_turn_gap_ignores_the_silence_between_turns():
    """每輪第一塊沒有「上一塊」可比 → 不准算出空檔（舊版就是在這裡量到 45 秒）。"""
    new_max, gap = note_turn_gap(145.0, turn_last_out=None, current_max_ms=0.0)
    assert gap is None, gap
    assert new_max == 0.0, new_max


def test_turn_gap_measures_within_the_turn_and_keeps_the_worst():
    """同一輪內：0.3 秒空檔要抓到；後面順了也要保留最大值。"""
    new_max, gap = note_turn_gap(100.30, turn_last_out=100.0, current_max_ms=0.0)
    assert round(gap) == 300, gap
    assert round(new_max) == 300, new_max

    new_max, gap = note_turn_gap(100.32, turn_last_out=100.30, current_max_ms=new_max)
    assert round(gap) == 20, gap
    assert round(new_max) == 300, new_max


def test_app_side_stall_meter_waits_for_the_face_to_start():
    """手機端那支表（web/src/app.js）：臉機還沒開口的那段不准算成斷流。

    這裡守的是接線，不是句子——App 是 JavaScript、沒辦法在這支 Python 測試裡跑，
    所以確認三件事都在：開口旗標、臉機延遲事件、以及斷流只在開口後才起算。
    """
    app_js = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "src", "app.js")
    with open(app_js, encoding="utf-8") as fh:
        src = fh.read()
    assert "_slFaceStarted" in src, "臉機開口旗標不見了"
    assert "sameline_face_lead_ms" in src, "臉機這輪隔多久才開口，沒有在回報"
    guard = src.index("if (!this._slFaceStarted) {")
    stall = src.index("trackProductEvent('sameline_audio_stall'")
    assert guard < stall, "斷流計數必須排在『臉機已開口』的關卡後面"


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  PASS {name}")
    print(f"通話儀表守門測試 {passed} 項全過")
