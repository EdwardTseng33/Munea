#!/usr/bin/env python3
"""衛教知識庫（B2・2026-07-24）：21 題策展題庫的觸發與注入。

設計拍板（7/24）＝混合式：
- 常駐：保命紅線（中風FAST／心梗／低血糖／急性譫妄）＋褪黑激素法規，由 chat_engine.RED 併入、
  文字線與語音線每一輪都在。
- 觸發：其餘 21 題按「長輩真實問法」關鍵字命中才注入（單次 +500-700 字）。
  否決全塞——21 題全進說明書會膨脹兩倍、把安全紅線淹沒在雜訊裡。

策展題庫、不是開放式 RAG（7/24 三路調研收斂）：內容全部出自已雙審的
docs/research/衛教題庫-21題完整劇本v1-2026-07-24.md，紅旗逐條回鏈官方來源；
這個模組只做關鍵字比對與文字組裝，不呼叫任何模型、不連網、不碰劑量與診斷。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOPICS_PATH = os.path.join(HERE, "health_topics.json")

with open(TOPICS_PATH, encoding="utf-8") as _f:
    _DOC = json.load(_f)

TOPICS = _DOC["topics"]
TOPIC_BY_ID = {t["id"]: t for t in TOPICS}

# 每通電話最多注入幾題：衛教是配菜、不是把通話變成衛教講座。
MAX_TOPICS_PER_CALL = 3
# 單輪最多同時注入幾題：兩題以上通常代表用戶一句話跨題，再多就淹沒重點。
MAX_TOPICS_PER_TURN = 2


def resident_rules():
    """常駐保命紅線（進 chat_engine.RED、所有線路每輪都在）。"""
    return _DOC["resident"]


def match_topics(text, limit=MAX_TOPICS_PER_TURN, exclude=None):
    """關鍵字比對：回傳命中的 topic id 清單（命中字愈長愈優先＝愈specific愈可信）。
    純字串包含比對——ASR 字幕沒有標點、打字有錯字都吃得下最大公約數；不做模型呼叫。"""
    if not text:
        return []
    exclude = exclude or ()
    scored = []
    for t in TOPICS:
        if t["id"] in exclude:
            continue
        hit_len = sum(len(k) for k in t["keywords"] if k in text)
        if hit_len:
            scored.append((hit_len, t["id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [tid for _, tid in scored[:limit]]


def injection_for(text, exclude=None):
    """文字線用：按這一句用戶的話組出注入段；沒命中回空字串（不佔說明書）。"""
    ids = match_topics(text, exclude=exclude)
    if not ids:
        return ""
    parts = []
    for tid in ids:
        t = TOPIC_BY_ID[tid]
        parts.append(f"【{t['title']}】{t['inject']}（出處：{t['source']}）")
    return (
        "（衛教資料庫命中・這一輪他聊到相關話題，回應時自然運用下面已審核的衛教方向；"
        "照舊先接住情緒、保持一兩句短話、他想深入才展開；"
        "短話塞不下全部時的取捨順序：紅旗紅線＞更有效的替代方向＞證據誠實——"
        "潑冷水（說某保健品沒那麼神）時同一句要帶更有效的替代、不能只否定不給路；"
        "若其實不相關就忽略這段："
        + "".join(parts) + "）"
    )


def voice_cue(topic_id):
    """語音線用：在守護腦同一個「輪替空檔」機制排隊送出的衛教提示（每題整通只送一次）。"""
    t = TOPIC_BY_ID[topic_id]
    return (
        f"（系統衛教提示、不是用戶說的話——他剛聊到「{t['title']}」相關話題。"
        f"接下來回應時自然運用這份已審核的衛教方向、絕不把這段提示唸出來："
        f"{t['inject']}（出處：{t['source']}）"
        "照舊保持一兩句短話、先接情緒、他想深入才展開。）"
    )
