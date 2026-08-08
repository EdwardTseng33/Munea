"""使用者先說、麥克風不再等她 · 守門測試（2026-08-08）。

Edward 1.0.55 / 1.0.56 真機連報：
  · 「我無法講話」
  · 「有一通可以講，但撥通後就又都不能講了」（間歇性）
  · 「首句招呼像當機，話講不出來但嘴巴動了幾下」
  · 「不講話 10 秒它會自動掐斷通話」

查下來是同一條開場流程上的四個結：

  ① 麥克風本來掛在接通那條路的尾巴（markConnected 之後）才開，
     但那條路上有兩道「狀態變了就直接離開」的檢查——命中就整段跳過，
     麥克風永遠關著。同一份程式有時走到有時沒走到，所以是間歇性的。
  ② 她主動說的那句招呼要先繞去顯示卡算嘴型再回來，使用者只能盯著畫面等。
  ③ 上行一包都沒有 → 死線看門判定線死掉 → 重接，使用者感覺就是「被掐斷」。
  ④ 沉默 90 秒真的會自動收線。

Edward 8/8 拍板：**她放棄主動打招呼，改由使用者先說第一句她才回**；
沉默不再自動掛斷。這支測試釘住修法（誰改回去，這裡就會紅）。
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
APP_JS = os.path.join(os.path.dirname(HERE), "web", "src", "app.js")


def _src():
    with open(APP_JS, encoding="utf-8") as fh:
        return fh.read()


def test_mic_opens_on_ready_not_after_greeting():
    """麥克風要掛在 ready 事件（最早、沒有分支繞得過去），不是接通那條路的尾巴。"""
    src = _src()
    ready = re.search(r"if \(o\.type === 'ready'\) \{(.{0,1200}?)\n\s{12}\}", src, re.S)
    assert ready, "找不到 ready 事件那段"
    body = ready.group(1)
    assert "_setMicOpen(true)" in body, (
        "ready 事件沒有開麥——開麥若只掛在接通那條路的尾巴，"
        "路上兩道提早離開的檢查一命中就整段跳過（8/8 間歇性講不了話的根因）"
    )


def test_she_does_not_greet_unless_family_relay():
    """沒有家人傳話時，不准請她主動開口。"""
    src = _src()
    greet = re.search(r"\n  greet\(\) \{(.*?)\n  \},", src, re.S)
    assert greet, "找不到 greet()"
    body = greet.group(1)
    assert "if (!relay)" in body and "return" in body, (
        "greet() 沒有「沒有家人傳話就不開口」的出口——"
        "Edward 8/8 拍板改由使用者先說第一句"
    )
    assert "greeting_skipped" in body, "略過招呼時要留下紀錄，不然查不到為什麼她沒說話"


def test_family_relay_still_speaks_first():
    """例外要保住：家人託她轉達時仍由她先說，不然使用者不開口就永遠聽不到。"""
    src = _src()
    greet = re.search(r"\n  greet\(\) \{(.*?)\n  \},", src, re.S)
    body = greet.group(1)
    assert "type: 'greet'" in body and "relay" in body, (
        "家人傳話的路被一起拿掉了——那是唯一該讓她先開口的情況"
    )


def test_dead_line_no_longer_needs_her_voice():
    """她不主動說話之後，「她沒出聲」不能再當成線死掉的證據。"""
    src = _src()
    watch = re.search(r"const lineAlive = phase === 'ready_timeout'(.{0,400}?);", src, re.S)
    assert watch, "找不到死線看門的判斷"
    body = watch.group(1)
    assert "_micPackets" in body, (
        "死線判斷沒看上行——改成使用者先說之後，只有上行能證明線是活的"
    )


def test_silence_does_not_hang_up():
    """沉默不再自動收線（Edward 8/8：拿掉這個機制）。"""
    src = _src()
    # 三段沉默的最後一段，過去是 clearInterval + _autoEndCall
    tail = re.search(r"else \{ (_idleLast = Date\.now\(\);|clearInterval\(_idleMon\); _autoEndCall\(\);)", src)
    assert tail, "找不到沉默三段判斷的最後一段"
    assert "_autoEndCall" not in tail.group(1), (
        "沉默還是會自動掛斷——Edward 8/8 明確要求拿掉；"
        "改成使用者先說之後，安靜是常態，掛掉他等於當機"
    )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("使用者先說 · 守門全過")
