"""Locale policy shared by Munea's API, model prompts, and speech synthesis."""

import re

SUPPORTED_LOCALES = ("zh-TW", "en", "ja", "es")
DEFAULT_LOCALE = "zh-TW"
_SPEECH_CODES = {"zh-TW": "cmn-TW", "en": "en-US", "ja": "ja-JP", "es": "es-ES"}
_REPLY_INSTRUCTIONS = {
    "zh-TW": "請一律使用自然的繁體台灣中文回覆，絕不使用簡體字。",
    "en": "Reply in warm, plain English. Keep voice responses short and easy to follow.",
    "ja": "自然でやさしい日本語で答えてください。音声で聞き取りやすい短い文を優先してください。",
    "es": "Responde en español claro y cálido. Para voz, usa frases cortas y fáciles de entender.",
}
_OPENING_MESSAGES = {
    "zh-TW": "嗨，我在的，想聊什麼都可以，先跟我說說今天過得怎麼樣？",
    "en": "Hi, I am here with you. How has your day been? We can talk about anything.",
    "ja": "こんにちは。ここにいますよ。今日はどんな一日でしたか？何でも話してくださいね。",
    "es": "Hola, estoy aquí contigo. ¿Cómo ha ido tu día? Podemos hablar de lo que quieras.",
}
_RETRY_MESSAGES = {
    "zh-TW": "不好意思，我這邊連線有點不順，等一下再陪你好不好？",
    "en": "I am having a little trouble connecting. Could we try again in a moment?",
    "ja": "少し接続が不安定です。少し待ってから、もう一度話しかけてもらえますか？",
    "es": "Estoy teniendo un pequeño problema de conexión. ¿Podemos intentarlo de nuevo en un momento?",
}

# Keep product copy canonical while giving speech synthesis an explicit,
# user-verified pronunciation. Add entries conservatively: an incorrect
# phonetic hint is worse than falling back to natural Taiwan Mandarin.
_TAIWANESE_SPEECH_FORMS = (
    ("卡早捆", "咖紮綑"),
)

def normalize_locale(locale):
    raw = str(locale or "").strip().replace("_", "-")
    if raw in SUPPORTED_LOCALES: return raw
    lowered = raw.lower()
    if lowered.startswith("zh"): return "zh-TW"
    if lowered.startswith("ja"): return "ja"
    if lowered.startswith("es"): return "es"
    if lowered.startswith("en"): return "en"
    return DEFAULT_LOCALE

def speech_language_code(locale): return _SPEECH_CODES[normalize_locale(locale)]

def opening_message(locale): return _OPENING_MESSAGES[normalize_locale(locale)]

def retry_message(locale): return _RETRY_MESSAGES[normalize_locale(locale)]

def reply_language_instruction(locale):
    """A narrow addition to the existing safety/persona prompt, never a replacement."""
    normalized = normalize_locale(locale)
    emergency = " Do not use Taiwan-specific hotline numbers or Taiwan-only service information; tell the person to contact their local emergency service or a trusted person nearby." if normalized != "zh-TW" else ""
    return "\n[Reply language]\n" + _REPLY_INSTRUCTIONS[normalized] + emergency

def speech_text(text, locale):
    """Return speech-only text without changing stored or displayed copy."""
    value = str(text or "")
    if normalize_locale(locale) != "zh-TW":
        return value
    for display, spoken in _TAIWANESE_SPEECH_FORMS:
        value = value.replace(display, spoken)
    return value

def display_text(text, locale):
    """Normalize speech transcriptions back to canonical product copy."""
    value = str(text or "")
    if normalize_locale(locale) != "zh-TW":
        return value
    for display, spoken in _TAIWANESE_SPEECH_FORMS:
        # Live transcription may insert spaces between CJK syllables. Limit
        # whitespace cleanup to verified terms instead of changing all copy.
        for form in (spoken, display):
            pattern = r"\s*".join(re.escape(char) for char in form)
            value = re.sub(pattern, display, value)
    return value

def taiwanese_pronunciation_instruction(locale):
    """Narrow speech policy for native-audio models such as Gemini Live."""
    if normalize_locale(locale) != "zh-TW":
        return ""
    examples = "；".join(f"「{display}」要唸成「{spoken}」" for display, spoken in _TAIWANESE_SPEECH_FORMS)
    return (
        "\n[台語發音]\n"
        "回覆可使用自然的台灣口語。遇到下列台語詞時，畫面文字仍保留原詞，但實際發音必須依照指定讀法："
        + examples
        + "。不要按國語逐字朗讀；若不確定其他台語詞的發音，就改用自然台灣華語表達，不要自行猜音。"
    )
