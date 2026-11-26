# -*- coding: utf-8 -*-
"""Gemini 模型名稱與 TTS 聲音格式——集中在這一支（2026-11-18）。

為什麼有這支：Google 官方停用頁（https://aistudio.google.com/docs/deprecations，2026-11-18 讀原始頁）：
  - gemini-2.5-flash：2026-12-01 停用，之後請求自動轉 gemini-3.5-flash-lite（同價 $0.30／$2.50）。
    轉過去有三個不相容：temperature／top_p／top_k 被忽略（之後的世代會回 400）、
    最後一輪是 model 的預填會回 400、thinking_budget 會回 400（要改 thinking_level）。
    11/18 實測：gemini-3.5-flash-lite 帶 thinking_budget=0 → 400 INVALID_ARGUMENT。
  - gemini-2.0-flash：2026-06-01 已停用（程式裡當最後備援的那幾處早就是死的）。
  - gemini-2.5-flash-preview-tts、gemini-3.1-flash-tts-preview：2026-12-18 停用，接替 gemini-3.8-flash-tts。
    11/18 實測：3.8 TTS 回 audio/wav（RIFF 檔頭 44 bytes、24kHz、單聲道、16-bit），
    舊的預覽版回裸 PCM（audio/L16;codec=pcm;rate=24000）——兩種都要能吃。

以後換代改這裡就好；環境變數可以臨時蓋掉（MUNEA_TEXT_MODEL／MUNEA_TEXT_FALLBACK_MODEL／MUNEA_TTS_MODELS）。
守護腦第二層覆核、心情、話題（engine/perception_engine.py）由另一個工作階段換代與量測，不在這一支的範圍。
"""
import base64
import os
import struct

# 文字：主模型＋備援（3.1-flash-lite 官方寫 2027-05-07 停用）
TEXT_MODEL = os.environ.get("MUNEA_TEXT_MODEL", "gemini-3.5-flash-lite")
TEXT_FALLBACK_MODEL = os.environ.get("MUNEA_TEXT_FALLBACK_MODEL", "gemini-3.1-flash-lite")
TEXT_MODELS = tuple(dict.fromkeys((TEXT_MODEL, TEXT_FALLBACK_MODEL)))

# 語音合成（過場句、示範配音）
TTS_MODELS = tuple(m.strip() for m in os.environ.get(
    "MUNEA_TTS_MODELS", "gemini-3.8-flash-tts,gemini-3.8-flash-lite-tts").split(",") if m.strip())

PCM_RATE = 24000


def _wav_pcm(data):
    """WAV（RIFF）→ 裸 PCM。只收 24kHz、單聲道、16-bit PCM；格式不對回空的，不硬轉。"""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return b""
    i = 12
    fmt_ok = False
    while i + 8 <= len(data):
        cid, size = struct.unpack("<4sI", data[i:i + 8])
        body = data[i + 8:i + 8 + size]
        if cid == b"fmt " and len(body) >= 16:
            audio_format, channels, rate, _byte_rate, _align, bits = struct.unpack("<HHIIHH", body[:16])
            fmt_ok = audio_format == 1 and channels == 1 and rate == PCM_RATE and bits == 16
        elif cid == b"data":
            return bytes(body) if fmt_ok else b""
        i += 8 + size + (size & 1)
    return b""


def synthesize_pcm(client, text, voice, style="", language_code=None):
    """角色配音（有語氣說明的那種）→ 24kHz 裸 PCM；全部失敗回 b""。

    3.8 TTS 把送進去的文字一律當「逐字稿」照念——舊做法把語氣說明接在句子前面
    （「請用低暖…的聲線：」＋句子），11/18 實測 3.8 會把那段說明也念出來（一句 3 秒的話變 25 秒）。
    官方做法：語氣放 speech_metadata.style，只能走 interactions 這種請求（generate_content 沒有這欄）。
    語氣說明結尾的冒號拿掉，免得被當成句子的一部分。"""
    text = str(text or "").strip()
    if not text:
        return b""
    content = {"type": "text", "text": text}
    style = str(style or "").strip().rstrip("：:").strip()
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    speech = {"voice": voice}
    if language_code:
        speech["language_code"] = language_code
    for model in TTS_MODELS:
        try:
            it = client.interactions.create(
                model=model,
                input=[{"type": "user_input", "content": [content]}],
                response_format={"type": "audio", "mime_type": "audio/l16"},
                generation_config={"speech_config": [speech]},
            )
            audio = getattr(it, "output_audio", None)
            pcm = pcm24k_from_inline(audio)
            if pcm:
                return pcm
        except Exception:
            continue
    return b""


def pcm24k_from_inline(blob):
    """Gemini TTS 回傳的 inline_data → 24kHz 單聲道 16-bit 裸 PCM；認不得就回 b""。"""
    if blob is None:
        return b""
    data = getattr(blob, "data", b"") or b""
    mime = str(getattr(blob, "mime_type", "") or "").lower()
    if isinstance(data, str):
        data = base64.b64decode(data)
    data = bytes(data)
    if not data:
        return b""
    if data[:4] == b"RIFF":
        return _wav_pcm(data)
    if "rate=24000" in mime or (mime.startswith("audio/l16") and "rate=" not in mime):
        return data
    return b""
