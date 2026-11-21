"""寧寧的表情訊號（2026-11-21 草稿，開關預設關）。

語音主機看「她自己這一輪說的話」（output_transcription 字幕），用關鍵字判斷這一輪該是哪種表情，
送一個 {"type":"face_expression","expr":...} 給 App，App 收到就叫臉換表情（companion-face.js setExpression）。

為什麼用關鍵字、不多打一次模型：11/16 實驗過讓 3.8 自己用工具送表情——不是整輪不講話、就是慢一倍還漏輪；
表情只是「同一句話配什麼眼神」，關鍵字已經夠，而且零延遲、零花費。

規則：
- 每一輪（她開口到講完）最多送一次。字幕一進來就看；比對到關鍵字立刻送；
  累積超過 NEUTRAL_AFTER_CHARS 個字都沒有關鍵字，就送一次 neutral（把上一輪的表情收回來）。
- 優先順序：關心 > 微笑 > 傾聽（說到痛、難過時寧可關心，不要笑）。
- 開關：環境變數 MUNEA_FACE_EXPRESSIONS=1 才會送；預設關＝正式線行為完全不變。

第三輪（11/21 晚）：
- 事件多帶 pos＝觸發的那個字在這一輪字幕的第幾個字元。聲音和字幕都比她講話快很多（測試機量到 22 秒的話
  3～4 秒就送完），App 收到事件時那個字還沒講到；App 照 pos 等那個字真的被講出來才換表情。
- 手勢（gesture／gpos，每輪最多一個）：這通電話她的第一句＝揮手（wave，從第一個字開始）；
  關心＝手放胸口（chest）；沒有情緒關鍵字但在解釋事情（因為、所以、建議、記得…）＝攤開手掌（palm）。
"""

from __future__ import annotations

import os
import re

EXPRESSIONS = ("neutral", "listen", "smile", "concern")
NEUTRAL_AFTER_CHARS = 24

# 關心：對方不舒服、難過、累、擔心；或她在安撫
_CONCERN = re.compile(
    r"痛|痠|酸痛|不舒服|難過|傷心|辛苦|擔心|心疼|累了|很累|好累|睡不好|睡不著|失眠|頭暈|頭痛|發燒|咳嗽|"
    r"還好嗎|好一點了?嗎|有沒有好一點|慢慢來|別擔心|不要擔心|抱歉|對不起|不好意思|孤單|寂寞|害怕|"
    r"\b(?:hurt|hurts|ache|aching|pain|sore|sorry|worried|worry|tired|exhausted|lonely|sad|dizzy|"
    r"feeling better|are you okay|are you ok|take it easy)\b|"
    r"痛い|つらい|辛い|心配|大丈夫|疲れ|寂しい|悲しい|ごめん|すみません|無理しない",
    re.IGNORECASE,
)
# 微笑：打招呼、稱讚、開心、謝謝
_SMILE = re.compile(
    r"早安|午安|晚安|你好|哈囉|哈哈|太好了|真棒|好棒|很棒|恭喜|開心|高興|謝謝|好厲害|真厲害|不錯喔|好喜歡|好可愛|"
    r"\b(?:good morning|good afternoon|good evening|hello|hi there|great|wonderful|awesome|congrat\w*|"
    r"glad|happy|haha|thank you|thanks|lovely|well done)\b|"
    r"おはよう|こんにちは|こんばんは|よかった|すごい|嬉しい|うれしい|ありがとう|素敵|おめでとう",
    re.IGNORECASE,
)
# 解釋：沒有情緒字、但在說明事情（攤開手掌）
_EXPLAIN = re.compile(
    r"因為|所以|建議|可以試試|記得|首先|其實|比如|例如|也就是說|簡單說|"
    r"\b(?:because|so you can|i suggest|i recommend|remember to|for example|first)\b|"
    r"なぜなら|だから|おすすめ|例えば|まず",
    re.IGNORECASE,
)
# 傾聽：她在接話、請對方繼續說
_LISTEN = re.compile(
    r"嗯嗯|我在聽|你說|慢慢說|然後呢|後來呢|我在這裡|說說看|"
    r"\b(?:i'?m listening|go on|tell me more|and then)\b|"
    r"うんうん|聞いてる|それで|話して",
    re.IGNORECASE,
)


def enabled() -> bool:
    return os.environ.get("MUNEA_FACE_EXPRESSIONS", "0").strip().lower() in {"1", "true", "yes", "on"}


def match(text: str) -> tuple[str, int] | None:
    """一段她說的話 → (表情, 觸發字的位置)；沒有關鍵字回 None。"""
    t = str(text or "")
    if not t.strip():
        return None
    for expr, rx in (("concern", _CONCERN), ("smile", _SMILE), ("listen", _LISTEN)):
        m = rx.search(t)
        if m:
            return expr, m.start()
    return None


def classify(text: str) -> str | None:
    """一段她說的話 → 表情；沒有關鍵字回 None。"""
    hit = match(text)
    return hit[0] if hit else None


def next_event(st: dict, turn_text: str, new_turn: bool) -> dict | None:
    """字幕進來時呼叫：回傳要送給 App 的事件，或 None（這輪已送過／還沒判斷得出來／開關關）。

    st：這通電話的狀態表（只用 face_expr_sent 一個欄位記「這一輪送過了沒」）。
    turn_text：這一輪到目前為止她說的全部字幕。
    new_turn：這是這一輪的第一段字幕（上一輪講完後清空過）。"""
    if not enabled():
        return None
    if new_turn:
        st["face_expr_sent"] = False
        st["face_turns"] = int(st.get("face_turns") or 0) + 1
    if st.get("face_expr_sent"):
        return None
    text = str(turn_text or "")
    hit = match(text)
    explain = _EXPLAIN.search(text) if hit is None else None
    if hit is None and explain is not None:
        hit = ("neutral", explain.start())
    if hit is None and len(re.sub(r"\s+", "", text)) >= NEUTRAL_AFTER_CHARS:
        hit = ("neutral", len(text))
    if hit is None:
        return None
    st["face_expr_sent"] = True
    expr, pos = hit
    evt = {"type": "face_expression", "expr": expr, "pos": pos}
    # 手勢：每輪最多一個；第一句揮手優先
    if int(st.get("face_turns") or 0) == 1:
        evt["gesture"], evt["gpos"] = "wave", 0
    elif expr == "concern":
        evt["gesture"], evt["gpos"] = "chest", pos
    elif explain is not None:
        evt["gesture"], evt["gpos"] = "palm", explain.start()
    return evt
