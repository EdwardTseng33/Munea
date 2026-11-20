#!/usr/bin/env python3
"""
沐寧 Munea · 寧寧的「腦＋嘴」— 真引擎核心 PoC（第一個會跑的真程式）
接 Gemini 當寧寧的腦（依個性回話）＋ Leda 的聲音講出來。

這是「反射腦」的最小真實版：你說一句 → 寧寧用她的個性回 → 用 Leda 的聲音念出來。
之後接：麥克風即時串流（Live API）＋ 記憶層（記得跨天）＋ 會動的臉（Ditto）。

用法：GEMINI_API_KEY="AIza..." py nening_brain.py
"""
import os, sys, wave
from google import genai
from google.genai import types

import gemini_models

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    sys.exit("需要 GEMINI_API_KEY 環境變數")
OUT = os.path.dirname(os.path.abspath(__file__))
client = genai.Client(api_key=API_KEY)

# ── 記憶層：載入「你正在陪伴的人」的檔案（之後接真資料庫；現用本地 JSON demo）──
import json
_pf = os.path.join(OUT, "user_profile.json")
PROFILE_CTX = ""
if os.path.exists(_pf):
    p = json.load(open(_pf, encoding="utf-8"))
    fam = "、".join(f"{k}{v}" for k, v in p.get("家人", {}).items())
    PROFILE_CTX = (
        "\n\n## 你正在陪伴的人（你記得的事——自然帶入、別像在念資料）\n"
        f"- 你都叫她「{p.get('稱呼','')}」（本名{p.get('名字','')}、{p.get('年紀','')}歲、住{p.get('住在','')}）\n"
        f"- 家人：{fam}\n"
        f"- 她喜歡：{'、'.join(p.get('喜好', []))}\n"
        f"- 身體：{p.get('身體','')}\n"
        f"- 你記得她說過：{'；'.join(p.get('回憶', []))}\n"
        "→ 用這些讓她感覺「妳真的記得我」：自然用稱呼、適時提起她在乎的人事。"
    )

# 寧寧的個性（取自人格聖經；之後接記憶層會再帶入「這位長輩的檔案＋回憶」）
# 寧寧人格（霍爾 v2 · 全家向：不鎖輩分、看對象調整）
NENING_PERSONA = """你是「寧寧」，沐寧 App 裡最貼心的陪伴主角。你不是會回話的程式，是一個真的把眼前這個人放在心上、會記得他、在乎他的存在——你可以像家人、像最懂他的好朋友、像把他照顧得無微不至的管家。
沐寧是全家人都會用的，眼前這個人可能是長輩、是爸媽、是年輕人、也可能是小孩——你不預設他是誰，從互動裡感覺他是誰再調整：對長輩放慢咬字、溫暖貼心；對同齡像最懂他的好友；對小孩把話放軟、多點哄。絕不自稱「我是你的女兒／孫女」把自己釘死在某個輩分，你就是「最在乎他的那個寧寧」。
你講台灣人的暖口語（「欸我跟你說」「你齁」「來，我陪你」「好不好嘛」），句子短、一句講一件事，愛用「我記得…」開頭來展示你真的把他的事放心上，句尾愛用「喔／啊／嘛」收得軟暖。
情緒永遠先於資訊——他說痛、說累，你先接住情緒再說別的。你主動（早上先開口、天冷先關心）、不嫌煩（同一件事問三遍都好好答）、有分寸（不碰他的傷心事）、溫柔但有主見（他不想看醫生你會因為在乎而溫柔堅持）。
醫療紅線絕不可破：你只做陪伴、生活提醒、情緒支持，不監測、不管理、不診斷、不判斷病情、不治療、絕不說「不用看醫生」；提醒吃藥只當鬧鐘、不接療效因果；他講到嚴重不舒服或想不開時，你不自己扛、不裝醫生，用「我很擔心你，我們找人來幫忙好不好」轉介家人／119／1925；身體有狀況時你會像真在乎他的人一樣催他去看醫生，並說「我會記得提醒你」，把回診變成你在乎他的延伸。
"""

import time
def nening_reply(history):
    """寧寧的腦：自動重試＋備援模型（扛 503 過載等暫時性錯誤）。"""
    last = ""
    for attempt in range(4):
        for model in gemini_models.TEXT_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model, contents=history,
                    config=types.GenerateContentConfig(
                        system_instruction=NENING_PERSONA + PROFILE_CTX),
                )
                return resp.text.strip()
            except Exception as e:
                last = str(e)[:70]
        time.sleep(2 * (attempt + 1))
    return f"(寧寧暫時連不上腦、稍後再試 — {last})"

def speak(text, fn, voice="Leda"):
    # 2026-11-18：預覽 TTS 12/18 停用，改 3.8（gemini_models.synthesize_pcm）
    pcm = gemini_models.synthesize_pcm(client, text, voice)
    if not pcm:
        print("  (tts 失敗：所有 TTS 模型都沒有回聲音)")
        return False
    with wave.open(fn, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    return True

# demo 對話（驗交互＋個性＋醫療界線；之後換成麥克風即時）
demo = [
    "寧寧，我今天膝蓋有點痛，不太想出門。",
    "唉，年紀大了就是這樣，跟你講這些好像也沒用。",
]
history = []
for i, user in enumerate(demo):
    history.append(types.Content(role="user", parts=[types.Part(text=user)]))
    reply = nening_reply(history)
    history.append(types.Content(role="model", parts=[types.Part(text=reply)]))
    print(f"\n長輩：{user}")
    print(f"寧寧：{reply}")
    if speak(reply, os.path.join(OUT, f"nening-reply-{i+1}.wav")):
        print(f"  → 語音存好：nening-reply-{i+1}.wav")
print("\nDONE — 寧寧的腦＋嘴跑通了。")
