"""Small, testable helpers for Voice's controlled current-information lookup."""

import re


TOOL_NAME = "search_current_information"
CUE_TEXT = "我幫你查一下"
MAX_QUERY_CHARS = 320
MAX_RESULT_CHARS = 1200
SUPPORTED_LOCALES = ("zh-TW", "en", "ja", "es")

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CITATION_RE = re.compile(r"\[(?:\d+(?:\s*[-,]\s*\d+)*|cite[^\]]*)\]", re.IGNORECASE)


def normalize_query(value):
    return " ".join(str(value or "").split())[:MAX_QUERY_CHARS]


def normalize_locale(locale):
    raw = str(locale or "").strip().replace("_", "-")
    if raw in SUPPORTED_LOCALES:
        return raw
    lowered = raw.lower()
    if lowered.startswith("zh"):
        return "zh-TW"
    if lowered.startswith("ja"):
        return "ja"
    if lowered.startswith("es"):
        return "es"
    if lowered.startswith("en"):
        return "en"
    return "zh-TW"


_REQUEST_TEMPLATES = {
    "zh-TW": {
        "location": "使用者所在地脈絡：{location}\n",
        "question": "問題：{query}\n",
        "intro": "請使用 Google Search 查證下列問題，整理成可交給語音助理回答的繁體中文材料。\n",
        "rules": (
            "規則：只寫查得到的資訊；地點或店家問題優先核對名稱、區域與近期營業狀態；"
            "最多五個重點、不要附網址、不要寫成對使用者說話的開場，也不要捏造親身經驗；"
            "每個重點都寫成口語、可以直接照著念出來的完整句子，不要用條列符號（一、二、-、•），"
            "也不要用書面體或報告用語（例如「綜上所述」「根據查詢結果」「以下」）。"
        ),
    },
    "en": {
        "location": "User location context: {location}\n",
        "question": "Question: {query}\n",
        "intro": (
            "Use Google Search to verify the question below and prepare clear English material "
            "that a voice assistant can say naturally.\n"
        ),
        "rules": (
            "Rules: include only verified information. For places or businesses, prioritize the exact name, "
            "area, and recent operating status. Use at most five concise points, omit URLs, do not add a "
            "user-facing opening, and never invent personal experience. Write complete, conversational "
            "sentences that can be spoken aloud. Do not use bullets or report-style phrases."
        ),
    },
    "ja": {
        "location": "ユーザーの所在地情報：{location}\n",
        "question": "質問：{query}\n",
        "intro": (
            "Google Search で次の質問を確認し、音声アシスタントが自然に話せる日本語の材料にまとめてください。\n"
        ),
        "rules": (
            "ルール：確認できた情報だけを書いてください。場所や店舗については、正式名称、地域、"
            "最近の営業状況を優先して確認してください。内容は五つ以内に絞り、URL、ユーザーへの前置き、"
            "架空の体験談は入れないでください。箇条書きや報告書調ではなく、そのまま声に出せる自然な"
            "会話文で書いてください。"
        ),
    },
    "es": {
        "location": "Contexto de ubicación del usuario: {location}\n",
        "question": "Pregunta: {query}\n",
        "intro": (
            "Usa Google Search para verificar la siguiente pregunta y prepara información clara en español "
            "que un asistente de voz pueda decir de forma natural.\n"
        ),
        "rules": (
            "Reglas: incluye solo información verificada. Para lugares o negocios, comprueba primero el nombre "
            "exacto, la zona y el estado de apertura reciente. Resume en un máximo de cinco ideas, omite URL, "
            "no añadas una introducción dirigida al usuario ni inventes experiencias personales. Escribe frases "
            "completas y conversacionales que se puedan decir en voz alta, sin viñetas ni tono de informe."
        ),
    },
}


def build_request(query, location=None, locale="zh-TW"):
    clean_query = normalize_query(query)
    clean_location = " ".join(str(location or "").split())[:80]
    template = _REQUEST_TEMPLATES[normalize_locale(locale)]
    location_line = (
        template["location"].format(location=clean_location)
        if clean_location else ""
    )
    return (
        template["intro"]
        + location_line
        + template["question"].format(query=clean_query)
        + template["rules"]
    )


# 過場句去罐頭化（2026-07-25 · 語音優化週包）：先判斷問的是哪一類（天氣／新聞／
# 店家景點／其他），再從對應句庫挑一句——貼題、也不會每次都聽到同一句「我幫你查一下」。
CUE_CATEGORY_WEATHER = "weather"
CUE_CATEGORY_NEWS = "news"
CUE_CATEGORY_STORE = "store"
CUE_CATEGORY_OTHER = "other"

_TOPIC_KEYWORDS = {
    "zh-TW": {
        CUE_CATEGORY_WEATHER: (
            "天氣", "氣溫", "下雨", "會不會冷", "會不會熱", "颱風", "紫外線",
            "空氣品質", "空品", "濕度",
        ),
        CUE_CATEGORY_NEWS: ("新聞", "時事", "最近發生", "頭條", "選舉", "疫情", "股市", "股票"),
        CUE_CATEGORY_STORE: (
            "店", "餐廳", "小吃", "美食", "景點", "好玩", "推薦", "營業", "還開嗎",
            "開了嗎", "電影", "影城", "上映", "活動", "檔期", "門票", "旅遊", "玩什麼",
        ),
    },
    "en": {
        CUE_CATEGORY_WEATHER: (
            "weather", "temperature", "forecast", "rain", "cold", "hot", "storm",
            "air quality", "humidity",
        ),
        CUE_CATEGORY_NEWS: (
            "news", "headline", "latest update", "election", "outbreak", "stock market", "stocks",
        ),
        CUE_CATEGORY_STORE: (
            "restaurant", "cafe", "shop", "store", "food", "attraction", "recommend",
            "open now", "opening hours", "movie", "cinema", "event", "ticket", "travel",
        ),
    },
    "ja": {
        CUE_CATEGORY_WEATHER: (
            "天気", "気温", "予報", "雨", "寒い", "暑い", "台風", "紫外線", "空気質", "湿度",
        ),
        CUE_CATEGORY_NEWS: ("ニュース", "時事", "最新情報", "見出し", "選挙", "感染症", "株式市場", "株価"),
        CUE_CATEGORY_STORE: (
            "お店", "店舗", "レストラン", "カフェ", "グルメ", "観光", "おすすめ", "営業時間",
            "営業中", "映画", "映画館", "イベント", "チケット", "旅行",
        ),
    },
    "es": {
        CUE_CATEGORY_WEATHER: (
            "tiempo", "clima", "temperatura", "pronóstico", "lluvia", "frío", "calor",
            "tormenta", "calidad del aire", "humedad",
        ),
        CUE_CATEGORY_NEWS: (
            "noticias", "titular", "última hora", "elecciones", "brote", "bolsa", "acciones",
        ),
        CUE_CATEGORY_STORE: (
            "restaurante", "cafetería", "tienda", "comida", "atracción", "recomienda",
            "abierto", "horario", "cine", "película", "evento", "entrada", "viaje",
        ),
    },
}


def classify_query_topic(query, locale="zh-TW"):
    """粗略的關鍵字分類，只用來挑一句貼題的過場話，不影響實際查詢邏輯。
    順序有意義：天氣／新聞先判，店家／景點這個較寬的桶子放最後——
    避免「最近天氣新聞」這種句子先被店家關鍵字打到。"""
    text = str(query or "").casefold()
    preferred = normalize_locale(locale)
    locale_order = (preferred,) + tuple(
        candidate for candidate in SUPPORTED_LOCALES if candidate != preferred
    )
    for candidate in locale_order:
        keyword_groups = _TOPIC_KEYWORDS[candidate]
        for category in (
            CUE_CATEGORY_WEATHER,
            CUE_CATEGORY_NEWS,
            CUE_CATEGORY_STORE,
        ):
            if any(keyword.casefold() in text for keyword in keyword_groups[category]):
                return category
    return CUE_CATEGORY_OTHER


# 每類 2-3 句：短、口語、跟她的角色分寸一致（不裝熱情、不加語助詞）。CUE_TEXT 保留在
# other 池首位，向後相容任何還在直接引用這個常數當預設值的呼叫端。
CUE_PHRASES_BY_LOCALE = {
    "zh-TW": {
        CUE_CATEGORY_WEATHER: (
            "我幫你看一下天氣喔",
            "等我一下，我查查外面天氣",
            "好，我看一下天氣怎麼樣",
        ),
        CUE_CATEGORY_NEWS: (
            "我幫你看一下新聞",
            "等我一下，我查查看",
            "好，我看一下最近的消息",
        ),
        CUE_CATEGORY_STORE: (
            "好，我幫你看看",
            "我查一下這個喔",
            "等我一下，我看看",
        ),
        CUE_CATEGORY_OTHER: (
            CUE_TEXT,
            "等我一下，我查查看",
            "好，我看一下喔",
        ),
    },
    "en": {
        CUE_CATEGORY_WEATHER: (
            "Let me check the weather for you.",
            "One moment, I will check the weather.",
            "Okay, let me see what the weather is like.",
        ),
        CUE_CATEGORY_NEWS: (
            "Let me check the latest news.",
            "One moment, I will look that up.",
            "Okay, let me check the latest update.",
        ),
        CUE_CATEGORY_STORE: (
            "Okay, let me check that for you.",
            "I will look that up.",
            "One moment, let me take a look.",
        ),
        CUE_CATEGORY_OTHER: (
            "Let me check that for you.",
            "One moment, I will look that up.",
            "Okay, let me take a look.",
        ),
    },
    "ja": {
        CUE_CATEGORY_WEATHER: (
            "天気を確認しますね。",
            "少し待ってくださいね。天気を調べます。",
            "はい、今の天気を見てみます。",
        ),
        CUE_CATEGORY_NEWS: (
            "最新のニュースを確認しますね。",
            "少し待ってくださいね。調べてみます。",
            "はい、最近の情報を見てみます。",
        ),
        CUE_CATEGORY_STORE: (
            "はい、確認してみますね。",
            "その情報を調べますね。",
            "少し待ってくださいね。見てみます。",
        ),
        CUE_CATEGORY_OTHER: (
            "確認してみますね。",
            "少し待ってくださいね。調べてみます。",
            "はい、見てみますね。",
        ),
    },
    "es": {
        CUE_CATEGORY_WEATHER: (
            "Déjame consultar el tiempo.",
            "Un momento, voy a revisar el tiempo.",
            "De acuerdo, voy a ver qué tiempo hace.",
        ),
        CUE_CATEGORY_NEWS: (
            "Déjame consultar las últimas noticias.",
            "Un momento, voy a buscarlo.",
            "De acuerdo, voy a revisar la información más reciente.",
        ),
        CUE_CATEGORY_STORE: (
            "De acuerdo, voy a comprobarlo.",
            "Voy a buscar esa información.",
            "Un momento, déjame revisarlo.",
        ),
        CUE_CATEGORY_OTHER: (
            "Déjame comprobarlo.",
            "Un momento, voy a buscarlo.",
            "De acuerdo, déjame revisarlo.",
        ),
    },
}
CUE_PHRASES = CUE_PHRASES_BY_LOCALE["zh-TW"]


def cue_phrase(category, index=0, locale="zh-TW"):
    """挑一句貼題的過場話。用 index 而不是隨機——同一支電話裡連問兩次同類問題，
    輪到下一句而不是每次重骰；也讓這個函式維持純函式、好單元測試。"""
    locale_phrases = CUE_PHRASES_BY_LOCALE[normalize_locale(locale)]
    pool = locale_phrases.get(category) or locale_phrases[CUE_CATEGORY_OTHER]
    if not pool:
        return locale_phrases[CUE_CATEGORY_OTHER][0]
    return pool[index % len(pool)]


# 查太久（5.5 秒安撫句）同樣去罐頭化：原本固定一句，現在跟過場句一樣輪替。
WAIT_PHRASES_BY_LOCALE = {
    "zh-TW": (
        "還在幫你找喔，再等我一下。",
        "資料有點多，我再看一下喔。",
        "快好了，再等我幾秒喔。",
    ),
    "en": (
        "I am still looking. Give me another moment.",
        "There is a little more to check. I am still looking.",
        "Almost there. Give me a few more seconds.",
    ),
    "ja": (
        "まだ調べています。もう少し待ってくださいね。",
        "確認する情報が少し多いので、もう少し見ていますね。",
        "もうすぐです。あと少しだけ待ってくださいね。",
    ),
    "es": (
        "Todavía estoy buscando. Dame un momento más.",
        "Hay un poco más que revisar. Sigo buscando.",
        "Casi está. Dame unos segundos más.",
    ),
}
WAIT_PHRASES = WAIT_PHRASES_BY_LOCALE["zh-TW"]


def wait_phrase(index=0, locale="zh-TW"):
    pool = WAIT_PHRASES_BY_LOCALE[normalize_locale(locale)]
    return pool[index % len(pool)]


_FAILURE_INSTRUCTIONS = {
    "zh-TW": {
        "unavailable": "查詢服務暫時沒有回應。請直接用一句話跟用戶說現在查不到、建議晚點再問，然後繼續原本的聊天。不要再呼叫查詢工具。",
        "timeout": "查詢沒有回應。請用一句話跟用戶說現在查不到、之後再幫忙看，除非用戶再次主動要求，不要再呼叫查詢工具。",
        "failed": "查詢出了點狀況。請用一句話跟用戶說現在查不到、之後再幫忙看，除非用戶再次主動要求，不要再呼叫查詢工具。",
    },
    "en": {
        "unavailable": "The lookup service is temporarily unavailable. Tell the user in one sentence that you cannot check it right now, suggest trying later, then continue the conversation. Do not call the lookup tool again.",
        "timeout": "The lookup did not respond. Tell the user in one sentence that you cannot check it right now and can try again later. Do not call the lookup tool again unless the user asks.",
        "failed": "The lookup ran into a problem. Tell the user in one sentence that you cannot check it right now and can try again later. Do not call the lookup tool again unless the user asks.",
    },
    "ja": {
        "unavailable": "検索サービスが一時的に応答していません。今は確認できないことと、後でもう一度試せることを日本語で一文だけ伝え、そのまま会話を続けてください。検索ツールを再度呼び出さないでください。",
        "timeout": "検索から応答がありません。今は確認できず、後でもう一度調べられることを日本語で一文だけ伝えてください。ユーザーが改めて頼まない限り、検索ツールを再度呼び出さないでください。",
        "failed": "検索中に問題が起きました。今は確認できず、後でもう一度調べられることを日本語で一文だけ伝えてください。ユーザーが改めて頼まない限り、検索ツールを再度呼び出さないでください。",
    },
    "es": {
        "unavailable": "El servicio de búsqueda no responde temporalmente. Dile al usuario en una sola frase que no puedes comprobarlo ahora y que puede intentarlo más tarde; después continúa la conversación. No vuelvas a llamar a la herramienta de búsqueda.",
        "timeout": "La búsqueda no respondió. Dile al usuario en una sola frase que no puedes comprobarlo ahora y que podrás intentarlo más tarde. No vuelvas a llamar a la herramienta salvo que el usuario lo pida.",
        "failed": "La búsqueda tuvo un problema. Dile al usuario en una sola frase que no puedes comprobarlo ahora y que podrás intentarlo más tarde. No vuelvas a llamar a la herramienta salvo que el usuario lo pida.",
    },
}


def failure_instruction(reason, locale="zh-TW"):
    instructions = _FAILURE_INSTRUCTIONS[normalize_locale(locale)]
    return instructions.get(reason) or instructions["failed"]


def _grounding_metadata(response):
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    return getattr(candidates[0], "grounding_metadata", None)


def source_count(response):
    grounding = _grounding_metadata(response)
    chunks = getattr(grounding, "grounding_chunks", None) if grounding is not None else None
    return len(chunks or [])


def sanitize_result(value):
    text = _MARKDOWN_LINK_RE.sub(r"\1", str(value or ""))
    text = _URL_RE.sub("", text)
    text = _CITATION_RE.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_RESULT_CHARS]


def extract_result(response):
    text = sanitize_result(getattr(response, "text", ""))
    if not text:
        raise ValueError("lookup returned no answer material")
    sources = source_count(response)
    if sources < 1:
        raise ValueError("lookup returned no grounded sources")
    return {"text": text, "sources": sources}
