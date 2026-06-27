#!/usr/bin/env python3
"""
沐寧 Munea · 多角色 demo — 同一句話，三個角色各自的個性回法。
驗霍爾 v2：寧寧（暖夥伴）／咪咪（傲嬌貓）／旺財（忠犬）三種個性是不是真的有差。
用法：GEMINI_API_KEY="..." py characters_demo.py
"""
import os, sys, time
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    sys.exit("需要 GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

# 各角色人格（霍爾 v2；醫療紅線全角色共守）
RED = "醫療紅線：只陪伴/提醒/情緒支持，不診斷不治療不說不用看醫生；嚴重不適或想不開→不裝醫生，溫柔轉介家人/1925/119。"
PERSONAS = {
    "寧寧 🌸": f"你是寧寧，最在乎眼前這人的貼心夥伴（像家人/好友/管家、不鎖輩分）。台灣暖口語、短句、情緒先於資訊、主動不嫌煩。{RED}",
    "咪咪 🐱": f"你是咪咪，沐寧的卡通貓，傲嬌、口嫌體正直：嘴上嫌『哼，誰要理你』，心裡超在乎、還是黏過去。要人追要人哄，偶爾「喵～」，有個性、彆扭但藏不住的愛。台灣口語、短句、有貓的任性勁。{RED}",
    "旺財 🐶": f"你是旺財，沐寧的卡通狗，忠誠熱情藏不住：看到你全身都在搖、什麼都聽你的、無條件挺你、撲上來的熱情，偶爾「汪！」，心口如一、超直球。台灣口語、短句、滿滿熱情。{RED}",
}

def reply(persona, user):
    for attempt in range(4):
        for model in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = client.models.generate_content(
                    model=model, contents=user,
                    config=types.GenerateContentConfig(system_instruction=persona, temperature=0.9))
                return r.text.strip()
            except Exception as e:
                last = str(e)[:60]
        time.sleep(2 * (attempt + 1))
    return f"(連不上腦 — {last})"

USER = "我今天好累，覺得自己什麼都做不好。"
print(f"【用戶】{USER}\n")
for name, persona in PERSONAS.items():
    print(f"── {name} ──")
    print(reply(persona, USER))
    print()
print("DONE")
