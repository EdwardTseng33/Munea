# -*- coding: utf-8 -*-
"""臉那條線永遠不准回頭卡住聲音（2026-07-29 · 穩定度優化）

背景：同一份聲音要送兩個地方——
  ① 手機（使用者在聽）＝**必須**
  ② 雲端臉（臉會動對嘴）＝**加分**

原本兩個都是直接 await，寫成：

    await ws.send(data)      # 給手機
    await fw.send(data)      # 給臉  ← 這行慢，下一塊聲音就要排隊

臉機是租來的 GPU、跨網路，慢是常態不是意外。它一慢，下一塊聲音就送不出去，
使用者聽到的就是「卡一下／吃掉一個字」——正是 Edward 7/28 回報的症狀之一。

程式碼原本的註解寫著「連不上/斷了都不能拖累語音對話：任何失敗都吞掉」——立意對，
但只擋了「斷掉」（例外），沒擋「變慢」（阻塞）。這支測試守住「慢也要擋」。

為什麼值得寫成測試：這個錯**看起來完全正常**（有 try/except、有註解說不拖累），
下次有人重構很容易又寫回直接 await。

佐證這條路徑真的是嫌疑犯：2026-07-29 實測 Gemini 送過來的節奏 697 個間隔、
最久 281 毫秒、零次超過手機端 600 毫秒的播放水庫——上游穩得很，卡只可能在下游。

跑法：python engine/test_voice_face_never_blocks_audio.py（純文字檢查、不需網路/鑰匙）
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, ok):
    print(("  OK  " if ok else "  FAIL") + "  " + label)
    if not ok:
        FAILS.append(label)


def main():
    with open(os.path.join(HERE, "live_voice_server.py"), encoding="utf-8") as f:
        srv = f.read()

    check("有『送臉最多等多久』這個上限", "FACE_SEND_TIMEOUT_S" in srv)
    check("上限可用環境變數調（現場出事能立刻轉）",
          "MUNEA_VOICE_FACE_SEND_TIMEOUT_S" in srv)
    check("上限遠小於手機端 600 毫秒的播放水庫",
          re.search(r'MUNEA_VOICE_FACE_SEND_TIMEOUT_S",\s*"0\.[01]\d*"', srv) is not None)

    # 核心契約：所有「送聲音給臉」都要包在逾時裡，一個都不能漏。
    sends = re.findall(r'fw\.send\((data|chunk)\)', srv)
    guarded = re.findall(r'asyncio\.wait_for\(fw\.send\((?:data|chunk)\),\s*timeout=FACE_SEND_TIMEOUT_S\)', srv)
    check(f"每一條送聲音給臉的路都有逾時保護（找到 {len(sends)} 條、保護 {len(guarded)} 條）",
          len(sends) > 0 and len(sends) == len(guarded))
    check("沒有任何一處是裸的 await fw.send(聲音)",
          re.search(r'await\s+fw\.send\((data|chunk)\)', srv) is None)

    check("逾時後把臉那條線放掉（不要每塊都再等一次）",
          srv.count("node.faceaudio_slow_dropped") >= 2)
    check("放掉之後在背景收線、不擋主流程",
          "asyncio.create_task(_face_audio_close(fw))" in srv)

    # 反向確認：給手機那條**不准**有逾時——那是必須送到的，逾時等於直接丟掉聲音。
    check("給手機那條沒有被順手加上逾時（那條是必須送到的）",
          re.search(r'wait_for\(ws\.send', srv) is None)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 臉慢就放掉臉，聲音永遠優先")


if __name__ == "__main__":
    main()
