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
    start = src.find("if (o.type === 'ready') {")
    end = src.find("if (o.type === 'caption' && o.who === 'user'", start)
    assert start >= 0 and end > start, "找不到 ready 事件那段"
    body = src[start:end]
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


def test_her_voice_is_not_proof_your_microphone_works():
    """她出聲**不能**頂替「你的聲音送得出去」。

    2026-08-18 Edward「檢查聊聊是不是壞了」查出來的：8/13 之後每一通的收尾總帳都是
    in_bytes=0（你的麥克風一格都沒送到伺服器），她照樣自己講了 23 秒 × 3 輪。
    而這道本來該喊「你的聲音沒送出去」的看門，被寫成
        (this._micPackets > 0 || this._firstAudioRecorded)
    ——她每通都會出聲，所以這道保險絲永遠不會響，壞了五天沒人發現。

    她的聲音只證明「她那邊好」，不證明「你講得出去」。兩件事不可以互相頂替。
    """
    src = _src()
    watch = re.search(r"const lineAlive = phase === 'ready_timeout'(.{0,400}?);", src, re.S)
    body = watch.group(1)
    assert "_firstAudioRecorded" not in body, (
        "死線判斷又把「她有出聲」當成線活著——那正是 8/13～8/18 麥克風全死卻沒人發現的原因"
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


GUESS_FREE_DUCK = "誤判插話不准再把她的話砍掉（2026-08-09）"


def test_barge_in_candidate_does_not_touch_playback_before_server_verdict():
    """候選插話只能收證據；Voice 接受前不准壓音量或停聲。

    Edward 8/8 真機「整句話頻繁斷字、卡住一個字跳針」。舊行為＝一判定就硬停播放
    ＋清空臉那邊的緩衝；1.0.62 改成先壓低 24dB 後，擴音回音仍會反覆讓每句變小，
    使用者聽起來一樣是中斷。唯一安全邊界是 server accepted 前完全不改播放。
    """
    src = _src()
    maybe = re.search(r"\n  _maybeBargeIn\(.*?\n  \},", src, re.S)
    assert maybe, "找不到插話候選觀察窗"
    body = maybe.group(0)
    assert "_duckAssistantAudio()" not in body, (
        "Voice 裁決前仍會壓低播放——擴音回音會讓 AI 每句自我中斷"
    )
    assert "_stopAssistantPlayback()" not in body, "候選期不准自行停聲"
    assert "playbackChanged: false" in body, "候選事件必須明示播放未被改動"
    begin = re.search(r"\n  _beginBargeIn\(.*?\n  \},", src, re.S).group(0)
    assert "post_duck_frames: 0" in begin and "playback_unchanged: true" in begin, (
        "播放未 duck 卻仍宣稱 post-duck，Voice 會用過低門檻接受喇叭回音"
    )
    caller = re.search(r"this\.(_maybeBargeIn|_beginBargeIn)\(rms, observed\.threshold", src)
    assert caller and caller.group(1) == "_maybeBargeIn", (
        "偵測到插話仍直接砍話——要先走 _maybeBargeIn 收證據"
    )


def test_sameline_quality_heuristics_never_disable_lip_sync():
    """短停頓／慢起播只能記錄，不能把 Avatar 整通切成無對嘴模式。"""
    src = _src()
    queue = re.search(r"\n  _queueSameLineBoundaryFallback\(.*?\n  \},", src, re.S)
    assert queue, "找不到同線品質降級守門"
    body = queue.group(0)
    assert "_slFallbackAfterTurn =" not in body, (
        "品質 heuristic 仍在排程 voice-only fallback——查詢回覆會有聲無嘴"
    )
    assert "sameline_fallback_suppressed" in body


def test_false_alarm_is_recorded_without_playback_recovery():
    """候選放棄與伺服器拒絕都要留紀錄，但不應有音量復原需求。"""
    src = _src()
    assert "barge_in_candidate_abandoned" in src, "候選放棄沒有留下紀錄"
    assert "voice_barge_in_rejected" in src, "Voice 拒絕沒有回報，看不到誤判率"
    maybe = re.search(r"\n  _maybeBargeIn\(.*?\n  \},", src, re.S).group(0)
    assert "_unduckAssistantAudio()" not in maybe, (
        "候選放棄仍需恢復音量，代表候選期其實動過播放"
    )


def test_no_client_playback_duck_implementation_remains():
    """App 不只不能呼叫 duck，也不應保留可誤接回去的播放突變方法。"""
    src = _src()
    assert "_duckAssistantAudio()" not in src
    assert "_unduckAssistantAudio()" not in src
    assert "p.volume=0.06" not in src


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("使用者先說 · 守門全過")
