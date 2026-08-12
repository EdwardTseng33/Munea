#!/usr/bin/env python3
"""「接通＝證明過才算」的守門（2026-08-12 · Edward：「為什麼不等真的接通才顯示接通」）。

保證三件事，缺一件使用者就會再次看到「顯示接通、其實聾著」（8/10 有兩通
整通麥克風 0 位元組卻照樣顯示接通）：
  ① 伺服器收到第一格麥克風封包時，回一句 uplink_ok 給 App（只回一次）
  ② App 收到 uplink_ok 才記 uplink_confirmed、才讓叮聲與「接通了」亮
  ③ App 有 2.5 秒的保底（舊伺服器沒有這個回報，不能讓畫面卡死），但保底
     走的是 warn 帳（connected_ux_shown basis=timeout）——帳上看得出哪通心虛
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def check(name, ok):
    print(("  OK  " if ok else " FAIL ") + name)
    return ok


def main():
    server = read("engine/live_voice_server.py")
    app = read("web/src/app.js")
    results = []

    # ① 伺服器：uplink_ok 必須發在「第一格麥克風封包」那個分支裡、整份程式只有一處
    first_mic_block = re.search(
        r'if not st\["first_mic"\]:\n(?:.*\n){0,14}?\s*await ws\.send\(json\.dumps\(\{"type": "uplink_ok"\}\)\)',
        server,
    )
    results.append(check("伺服器在第一格麥克風封包時回 uplink_ok", bool(first_mic_block)))
    results.append(check("uplink_ok 整份伺服器只發一處（不會每格都發）",
                         server.count('{"type": "uplink_ok"}') == 1))

    # ② App：有 uplink_ok 的接收處、會記 uplink_confirmed
    results.append(check("App 接得住 uplink_ok", "o.type === 'uplink_ok'" in app))
    results.append(check("App 收到就記 uplink_confirmed 帳",
                         "voiceCallMark('uplink_confirmed', 'pass')" in app))
    results.append(check("每通重新證明（_uplinkOk 每通歸零）",
                         "this._uplinkOk = false" in app))

    # ③ App：叮聲只住在「證明過才亮」的關卡裡；關卡有 2.5 秒保底、保底走 warn 帳
    results.append(check("叮聲只有一個出口（在確認關卡裡）",
                         app.count("CallChime.play()") == 1))
    gate = re.search(r"const _confirmConnectedUx = [\s\S]{0,900}?CallChime\.play\(\)", app)
    results.append(check("叮聲被 _confirmConnectedUx 關卡包住", bool(gate)))
    results.append(check("有 2.5 秒保底（舊伺服器不卡死）",
                         bool(re.search(r"_confirmConnectedUx\('timeout'\), 2500\)", app))))
    results.append(check("保底走 warn 帳（哪通心虛帳上看得到）",
                         "basis === 'uplink_ok' ? 'pass' : 'warn'" in app))
    results.append(check("等到 uplink_ok 才走 pass 路",
                         "LiveVoice.onUplinkOk = () => _confirmConnectedUx('uplink_ok')" in app))

    failed = results.count(False)
    if failed:
        print(f"\n❌ {failed} 項未過")
        return 1
    print("\n接通＝證明過才算：守門全過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
