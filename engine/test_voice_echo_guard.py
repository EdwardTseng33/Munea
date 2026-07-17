# -*- coding: utf-8 -*-
"""回音濾網＋聲線統一 · 護欄測試（2026-07-16 · 聊聊事故夜病歷 a/d）

守的線：a. 她講話期間（＋殘響窗）低能量上行＝回音要丟、正常音量直說要放行、
她沒講話時一律放行＝不取捨。d. 台語攔截後先讓她自己重講（同聲線）、重講再被攔
才換安全配音。

跑法：python engine/test_voice_echo_guard.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))

from voice_echo_guard import frame_rms, in_output_window, should_drop_uplink_frame

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

    # 預設值鎖（7/16 首晚實戰調參：700/1500 攔不住大聲外放）
    for k in ("MUNEA_VOICE_ECHO_GUARD_RMS", "MUNEA_VOICE_ECHO_GUARD_TAIL_MS"):
        os.environ.pop(k, None)
    from voice_echo_guard import guard_rms_threshold, guard_tail_ms
    check("預設門檻=1150", guard_rms_threshold() == 1150)
    check("預設殘響窗=2500ms", guard_tail_ms() == 2500)

    # 防刪除契約：伺服器真的接了線（防有人改壞）
    root = os.path.dirname(os.path.abspath(__file__))
    srv = open(os.path.join(root, "live_voice_server.py"), encoding="utf-8").read()
    check("伺服器有掛回音濾網", "should_drop_uplink_frame" in srv and "node.echo_guard_dropped" in srv)
    check("模型主聲道記出聲時間", srv.count('st["last_out"] = time.monotonic()') >= 2)
    check("收線總帳含回音丟棄數", "echo_dropped=st" in srv)
    check("發音級攔截先讓她自己重講(同聲線)", 'source in ("model_output", "mandarin_pronunciation")' in srv)
    check("重講再被攔才換安全配音", "_send_safe_mandarin_tts(blocked_text, source)" in srv)

    # 契約：查詢備胎鏈＋安撫句＋配速（7/16 晚 gemini-2.5-flash 整批客滿事故後立）
    check("查詢有備胎鏈", "lookup_model_failover" in srv and "gemini-3.1-flash-lite" in srv)
    check("查太久先安撫一句", "lookup_wait_cue_sent" in srv and "LOOKUP_WAIT_TEXT" in srv)
    check("結果一到取消安撫句", "wait_cue_task.cancel()" in srv)
    check("過場音配速不灌爆", srv.count("await asyncio.sleep(0.08)") >= 3)
    check("查詢總預算 13 秒", 'MUNEA_LOOKUP_TIMEOUT_SECONDS", "13"' in srv)

    # 契約：重試斷路器（7/16 深夜「一直重複我幫你查一下」事故後立）
    check("連兩敗進冷卻", 'st["lookup_fail_streak"] >= 2' in srv and "lookup_block_until" in srv)
    check("冷卻期內不查不念", "node.lookup_suppressed" in srv)
    check("過場句30秒不重播", "node.lookup_cue_skipped" in srv)
    check("失敗時明令說查不到", srv.count("不要再呼叫查詢工具") >= 3)
    check("成功歸零斷路器", 'st["lookup_fail_streak"] = 0' in srv)

    # 契約：過場句同聲線（Phase 3 · 7/17 凌晨）
    check("有她本人聲線的配音通道", "_gemini_tts_pcm" in srv and "gemini-2.5-flash-preview-tts" in srv)
    check("配音失敗自動退回舊路", srv.count("server.tts_b64") >= 3)
    check("工具說明教她先講一句再查", "說完立刻呼叫本工具" in srv)
    check("聲線跟角色走", "_char_voice_name" in srv)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 回音濾網＋聲線統一護欄全過")


if __name__ == "__main__":
    main()
