# -*- coding: utf-8 -*-
"""回音濾網＋聲線統一 · 護欄測試（2026-07-16 · 聊聊事故夜病歷 a/d）

守的線：a. 她講話期間（＋殘響窗）低能量上行＝回音要丟、正常音量直說要放行、
她沒講話時一律放行＝不取捨。d. 片語級台語輸出攔截後只允許一次同聲線重講；
單一國語發音不穩只記證據，不再換陌生安全配音重播整段。

跑法：python engine/test_voice_echo_guard.py
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))

from voice_echo_guard import (frame_rms, in_output_window, should_drop_uplink_frame,
                              sustained_voice_evidence, speaker_threshold,
                              decide_speaker_evidence)

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def pcm(amplitude, n=320):
    return struct.pack("<" + "h" * n, *([amplitude] * n))


def main():
    # 音量尺規：安靜/小聲遠低於 700、正常直說遠高於 700
    check("靜音音量=0", frame_rms(pcm(0)) == 0.0)
    check("小聲漏音低於門檻", frame_rms(pcm(300)) < 700)
    check("正常直說高於門檻", frame_rms(pcm(4000)) > 700)
    check("壞資料回 0 不炸", frame_rms(b"\x01") == 0.0)
    check("空資料回 0", frame_rms(b"") == 0.0)

    # 出聲窗判定
    check("她沒出過聲→不在窗內", in_output_window(10.0, None) is False)
    check("剛出聲→在窗內", in_output_window(10.0, 9.9, tail_ms=1500) is True)
    check("出聲後 1.4 秒→仍在殘響窗", in_output_window(10.0, 8.6, tail_ms=1500) is True)
    check("出聲後 2 秒→窗已關", in_output_window(10.0, 8.0, tail_ms=1500) is False)

    # 丟棄決策（核心取捨：不必大吼、也不自說自話）
    check("她講話中+低能量→丟(回音)", should_drop_uplink_frame(10.0, 9.9, 300, enabled=True, tail_ms=1500, threshold=700) is True)
    check("她講話中+正常音量→放行(插話)", should_drop_uplink_frame(10.0, 9.9, 4000, enabled=True, tail_ms=1500, threshold=700) is False)
    check("她沒講話+低能量→放行", should_drop_uplink_frame(10.0, 5.0, 300, enabled=True, tail_ms=1500, threshold=700) is False)
    check("濾網關閉→一律放行", should_drop_uplink_frame(10.0, 9.9, 0, enabled=False, tail_ms=1500, threshold=700) is False)

    # App 只送候選；Voice 的單一裁決器用自己的門檻判斷，完全不信 client threshold。
    verdict = decide_speaker_evidence(
        [(300, 42.7), (1802, 42.7), (1802, 42.7), (1802, 42.7), (1802, 42.7)],
        playout_active=False, after_duck=True, sustain_ms=150,
    )
    check("Voice 單一裁決器接受持續真人聲", verdict["accepted"] is True)
    check("插話證據保留真正起音位置",
          verdict["onset_index"] == 1 and verdict["evidence_ms"] >= 150)
    rejected = decide_speaker_evidence(
        [(1802, 42.7), (200, 42.7), (1802, 42.7), (200, 42.7)],
        playout_active=False, after_duck=True, sustain_ms=150,
    )["accepted"]
    check("零星回音尖峰不會被誤判成持續插話", rejected is False)
    check("瀏覽器門檻函式已從 Voice 裁決移除",
          "normalized_rms_to_pcm16" not in open(
              os.path.join(os.path.dirname(__file__), "voice_echo_guard.py"), encoding="utf-8"
          ).read())

    # 預設值鎖（7/16 首晚實戰調參：700/1500 攔不住大聲外放）
    # A destructive two-phase interruption must not reuse the browser's low
    # adaptive threshold while the assistant is still playing. Production's
    # regular uplink and interruption evidence now share one threshold policy.
    os.environ["MUNEA_VOICE_ECHO_GUARD_HOT_MULT"] = "1.7"
    pre_duck_threshold = speaker_threshold(playout_active=True)
    check("播放中只讀單一裁決器的熱門檻",
          pre_duck_threshold == 1150 * 1.7)
    false_echo, _, _ = sustained_voice_evidence(
        [(1802, 42.7)] * 4, pre_duck_threshold, 150,
    )
    check("sustained speaker echo cannot cancel the assistant", false_echo is False)
    real_barge, _, _ = sustained_voice_evidence(
        [(4000, 42.7)] * 4, pre_duck_threshold, 150,
    )
    check("near-field speech still interrupts through the hot gate", real_barge is True)

    # New clients submit a dedicated post-duck tail. Two fresh callbacks are
    # enough for the 80ms confirmation while the original pre-roll remains
    # available only for first-syllable replay.
    post_duck_threshold = speaker_threshold(playout_active=False, after_duck=True)
    post_duck_voice, post_duck_ms, _ = sustained_voice_evidence(
        [(1802, 42.7)] * 2,
        post_duck_threshold,
        80,
        minimum_ms=60,
    )
    check("post-duck continuing speech has its own bounded gate",
          post_duck_voice is True and post_duck_ms >= 80)
    os.environ.pop("MUNEA_VOICE_ECHO_GUARD_HOT_MULT", None)

    for k in ("MUNEA_VOICE_ECHO_GUARD_RMS", "MUNEA_VOICE_ECHO_GUARD_TAIL_MS"):
        os.environ.pop(k, None)
    from voice_echo_guard import guard_rms_threshold, guard_tail_ms
    check("預設門檻=1150", guard_rms_threshold() == 1150)
    check("預設殘響窗=2500ms", guard_tail_ms() == 2500)

    # 防刪除契約：伺服器真的接了線（防有人改壞）
    root = os.path.dirname(os.path.abspath(__file__))
    srv = open(os.path.join(root, "live_voice_server.py"), encoding="utf-8").read()
    check("伺服器有掛回音濾網", "should_drop_uplink_frame" in srv and "node.echo_guard_dropped" in srv)
    # 2026-07-29：原本寫死比對 `st["last_out"] = time.monotonic()` 出現幾次，但主聲道那處
    # 為了順便量抖動改成先取一次 now 再指派（功能完全一樣）。改成檢查「有幾個地方在更新
    # 出聲時間」這個行為本身，不綁特定寫法——回音濾網要靠它判斷她此刻在不在講話。
    forward_match = re.search(
        r"async def _forward_audio\(chunk\):(?P<body>.*?)(?=\n    async def )",
        srv,
        re.DOTALL,
    )
    forward_body = forward_match.group("body") if forward_match else ""
    check("唯一音訊出口記出聲時間",
          'st["last_out"] = ' in forward_body and srv.count("await _forward_audio(") >= 4)

    # 回音窗 v2（2026-07-29 · Edward 點名「自問自答」後抓到的結構性漏洞）：
    # Gemini 送資料比講話快——一句 10 秒的話伺服器 2 秒送完，舊窗（送出時間+2.5秒）
    # 在她才播到第 5 秒時就關了，句子後半的回音全放行＝她回答自己。
    # v2 鏡射 App 播放節奏推「手機大概播到哪」的水位，窗蓋到播完+殘響。
    check("唯一音訊出口每塊都推進播放水位",
          'st["playout_head"] = note_playout(' in forward_body)
    check("回音判定以播放水位為主", "in_playout_window(_eg_now" in srv)
    check("送出時間窗留著當後備", "or in_output_window(_eg_now" in srv)
    check("用戶插話→水位歸零（App 已清掉未播聲音，窗立刻收、不吃真人聲）",
          srv.count('st["playout_head"] = 0.0') >= 2)
    check("插話先收證據再提交", 'elif t == "barge_in_start":' in srv and
          'st["pending_barge_in"]' in srv and "sustained_voice_evidence(" in srv)
    check("插話裁決明確回 accepted/rejected", '"accepted": False' in srv and '"accepted": True' in srv)
    check("插話通過後補送被守門留住的開頭", '_pending_barge["frames"][max(0, _onset_index - 1):]' in srv)

    check("server stores playout state at evidence start",
          '"playout_active": in_playout_window' in srv)
    check("server judges a declared post-duck tail through the sole arbiter",
          'decide_speaker_evidence(' in srv and '_decision_levels = _levels[-_post_duck_frames:]' in srv)
    check("server ignores browser amplitude thresholds",
          'normalized_rms_to_pcm16(obj.get("threshold"))' not in srv)

    import voice_echo_guard as g
    head = 0.0
    for i in range(5):
        head = g.note_playout(head, 100.0 + i*0.4, 24000*2*2)   # 10 秒的話、2 秒送完
    check("水位推到接近播完時刻", 110.0 < head < 112.0)
    check("舊窗在句子後半已經失守（這就是自問自答的洞）", not g.in_output_window(105.0, 101.6))
    check("新窗在句子後半仍蓋著", g.in_playout_window(105.0, head))
    check("播完+殘響後窗會關（不永遠蓋）", not g.in_playout_window(114.0, head))
    check("歸零後窗立即關", not g.in_playout_window(105.0, 0.0))
    check("收線總帳含回音丟棄數", "echo_dropped=st" in srv)
    check("片語級台語輸出只讓她自己重講一次", 'source == "model_output" and st.get("language_retry_count", 0) < 1' in srv)
    check("單一國語發音不穩不再重播整段", "_send_safe_mandarin_tts(blocked_text, source)" not in srv)

    # 契約：查詢備胎鏈＋安撫句＋配速（7/16 晚 gemini-2.5-flash 整批客滿事故後立）
    check("查詢有備胎鏈", "lookup_model_failover" in srv and "gemini-3.1-flash-lite" in srv)
    check("查太久先安撫一句", "lookup_wait_cue_sent" in srv and "LOOKUP_WAIT_TEXT" in srv)
    check("結果一到取消安撫句", "wait_cue_task.cancel()" in srv)
    check("過場音配速不灌爆", "for offset in range(0, len(pcm), 4800):" in srv and
          "await asyncio.sleep(0.08)" in srv)
    check("查詢總預算 13 秒", 'MUNEA_LOOKUP_TIMEOUT_SECONDS", "13"' in srv)

    # 契約：重試斷路器（7/16 深夜「一直重複我幫你查一下」事故後立）
    check("連兩敗進冷卻", 'st["lookup_fail_streak"] >= 2' in srv and "lookup_block_until" in srv)
    check("冷卻期內不查不念", "node.lookup_suppressed" in srv)
    check("過場句30秒不重播", "node.lookup_cue_skipped" in srv)
    check("失敗時依當輪語系明令說查不到",
          srv.count("live_lookup.failure_instruction(") >= 3)
    check("成功歸零斷路器", 'st["lookup_fail_streak"] = 0' in srv)

    # 契約：過場句同聲線（Phase 3 · 7/17 凌晨）
    check("有她本人聲線的配音通道", "_gemini_tts_pcm" in srv and "gemini-2.5-flash-preview-tts" in srv)
    check("配音失敗自動退回舊路", srv.count("server.tts_b64") >= 3)
    check("工具說明教她先講一句再查", "說完立刻呼叫本工具" in srv)
    check("聲線跟角色走", "_char_voice_name" in srv)
    check("過場音語言跟當輪回覆語系走",
          "localization.speech_language_code(locale)" in srv)
    check("過場音快取有語系隔離",
          "cache_key = (str(char or \"\"), normalized_locale, text)" in srv)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 回音濾網＋聲線統一護欄全過")


if __name__ == "__main__":
    main()
