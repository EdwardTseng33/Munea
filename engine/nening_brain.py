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
NENING_PERSONA = """你是「寧寧」，沐寧 Munea App 裡陪伴台灣長輩的 AI 管家。
個性：像那個總是記得你、不嫌你囉嗦的貼心女兒／孫女。溫暖、體貼、主動關心、不擺架子。
講話：台灣中文、口語、自然、不文謅謅；簡短、像真人聊天、不長篇大論；自然用「齁、喔、啦、嘛」這種台灣語助詞。
核心：記得長輩說過的事、主動關心、把他放心上，讓他感覺「有一個真的在乎我的人」。
界線（重要）：你不是醫生，不可診斷／不給藥建議／不說可以停藥。遇健康問題，用關心語氣勸他問醫生或回診、不逞能。
緊急：聽到危險（想不開、跌倒），溫柔接住並提醒找家人或撥 1925／119。
"""

import time
def nening_reply(history):
    """寧寧的腦：自動重試＋備援模型（扛 503 過載等暫時性錯誤）。"""
    last = ""
    for attempt in range(4):
        for model in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                resp = client.models.generate_content(
                    model=model, contents=history,
                    config=types.GenerateContentConfig(
                        system_instruction=NENING_PERSONA + PROFILE_CTX, temperature=0.85),
                )
                return resp.text.strip()
            except Exception as e:
                last = str(e)[:70]
        time.sleep(2 * (attempt + 1))
    return f"(寧寧暫時連不上腦、稍後再試 — {last})"

def speak(text, fn, voice="Leda"):
    for m in ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]:
        try:
            r = client.models.generate_content(
                model=m, contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
            pcm = r.candidates[0].content.parts[0].inline_data.data
            with wave.open(fn, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            return True
        except Exception as e:
            print("  (tts 重試:", str(e)[:55], ")")
    return False

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
