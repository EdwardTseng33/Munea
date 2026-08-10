# -*- coding: utf-8 -*-
"""收線還席位 ＋ 字幕不留上一通（2026-07-28 · Edward 1.0.44 真機驗測後立）

Edward 原話（7/28 聊聊體感驗測）：
  「目前撥通一次後，再回去撥通聊聊，字幕會顯示上一段對話的內容應該要修正」
  「二度撥通會有問題不是很容易撥通、而且撥通後感覺有bug又無法正常說話了」

兩個根因（讀原始碼確認、非推測）：

一、**正常掛斷不還席位**
   `handle()` 的收尾寫成「有 call_release_reason 才通知總機釋放」，但那個變數只在
   `except Exception` 那條路被設值——使用者正常講完掛斷（走 ConnectionClosed 或正常
   跑完）從頭到尾沒設過，於是**永遠不通知總機**。我們總共只有 2 席，第一通掛掉後那席
   還被總機認為佔用中，第二通自然撥不通、或搶到一個狀態不對的席位。

二、**字幕框只藏不清**
   `enterChat()` 對 `.face-caption-box` 做的是 `style.display='none'`，框裡上一通的
   最後一句原封不動留著；下次撥號那段又把它顯示回來——一接通就看到上一段對話。

這兩條都是「讀程式碼就看得出來」的契約，所以用原始碼契約檢查守住：改回舊寫法就會叫。

跑法：python engine/test_voice_teardown_and_captions.py（純文字檢查、不需網路/鑰匙）
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FAILS = []


def check(label, ok):
    print(("  OK  " if ok else "  FAIL") + "  " + label)
    if not ok:
        FAILS.append(label)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_hangup_always_releases_the_seat():
    srv = read("engine", "live_voice_server.py")

    check("收線原因有預設值（不是空字串）",
          re.search(r'call_release_reason\s*=\s*"call_ended"', srv) is not None)
    check("空字串預設已經不存在（那就是漏還席位的寫法）",
          re.search(r'call_release_reason\s*=\s*""', srv) is None)
    check("出錯那條路仍有自己的原因（看得出是哪種收線）",
          'call_release_reason = "voice_error"' in srv)
    check("收尾仍然會通知總機釋放", "/release" in srv and "voice-release-" in srv)
    check("準備期零收音重連不會誤釋放整通",
          "_defer_control_release_for_reconnect(call_release_reason, st)" in srv
          and 'node.control_release_deferred' in srv
          and 'preflight_zero_audio_reconnect' in srv)
    check("只有正常收線且雙向皆零才延後給 App／reaper 收席位",
          'reason == "call_ended"' in srv
          and 'get("in")' in srv
          and 'get("out")' in srv)
    check("鑰匙空位照樣歸還", srv.count("_release_client(_key_idx)") >= 2)

    # 真正要守的行為：不管走哪條路收線，都要有一個非空的原因 → finally 才會送 release。
    # 這裡把「所有指派」抓出來，確認沒有任何一條會把它變回空字串。
    assignments = re.findall(r'call_release_reason\s*=\s*(.+)', srv)
    check("沒有任何一條路會把收線原因清空",
          all(a.strip() not in ('""', "''") for a in assignments))


def test_captions_do_not_survive_into_the_next_call():
    app = read("web", "src", "app.js")

    check("進聊聊頁把字幕框整個拿掉（不是只藏起來）",
          re.search(r"enterChat[\s\S]{0,600}?face-caption-box[\s\S]{0,200}?box\.remove\(\)", app) is not None)
    check("進聊聊頁不再只切 display 就了事",
          re.search(r"enterChat[\s\S]{0,600}?box\.style\.display\s*=\s*'none'", app) is None)
    check("撥號時也從乾淨的字幕開始",
          app.count("if (box) box.remove();") >= 2)
    check("字幕開關關掉時本來就會移除（原有行為沒被我改掉）",
          "if (!captionsOn) { const box = document.querySelector('.face-caption-box'); if (box) box.remove(); }" in app)
    check("字幕仍然會被重建（不是把功能砍了）",
          "box.className = 'face-caption-box'" in app)


def test_native_search_skips_the_cue_warmup():
    """她自己查的時候，不該再為了「過場句」在接通瞬間燒 CPU 配 15 句音。

    Edward 7/28：「講話上前5分鐘都會卡卡」——接通那一刻把整個過場句庫丟進只有
    2 個工人的小隊列配音，在一顆 CPU 上跟送聲音的主線搶，一搶就是好幾分鐘。
    """
    srv = read("engine", "live_voice_server.py")
    check("暖機被關在舊路的條件裡",
          re.search(r"if live_lookup_enabled\(\):\s*\n\s*lookup_cue_future", srv) is not None)
    check("暖機不再無條件啟動",
          re.search(r"^\s{8}lookup_cue_future = asyncio", srv, re.M) is None)
    check("暖機程式本身留著（bridge 退回時還要用）", "_warm_lookup_cue_pool" in srv)


def main():
    test_hangup_always_releases_the_seat()
    test_captions_do_not_survive_into_the_next_call()
    test_native_search_skips_the_cue_warmup()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 收線還席位＋字幕不留上一通＋接通不燒暖機，全過")


if __name__ == "__main__":
    main()
