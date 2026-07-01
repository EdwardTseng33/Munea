"""沐寧記憶引擎 · 真萃取（取代關鍵字 mock 與「整句兜底」）

只從「長輩(使用者)說的話」萃取『關於這位長輩的事實』，寫進我們自己的四層/類型 schema。
- 絕不把 AI/寧寧自己講的話當成記憶（修掉「存到哈囉」的 bug）。
- 空泛招呼、沒資訊的閒聊 → 不記。
- 借鏡 Mem0 的「萃取→分類→打分」做法，但用我們自己的設計（`AI設計期待` 四層記憶）。

獨立模組，可被 server / butler 呼叫；也可單獨自測：GEMINI_API_KEY=... python engine/memory_engine.py
"""

import os
import json

from google import genai
from google.genai import types

_KEY = os.environ.get("GEMINI_API_KEY")
_client = genai.Client(api_key=_KEY) if _KEY else None
MODEL = "gemini-2.5-flash"

TIERS = {"core", "long", "recent", "today"}
TYPES = {
    "identity", "preference", "relationship", "routine", "health_context",
    "emotion", "topic_interest", "temporary_event", "safety_signal",
}
SENSITIVE = {"health_context", "emotion", "safety_signal"}

_SYS = """你是沐寧的記憶萃取員。從「長輩（使用者）說的話」裡，抽出「值得長期記住、關於這位長輩的事實」。
硬規則：
- 只從使用者的話萃取；**絕對不要**把 AI／寧寧自己講的話、招呼語當成記憶。
- 只記「關於這個人的事實」：身份、家人關係、喜好、習慣、健康、心情、興趣、近期事件、安全訊號。
- 空泛招呼、沒有資訊的閒聊、AI 的回話 → 一律不記（回空陣列 []）。
- content 用第三人稱、簡潔描述這位長輩的事實（例：「孫子小寶下個月結婚」「膝蓋不好、晚上追韓劇」）。
欄位：
- type：identity / preference / relationship / routine / health_context / emotion / topic_interest / temporary_event / safety_signal
- tier：core（定義你是誰：名字/家人/慢性病/喪偶，永久）、long（重要事件/長期喜好）、recent（近 1-2 週近況心情）、today（當天一次性）
- importance 0-1：情感重量高、健康相關、會重複的 → 高分；一次性閒聊 → 低分。
- confidence 0-1：這條事實有多確定。
只回 JSON 陣列：[{"type":..,"tier":..,"content":..,"importance":..,"confidence":..}]；沒有可記的就回 []。"""


def _user_text(history):
    return "\n".join(
        h.get("text", "") for h in (history or [])
        if h.get("role") == "user" and h.get("text")
    )


def extract(history):
    """history: [{'role':'user'|'model','text':..}] → 記憶候選 list（只含長輩的事實）。"""
    if not _client:
        return []
    user_text = _user_text(history)
    if not user_text.strip():
        return []
    try:
        r = _client.models.generate_content(
            model=MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text="長輩說的話：\n" + user_text)])],
            config=types.GenerateContentConfig(
                system_instruction=_SYS, temperature=0.2, response_mime_type="application/json"
            ),
        )
        items = json.loads(r.text)
    except Exception:
        return []
    out = []
    for it in (items if isinstance(items, list) else []):
        content = (it.get("content") or "").strip()
        if not content:
            continue
        t = it.get("type") if it.get("type") in TYPES else "temporary_event"
        tier = it.get("tier") if it.get("tier") in TIERS else "recent"
        out.append({
            "type": t,
            "tier": tier,
            "content": content[:500],
            "importance": round(float(it.get("importance", 0.5) or 0.5), 2),
            "confidence": round(float(it.get("confidence", 0.6) or 0.6), 2),
            "sensitivity": "sensitive" if t in SENSITIVE else "normal",
        })
    return out


if __name__ == "__main__":
    demo = [
        {"role": "user", "text": "寧寧，我孫子小寶下個月要結婚了，我最近膝蓋不太好，晚上都在追韓劇"},
        {"role": "model", "text": "哈囉，我聽見了，你慢慢說，我都在。"},
        {"role": "user", "text": "嗯今天天氣不錯"},
    ]
    print("萃取結果（應有孫子結婚/膝蓋/韓劇，不該有『哈囉』）：")
    for m in extract(demo):
        print(" -", m)
