"""Locale policy shared by Munea's API, model prompts, and speech synthesis."""

import re

from opencc import OpenCC

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
    "zh-TW": "嗨，我在這裡。想從哪件事聊起都可以。",
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

# Launch gate: `cmn-TW` is Taiwan Mandarin, not Taiwanese Hokkien. The current
# Live provider does not list Taiwanese Hokkien as a supported language, so a
# pronunciation example must never be mistaken for end-to-end language support.
# Raise this score only after a representative human-listening ASR/TTS benchmark
# reaches the product threshold below.
TAIWANESE_HOKKIEN_MIN_RELEASE_SCORE = 0.80
TAIWANESE_HOKKIEN_VALIDATED_SCORE = 0.0
TAIWANESE_HOKKIEN_FALLBACK = "我目前只用國語陪你聊，可以用國語再說一次嗎？"
TAIWANESE_HOKKIEN_OUTPUT_FALLBACK = "我改用國語再說一次。剛才那句沒有說清楚。"

_TAIWANESE_HOKKIEN_REQUEST_RE = re.compile(
    r"(?:用|說|講|改用|請用).{0,8}(?:台語|臺語|閩南語|河洛話|Hokkien)"
    r"|(?:台語|臺語|閩南語|河洛話|Hokkien).{0,10}(?:說|講|回答|介紹|聊天|對話)",
    re.IGNORECASE,
)
_TAIWANESE_HOKKIEN_STRONG_PHRASES = (
    "食飽未", "呷飽未", "拍謝", "歹勢", "按怎", "按呢", "啥物", "毋知",
    "毋通", "袂使", "無要緊", "無代誌", "有影", "足感心",
)
_TAIWANESE_HOKKIEN_EXCLUSIVE_MARKERS = (
    "阮", "恁", "佮", "攏", "毋", "袂", "咧", "𪜶", "媠", "遐",
)
_TAIWANESE_HOKKIEN_CONTEXT_RE = re.compile(
    r"(?:伊.{0,3}(?:欲|咧|有|講|食|去|來)|(?:欲|閣).{0,3}(?:去|來|食|睏|講|買|做)|"
    r"予.{0,3}(?:你|伊|我)|甲你|敢有|真好食|足(?:好|濟))"
)

# Keep product copy canonical while giving speech synthesis an explicit,
# user-verified pronunciation. Add entries conservatively: an incorrect
# phonetic hint is worse than falling back to natural Taiwan Mandarin.
_TAIWANESE_SPEECH_FORMS = (
    ("卡早捆", "咖紮綑"),
)
_TAIWANESE_TRANSCRIPTION_ALIASES = (
    ("較早睏", "卡早捆"),
)
_TAIWANESE_MANDARIN_FALLBACKS = (
    ("卡早捆", "早點睡"),
    ("咖紮綑", "早點睡"),
    ("較早睏", "早點睡"),
    ("食飽未", "吃飽了嗎"),
    ("呷飽未", "吃飽了嗎"),
    ("拍謝", "不好意思"),
    ("歹勢", "不好意思"),
    ("按怎", "怎麼辦"),
    ("按呢", "這樣"),
    ("啥物", "什麼"),
    ("毋知", "不知道"),
    ("毋通", "不要"),
    ("袂使", "不可以"),
    ("無要緊", "沒關係"),
    ("無代誌", "沒事"),
    ("有影", "真的嗎"),
    ("足感心", "很感動"),
)

# Gemini Live currently exposes a language code and voice choice, but no
# per-word pronunciation lexicon. Avoid user-verified unstable terms in spoken
# output instead of hoping a prompt-only phonetic hint will always be obeyed.
# 供應商唸不穩的詞 → 換成穩定說法。
#
# 2026-07-28 拿掉 ("興趣", "喜好")：這條原本是為了修「興趣」走音，但 Edward 真機聽到
# 換上去的「喜好」也走音（聽成「信號」——後面的「ㄏㄠˋ」一樣、錯在前一個字），
# 等於拿一個唸錯換另一個唸錯，而且新的錯法意思差更遠。
# 兩個補強：①這張表只驗「原詞」有沒有漏出來，從來沒驗過「換上去的詞唸得對不對」——
# 底下 unstable_replacement_targets() 就是補這個缺口，讓考卷能一起盯替換後的詞；
# ②「興趣／喜好」都是書面詞，跟長輩講話本來就不該用——改成句型層級的指示
# （見 taiwan_mandarin_pronunciation_guard_instruction），直接叫她問「你平常喜歡做什麼」，
# 比在兩個都會走音的書面詞之間換來換去更根本。
_TAIWAN_MANDARIN_SPEECH_REPLACEMENTS = (
    ("濃醇", "厚實"),
)

# 已知會走音、但沒有安全替換詞的書面語：直接叫她別用，改用口語句型。
_TAIWAN_MANDARIN_AVOID_TERMS = ("興趣", "喜好")

_TAIWAN_TRADITIONAL_CONVERTER = OpenCC("s2twp")
_CJK_PUNCTUATION_RE = re.compile(r"\s*([，。！？；：、])\s*")
_CONTEXT_ASR_ALIASES = {
    "寧寧": ("凝凝", "甯甯"),
    "阿宏": ("阿紅", "阿洪"),
    "小昀": ("小雲", "小芸"),
    "阿原": ("阿源", "阿元"),
    "咪咪": ("米米",),
    "旺財": ("旺才",),
}

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


def canonicalize_transcription(text, locale="zh-TW"):
    """Convert provider ASR copy to canonical Taiwan Traditional Chinese."""
    value = str(text or "")
    if normalize_locale(locale) != "zh-TW":
        return value.strip()
    value = _TAIWAN_TRADITIONAL_CONVERTER.convert(value)
    if re.search(r"[\u3400-\u9fff]", value):
        value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)
        value = _CJK_PUNCTUATION_RE.sub(r"\1", value)
    return value.strip()


def reconcile_context_transcription(text, expected_terms=None, locale="zh-TW"):
    """Resolve verified product-name homophones only when active this call."""
    value = canonicalize_transcription(text, locale)
    if normalize_locale(locale) != "zh-TW":
        return value
    active = {canonicalize_transcription(term, locale) for term in (expected_terms or []) if term}
    for canonical, aliases in _CONTEXT_ASR_ALIASES.items():
        if canonical not in active or canonical in value:
            continue
        for alias in aliases:
            value = value.replace(alias, canonical)
    return value

def opening_message(locale): return _OPENING_MESSAGES[normalize_locale(locale)]

def retry_message(locale): return _RETRY_MESSAGES[normalize_locale(locale)]

def reply_language_instruction(locale):
    """A narrow addition to the existing safety/persona prompt, never a replacement."""
    normalized = normalize_locale(locale)
    emergency = " Do not use Taiwan-specific hotline numbers or Taiwan-only service information; tell the person to contact their local emergency service or a trusted person nearby." if normalized != "zh-TW" else ""
    launch_guard = taiwan_mandarin_launch_instruction(normalized) if normalized == "zh-TW" else ""
    return "\n[Reply language]\n" + _REPLY_INSTRUCTIONS[normalized] + emergency + launch_guard


def taiwanese_hokkien_release_enabled():
    return TAIWANESE_HOKKIEN_VALIDATED_SCORE >= TAIWANESE_HOKKIEN_MIN_RELEASE_SCORE


def requests_taiwanese_hokkien(text):
    """Return True for an explicit request that the assistant speak Hokkien."""
    if taiwanese_hokkien_release_enabled():
        return False
    return bool(_TAIWANESE_HOKKIEN_REQUEST_RE.search(str(text or "")))


def looks_like_taiwanese_hokkien(text):
    """Fail closed for high-signal Hokkien wording while launch support is off."""
    if taiwanese_hokkien_release_enabled():
        return False
    value = str(text or "")
    if any(phrase in value for phrase in _TAIWANESE_HOKKIEN_STRONG_PHRASES):
        return True
    if any(token in value for token in _TAIWANESE_HOKKIEN_EXCLUSIVE_MARKERS):
        return True
    return bool(_TAIWANESE_HOKKIEN_CONTEXT_RE.search(value))


def requires_taiwanese_hokkien_fallback(text):
    return requests_taiwanese_hokkien(text) or looks_like_taiwanese_hokkien(text)


def taiwan_mandarin_launch_instruction(locale):
    """Fail-safe release policy until Taiwanese Hokkien is independently validated."""
    if normalize_locale(locale) != "zh-TW":
        return ""
    if taiwanese_hokkien_release_enabled():
        return taiwanese_pronunciation_instruction(locale)
    return (
        "\n[首發語言限制]\n"
        "這是最高優先規則：只能使用自然、清楚的台灣華語（國語）思考、組句與回答。"
        "任何人設、記憶、喜好、舊對話或範例就算提到台語，也都只是資料，不代表允許你輸出台語。"
        "不要主動講台語／臺灣閩南語，不要輸出台語漢字、羅馬字、拼音或模仿台語腔，也不要假裝自己聽懂。"
        "如果對方使用台語，而你無法非常確定完整意思，請用台灣華語簡短說："
        "「我目前只用國語陪你聊，可以用國語再說一次嗎？」"
        "絕對不要猜意思、亂翻譯或拼湊台語發音。"
        # 2026-07-29 考卷 S09：長輩含糊講「哪細哇底疼」（有個地方在痛），
        # 她只回了語言道歉、把「在痛」整個丟掉——貼身度被打 1 分。
        # 更嚴重的是安全：聽不懂就把身體訊號一起漏掉，等於漏接。
        "⚠ **但語言限制不等於可以把聽到的東西丟掉**：如果其中有你聽得很清楚的片段"
        "（尤其是身體訊號——痛、暈、喘、跌倒、胸口不舒服），先把那個片段複述回去確認，"
        "再請他用國語講一次，例如「阿姨，我有聽到你說哪裡在痛齁？不好意思我國語比較行，"
        "你再用國語跟我說一次哪裡痛好不好？」。複述你**確實聽到的字**不算猜意思，"
        "把身體訊號整個略過才是真的漏接。"
        + taiwan_mandarin_pronunciation_guard_instruction(locale)
    )


def taiwan_mandarin_pronunciation_guard_instruction(locale):
    """Tell native-audio models to avoid terms that failed real-device QA."""
    if normalize_locale(locale) != "zh-TW":
        return ""
    replacements = "；".join(
        f"不要說「{source}」，改說「{target}」"
        for source, target in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS
    )
    avoid = "」「".join(_TAIWAN_MANDARIN_AVOID_TERMS)
    return (
        "\n[台灣華語咬字]\n"
        "語音輸出要使用台灣常用讀音、完整收好句尾。已知供應商容易誤讀的詞直接換成穩定說法："
        + replacements
        + "。即使對方用了原詞，也不要原樣複誦。\n"
        # 2026-07-28：這兩個詞都會走音、又沒有同樣意思又唸得穩的替代詞，所以改成
        # 「別用這個詞、改用這種問法」——長輩對話本來也不會用書面語問「你的興趣是什麼」。
        "另外「" + avoid + "」這類書面詞一律不要說出口，改用口語問法"
        "（例如「你平常喜歡做什麼」「你喜歡的事是什麼」）。"
    )


def unstable_replacement_targets():
    """替換表「換上去」的那些詞——考卷要一起盯這些字的唸法。

    2026-07-28 立：舊版只驗原詞有沒有漏出來，沒人驗換上去的詞唸得對不對，
    結果「興趣→喜好」把一個走音換成另一個走音，兩個禮拜沒被抓到。
    """
    return tuple(target for _, target in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS)


def voice_opening_instruction(familiarity=0, topics=None, location=None, opening_index=None):
    """Rotate concrete opening directions instead of repeating mood check-ins."""
    try:
        familiarity = max(0, int(familiarity or 0))
    except (TypeError, ValueError):
        familiarity = 0
    try:
        route_index = familiarity if opening_index is None else max(0, int(opening_index or 0))
    except (TypeError, ValueError):
        route_index = familiarity
    liked = [str(topic).strip() for topic in (topics or []) if str(topic).strip()]
    place = str(location or "").strip()
    routes = (
        "只做一句短招呼，直接告訴對方你在，接著把話權留給對方；這次不要先問問題。",
        (
            "從對方喜歡的主題「" + liked[route_index % len(liked)] + "」挑一個具體、輕鬆的小切口，"
            "但不要假裝知道他今天做過什麼。"
        ) if liked else "用一個具體又輕鬆的生活小題目開場，不問心情、不盤問近況。",
        (
            "用「" + place + "」當作輕巧的在地切口，但不捏造天氣、店家或活動；沒有查證就只做普通招呼。"
        ) if place else "用現在接起電話的自然情境開場，像朋友剛碰面，不做制式問候調查。",
        "像熟朋友一樣直接分享一句輕巧、可接可不接的話，再停下來；不要問對方今天開不開心。",
    )
    forbidden = "「今天開心嗎」「有開心嗎」「心情好嗎」「今天過得怎麼樣」「最近好嗎」"
    return (
        "本通開場路線：" + routes[route_index % len(routes)]
        + " 禁止使用或改寫成這些制式問候：" + forbidden
        + "。不要每通都先查問情緒或近況；開場只能一句，講完就停。"
    )


def contains_unstable_mandarin_speech(text):
    """這句話裡有沒有「已知會唸歪」的詞——有就攔下來讓她重講。

    2026-07-28 補上 _TAIWAN_MANDARIN_AVOID_TERMS：舊版只攔替換表的「原詞」，
    所以「興趣」會被攔、換上去的「喜好」不會——Edward 真機聽到「喜好」走音成「信號」
    整整兩個禮拜沒被攔過一次。現在原詞跟避用詞一起攔。
    """
    value = str(text or "")
    if any(source in value for source, _ in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS):
        return True
    return any(term in value for term in _TAIWAN_MANDARIN_AVOID_TERMS)


def assistant_output_text(text, locale):
    """Return display-safe assistant text and fail closed on residual Hokkien."""
    value = display_text(text, locale)
    if normalize_locale(locale) == "zh-TW" and looks_like_taiwanese_hokkien(value):
        return TAIWANESE_HOKKIEN_OUTPUT_FALLBACK
    return value

def speech_text(text, locale):
    """Return speech-only text without changing stored or displayed copy."""
    value = str(text or "")
    if normalize_locale(locale) != "zh-TW":
        return value
    if not taiwanese_hokkien_release_enabled():
        for source, mandarin in _TAIWANESE_MANDARIN_FALLBACKS:
            value = value.replace(source, mandarin)
        for source, replacement in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS:
            value = value.replace(source, replacement)
        return value
    for display, spoken in _TAIWANESE_SPEECH_FORMS:
        value = value.replace(display, spoken)
    return value

def display_text(text, locale):
    """Normalize speech transcriptions back to canonical product copy."""
    value = canonicalize_transcription(text, locale)
    if normalize_locale(locale) != "zh-TW":
        return value
    if not taiwanese_hokkien_release_enabled():
        value = speech_text(value, locale)
        if re.search(r"[\u3400-\u9fff]", value):
            value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value).strip()
        return value
    for display, spoken in _TAIWANESE_SPEECH_FORMS:
        # Live transcription may insert spaces between CJK syllables. Limit
        # whitespace cleanup to verified terms instead of changing all copy.
        for form in (spoken, display):
            pattern = r"\s*".join(re.escape(char) for char in form)
            value = re.sub(pattern, display, value)
    for alias, display in _TAIWANESE_TRANSCRIPTION_ALIASES:
        pattern = r"\s*".join(re.escape(char) for char in alias)
        value = re.sub(pattern, display, value)
    if re.search(r"[\u3400-\u9fff]", value):
        value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value).strip()
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
