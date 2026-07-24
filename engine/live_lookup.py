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
