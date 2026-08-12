# -*- coding: utf-8 -*-
"""量真實的「首字時間」——從我講完，到她第一個字的聲音出來。

為什麼要自己量：
  · 業界 2026/04 獨立評測說 Gemini Flash Live 首字 2.98 秒（同批 OpenAI 0.82 秒）
  · 我們程式註解卻寫 7/30 實測「第一聲 750ms」
  · 兩個差四倍，必有一個錯。而 8/1 才踩過「儀表量錯起點」的坑
    （反應時間從上一格麥克風封包起算，永遠報 7-38 毫秒）
所以這支不信任何既有儀表：自己計時、起點是「送完最後一格聲音」，
終點是「收到第一個位元組的她的聲音」。

實測結果（2026-08-09，台灣連線）：
  gemini-3.1-flash-live-preview（正式線現用）中位數 **538ms**（595／529／538）
  → 模型生成不是瓶頸。慢的是後面——尤其聲音繞去顯示卡算嘴型再回來那 1~2 秒。
  ⚠ 這個數字**不含語音辨識**（送文字觸發），所以不能拿來直接反駁業界那個 2,980ms。

⚠ 備用模型 `gemini-live-2.5-flash-native-audio` 在一般接口上不存在（實測三輪全回
  「找不到這個模型」）——它只在 Google 雲 Vertex 那條路才有。哪天切過去要記得換認證方式。

跑法：
  GEMINI_API_KEY=... python scripts/measure-voice-first-word.py [輪數]
"""
import asyncio
import os
import statistics
import sys
import time
import wave

from google import genai
from google.genai import types

MODEL_31 = "gemini-3.1-flash-live-preview"
MODEL_25 = "gemini-live-2.5-flash-native-audio"
SR = 16000            # 送進去的取樣率（跟正式線一致）
CHUNK_MS = 20


def silence_then_tone(seconds=1.2):
    """做一段「像人在講話」的聲音：不是真人語音，但有能量、有起訖，
    足以讓模型判定『他講完了』並開始回話。量的是回話有多快，不是聽懂什麼。"""
    import math
    n = int(SR * seconds)
    out = bytearray()
    for i in range(n):
        t = i / SR
        # 200Hz 基頻 + 諧波，音量做出起伏，收尾漸弱（像一句話）
        env = min(1.0, t * 6) * min(1.0, max(0.0, (seconds - t) * 4))
        v = 0.0
        for f, a in ((200, 0.5), (400, 0.3), (800, 0.15)):
            v += a * math.sin(2 * math.pi * f * t)
        s = int(max(-1.0, min(1.0, v * env)) * 20000)
        out += s.to_bytes(2, "little", signed=True)
    return bytes(out)


async def one_round(client, model, audio, label):
    cfg = {
        "response_modalities": ["AUDIO"],
        "system_instruction": "你是寧寧。用一句話簡短回應，不要問問題。",
    }
    async with client.aio.live.connect(model=model, config=cfg) as session:
        # 先讓連線穩定
        await asyncio.sleep(0.3)
        # 合成音調不會被判定成人聲（實測 15 秒不回話），改用文字送一句話並收尾。
        # 量到的是「她從收到我的話，到第一個字的聲音出來」——那是首字時間的主要成分。
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="你好，今天天氣如何？")]),
            turn_complete=True)
        sent_at = time.perf_counter()          # ← 起點：我講完的那一刻
        first_at = None
        total_bytes = 0
        try:
            async with asyncio.timeout(15):
                async for msg in session.receive():
                    sc = getattr(msg, "server_content", None)
                    if not sc:
                        continue
                    mt = getattr(sc, "model_turn", None)
                    if mt and mt.parts:
                        for p in mt.parts:
                            data = getattr(getattr(p, "inline_data", None), "data", None)
                            if data:
                                if first_at is None:
                                    first_at = time.perf_counter()   # ← 終點：第一個字的聲音
                                total_bytes += len(data)
                    if getattr(sc, "turn_complete", False):
                        break
        except (asyncio.TimeoutError, TimeoutError):
            pass
        if first_at is None:
            return None
        return round((first_at - sent_at) * 1000)


async def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("需要 GEMINI_API_KEY")
    client = genai.Client(api_key=key)
    audio = silence_then_tone()
    print("=== 量「我講完 → 她第一個字」（毫秒）===")
    print("    人類自然反應約 200ms；業界評測說 Gemini Flash Live 約 2980ms\n")
    for model, label in ((MODEL_31, "3.1 Flash Live（正式線現用）"),
                         (MODEL_25, "2.5 Flash 原生語音")):
        got = []
        for i in range(rounds):
            try:
                ms = await one_round(client, model, audio, label)
            except Exception as e:
                print("  %-30s 第 %d 輪失敗：%s" % (label, i + 1, str(e)[:90]))
                continue
            if ms is None:
                print("  %-30s 第 %d 輪：15 秒內沒回聲音" % (label, i + 1))
            else:
                got.append(ms)
                print("  %-30s 第 %d 輪：%s ms" % (label, i + 1, ms))
        if got:
            print("  → %s 中位數 **%d ms**（%d 輪）\n" % (label, statistics.median(got), len(got)))
        else:
            print("  → %s 沒量到\n" % label)


if __name__ == "__main__":
    asyncio.run(main())
