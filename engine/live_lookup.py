"""Small, testable helpers for Voice's controlled current-information lookup."""

import re


TOOL_NAME = "search_current_information"
CUE_TEXT = "我幫你查一下"
MAX_QUERY_CHARS = 320
MAX_RESULT_CHARS = 1200

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CITATION_RE = re.compile(r"\[(?:\d+(?:\s*[-,]\s*\d+)*|cite[^\]]*)\]", re.IGNORECASE)


def normalize_query(value):
    return " ".join(str(value or "").split())[:MAX_QUERY_CHARS]


def build_request(query, location=None):
    clean_query = normalize_query(query)
    clean_location = " ".join(str(location or "").split())[:80]
    location_line = f"使用者所在地脈絡：{clean_location}\n" if clean_location else ""
    return (
        "請使用 Google Search 查證下列問題，整理成可交給語音助理回答的繁體中文材料。\n"
        f"{location_line}問題：{clean_query}\n"
        "規則：只寫查得到的資訊；地點或店家問題優先核對名稱、區域與近期營業狀態；"
        "最多五個重點、不要附網址、不要寫成對使用者說話的開場，也不要捏造親身經驗；"
        # 2026-07-24：這份材料是給語音助理直接照著念的，不是給人看的報告——
        # 條列符號、書面用語念出來會很生硬，逐條寫成口語完整句才唸得順。
        "每個重點都寫成口語、可以直接照著念出來的完整句子，不要用條列符號（一、二、-、•），"
        "也不要用書面體或報告用語（例如「綜上所述」「根據查詢結果」「以下」）。"
    )


# 過場句去罐頭化（2026-07-25 · 語音優化週包）：先判斷問的是哪一類（天氣／新聞／
# 店家景點／其他），再從對應句庫挑一句——貼題、也不會每次都聽到同一句「我幫你查一下」。
CUE_CATEGORY_WEATHER = "weather"
CUE_CATEGORY_NEWS = "news"
CUE_CATEGORY_STORE = "store"
CUE_CATEGORY_OTHER = "other"

_WEATHER_KEYWORDS = ("天氣", "氣溫", "下雨", "會不會冷", "會不會熱", "颱風", "紫外線", "空氣品質", "空品", "濕度")
_NEWS_KEYWORDS = ("新聞", "時事", "最近發生", "頭條", "選舉", "疫情", "股市", "股票")
_STORE_KEYWORDS = (
    "店", "餐廳", "小吃", "美食", "景點", "好玩", "推薦", "營業", "還開嗎", "開了嗎",
    "電影", "影城", "上映", "活動", "檔期", "門票", "旅遊", "玩什麼",
)


def classify_query_topic(query):
    """粗略的關鍵字分類，只用來挑一句貼題的過場話，不影響實際查詢邏輯。
    順序有意義：天氣／新聞先判，店家／景點這個較寬的桶子放最後——
    避免「最近天氣新聞」這種句子先被店家關鍵字打到。"""
    text = str(query or "")
    if any(keyword in text for keyword in _WEATHER_KEYWORDS):
        return CUE_CATEGORY_WEATHER
    if any(keyword in text for keyword in _NEWS_KEYWORDS):
        return CUE_CATEGORY_NEWS
    if any(keyword in text for keyword in _STORE_KEYWORDS):
        return CUE_CATEGORY_STORE
    return CUE_CATEGORY_OTHER


# 每類 2-3 句：短、口語、跟她的角色分寸一致（不裝熱情、不加語助詞）。CUE_TEXT 保留在
# other 池首位，向後相容任何還在直接引用這個常數當預設值的呼叫端。
CUE_PHRASES = {
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
}


def cue_phrase(category, index=0):
    """挑一句貼題的過場話。用 index 而不是隨機——同一支電話裡連問兩次同類問題，
    輪到下一句而不是每次重骰；也讓這個函式維持純函式、好單元測試。"""
    pool = CUE_PHRASES.get(category) or CUE_PHRASES[CUE_CATEGORY_OTHER]
    if not pool:
        return CUE_TEXT
    return pool[index % len(pool)]


# 查太久（5.5 秒安撫句）同樣去罐頭化：原本固定一句，現在跟過場句一樣輪替。
WAIT_PHRASES = (
    "還在幫你找喔，再等我一下。",
    "資料有點多，我再看一下喔。",
    "快好了，再等我幾秒喔。",
)


def wait_phrase(index=0):
    return WAIT_PHRASES[index % len(WAIT_PHRASES)]


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
