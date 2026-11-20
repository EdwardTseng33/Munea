#!/usr/bin/env python3
"""
寧寧台灣中文語音樣本產生器 — Gemini 原生語音 voice 試聽
沐寧 Munea · V1 語音引擎選型耳朵測試

用法：
  1. 拿一把 Google AI Studio 免費金鑰： https://aistudio.google.com → Get API key
  2. 設環境變數後跑：
        Windows PowerShell:  $env:GEMINI_API_KEY="AIza..."; py generate_voice_sample.py
        Git Bash:            GEMINI_API_KEY="AIza..." py generate_voice_sample.py
  3. 產出 voice-samples/ 底下幾個 .wav，雙擊播放、用耳朵挑哪個女聲最像寧寧。

說明：
  - 用 TTS 模型先出「音色」樣本（最快、共用同一套 voice library）。
  - 全對話即時（延遲/插話/聽懂）的深測留 Sprint-1（用 native-audio dialog 即時通道）。
"""
import os
import sys
import wave

try:
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit("缺套件：先跑  pip install google-genai")

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    sys.exit("沒找到金鑰：請先設 GEMINI_API_KEY 環境變數（見檔頭用法）。")

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 寧寧開場白（暖、慢、台灣中文用語）
LINES = {
    "greeting": "陳奶奶，今天過得好嗎？想聊什麼都可以，我都在。",
    "care": "外面風有點涼，記得加件外套。等一下我陪你看看今天有什麼想做的事，好不好？",
}

# 適合「溫暖成年女性管家」的女聲候選（以實跑可用為準、跑壞就換名單）
FEMALE_VOICES = ["Kore", "Aoede", "Leda", "Callirrhoe", "Autonoe"]

# 模型：先試 3.8 TTS、失敗退 3.8 lite TTS（2026-11-18 換代）
TTS_MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]  # 預覽 TTS 2026-12-18 停用；3.8 回 WAV，寫檔前要剝檔頭

def _strip_wav(data):
    """3.8 TTS 回 WAV（含 44 bytes 檔頭）；舊預覽版回裸 PCM。統一成裸 PCM。"""
    if data[:4] == b'RIFF':
        import io
        with wave.open(io.BytesIO(data)) as w:
            return w.readframes(w.getnframes())
    return data


def save_wav(path, pcm_bytes, rate=24000, width=2, channels=1):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


def synth(client, model, text, voice):
    resp = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    return _strip_wav(resp.candidates[0].content.parts[0].inline_data.data)


def pick_model(client):
    """挑一個能跑的 TTS 模型（先 3.8 後 3.8 lite）。"""
    for m in TTS_MODELS:
        try:
            synth(client, m, "測試", FEMALE_VOICES[0])
            print(f"  使用模型：{m}")
            return m
        except Exception as e:
            print(f"  {m} 不可用（{type(e).__name__}），試下一個…")
    sys.exit("兩個 TTS 模型都跑不起來——把上面錯誤貼回給卡西法。")


def main():
    client = genai.Client(api_key=API_KEY)
    print("挑可用模型中…")
    model = pick_model(client)

    made = []
    for voice in FEMALE_VOICES[:3]:          # 先出 3 個女聲讓 Edward 比
        for key, text in LINES.items():
            fname = f"nening-{voice.lower()}-{key}.wav"
            path = os.path.join(OUT_DIR, fname)
            try:
                pcm = synth(client, model, text, voice)
                save_wav(path, pcm)
                made.append(fname)
                print(f"  ✓ {fname}")
            except Exception as e:
                print(f"  ✗ {voice}/{key} 失敗：{e}")

    print("\n完成。產出檔案：")
    for f in made:
        print("   " + os.path.join(OUT_DIR, f))
    print("\n雙擊播放、用耳朵挑哪個女聲最像寧寧。")


if __name__ == "__main__":
    main()
