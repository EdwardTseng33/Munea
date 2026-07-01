"""沐寧記憶引擎 · 真萃取（取代關鍵字 mock 與「整句兜底」）

只從「長輩(使用者)說的話」萃取『關於這位長輩的事實』，寫進我們自己的四層/類型 schema。
- 絕不把 AI/寧寧自己講的話當成記憶（修掉「存到哈囉」的 bug）。
- 空泛招呼、沒資訊的閒聊 → 不記。
- 借鏡 Mem0 的「萃取→分類→打分」做法，但用我們自己的設計（`AI設計期待` 四層記憶）。

獨立模組，可被 server / butler 呼叫；也可單獨自測：GEMINI_API_KEY=... python engine/memory_engine.py
"""

import os
import json
import math

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


EMBED_MODEL = "gemini-embedding-001"
_embed_cache = {}


def _embed(text, task_type="RETRIEVAL_DOCUMENT"):
    text = (text or "").strip()
    if not text or not _client:
        return None
    key = (task_type, text)
    if key in _embed_cache:
        return _embed_cache[key]
    try:
        r = _client.models.embed_content(
            model=EMBED_MODEL, contents=text,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        vec = list(r.embeddings[0].values)
    except Exception:
        return None
    _embed_cache[key] = vec
    return vec


def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def retrieve(query, items, limit=5):
    """語意召回：用「意思」找回相關記憶（本機版，之後一鍵換 pgvector）。
    分數 = 語意相似度 × 重要性加權。回傳 top-K，含 _score/_sim 供驗證。"""
    qv = _embed(query, task_type="RETRIEVAL_QUERY")
    if qv is None:
        return []
    scored = []
    for it in items or []:
        vec = _embed(it.get("content"))
        if vec is None:
            continue
        sim = _cosine(qv, vec)
        imp = float(it.get("importance", 0.5) or 0.5)
        scored.append((sim + 0.05 * imp, sim, it))  # 以語意相似度為主、重要性只做微幅加權
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, sim, it in scored[:limit]:
        row = dict(it)
        row["_score"] = round(score, 3)
        row["_sim"] = round(sim, 3)
        out.append(row)
    return out


def consolidate(items, sim_threshold=0.9):
    """整理員：① 剪掉低價值（一次性閒聊、低分）② 合併重複／語意近重複（同類、意思幾乎一樣，留較優的）。
    回傳 (整理後清單, 報告)。之後由背景管家腦定期呼叫。"""
    items = [dict(it) for it in (items or [])]

    def keepscore(it):
        return (float(it.get("importance", 0.5) or 0.5), float(it.get("confidence", 0.5) or 0.5))

    pruned, kept = [], []
    for it in items:
        imp = float(it.get("importance", 0.5) or 0.5)
        if it.get("type") == "temporary_event" and imp < 0.3:
            pruned.append(it)
        else:
            kept.append(it)

    kept.sort(key=keepscore, reverse=True)  # 較優的排前、優先保留
    result, merged, vecs = [], [], {}
    for it in kept:
        content = it.get("content", "")
        vec = _embed(content)
        dup_of = None
        for idx, r in enumerate(result):
            if r.get("type") != it.get("type"):
                continue
            if content and content == r.get("content"):
                dup_of = r
                break
            rv = vecs.get(idx)
            if vec and rv and _cosine(vec, rv) >= sim_threshold:
                dup_of = r
                break
        if dup_of is None:
            vecs[len(result)] = vec
            result.append(it)
        else:
            merged.append(it)

    report = {
        "before": len(items),
        "after": len(result),
        "prunedLowValue": len(pruned),
        "mergedDuplicates": len(merged),
    }
    return result, report


_PROFILE_SYS = """你是沐寧的側寫員。讀「關於這位長輩的所有記憶」，合成一張『這個人現在是誰』的側寫，
給陪伴 AI（寧寧）主動關心時用。要溫暖、具體、講當下的他，不要條列一堆流水帳。
只回 JSON 物件，欄位：
- who：一句話核心（名字／家人／慢性病／喪偶等定義他的事）
- recent：近況（最近在幹嘛、生活發生什麼）
- moodTrend：心情走向（最近偏什麼情緒；沒線索就寫「平穩」）
- caresAbout：最在乎的 2-3 件事（陣列）
- intoLately：最近迷什麼／喜歡什麼 2-3 個（陣列）
- openingIdeas：寧寧可以主動開口關心／聊的 2-3 個點子（陣列，親切口語，像家人問候）
沒有足夠資訊的欄位就給空字串或空陣列，不要瞎編。"""


def build_living_profile(items):
    """活的側寫：讀所有記憶 → 合成一張「這位長輩現在是誰」（近況／心情走向／最在乎／最近迷什麼／可主動開口的點子）。
    餵給主動開口與人格。回 dict。"""
    if not _client or not items:
        return {}
    by_tier = {"core": [], "long": [], "recent": [], "today": []}
    for it in items:
        tier = it.get("tier") if it.get("tier") in by_tier else "recent"
        by_tier[tier].append(it.get("content", ""))
    lines = []
    for tier, label in (("core", "核心（你是誰）"), ("long", "長期（重要事件/喜好）"),
                        ("recent", "近況"), ("today", "今天")):
        if by_tier[tier]:
            lines.append(f"【{label}】\n" + "\n".join(f"- {c}" for c in by_tier[tier] if c))
    digest = "\n\n".join(lines)
    if not digest.strip():
        return {}
    try:
        r = _client.models.generate_content(
            model=MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text="這位長輩的記憶：\n" + digest)])],
            config=types.GenerateContentConfig(
                system_instruction=_PROFILE_SYS, temperature=0.4, response_mime_type="application/json"
            ),
        )
        profile = json.loads(r.text)
    except Exception:
        return {}
    if not isinstance(profile, dict):
        return {}
    return {
        "who": (profile.get("who") or "").strip(),
        "recent": (profile.get("recent") or "").strip(),
        "moodTrend": (profile.get("moodTrend") or "").strip(),
        "caresAbout": [str(x).strip() for x in (profile.get("caresAbout") or []) if str(x).strip()][:3],
        "intoLately": [str(x).strip() for x in (profile.get("intoLately") or []) if str(x).strip()][:3],
        "openingIdeas": [str(x).strip() for x in (profile.get("openingIdeas") or []) if str(x).strip()][:3],
        "basedOnMemories": len(items),
    }


def migrate_profile(profile):
    """收斂：把舊的中文側寫 `user_profile`（稱呼/年紀/住在/喜好/回憶/興趣權重）
    轉成新記憶候選，之後併進 `memory_items`（單一來源）。"""
    profile = profile or {}
    out = []
    call = (profile.get("稱呼") or "").strip()
    age = str(profile.get("年紀") or "").strip()
    live = (profile.get("住在") or "").strip()
    bits = []
    if call:
        bits.append(f"稱呼「{call}」")
    if age:
        bits.append(f"{age}歲")
    if live:
        bits.append(f"住在{live}")
    if bits:
        out.append({"type": "identity", "tier": "core", "content": "長輩" + "、".join(bits),
                    "importance": 0.9, "confidence": 0.8, "sensitivity": "normal"})
    for like in (profile.get("喜好") or []):
        if str(like).strip():
            out.append({"type": "preference", "tier": "long", "content": f"長輩喜歡{str(like).strip()}",
                        "importance": 0.6, "confidence": 0.75, "sensitivity": "normal"})
    for mem in (profile.get("回憶") or []):
        if str(mem).strip():
            out.append({"type": "relationship", "tier": "long", "content": f"長輩說過：{str(mem).strip()}",
                        "importance": 0.75, "confidence": 0.7, "sensitivity": "normal"})
    for topic, w in (profile.get("興趣權重") or {}).items():
        try:
            imp = max(0.3, min(1.0, 0.5 + float(w) * 0.1))
        except Exception:
            imp = 0.5
        out.append({"type": "topic_interest", "tier": "long", "content": f"長輩對「{topic}」有興趣（權重 {w}）",
                    "importance": round(imp, 2), "confidence": 0.7, "sensitivity": "normal"})
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
