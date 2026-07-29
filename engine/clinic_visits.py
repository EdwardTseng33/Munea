# -*- coding: utf-8 -*-
"""看診前後閉環（2026-07-29 · Edward 拍板「你們想清楚就優化」後建）。

**為什麼這個存在**：她原本只接得住「我不舒服怎麼辦」。但長輩真正的健康動線是四段：

    不舒服 → 去看醫生 → 醫生講了一堆 → 回家忘了一半、藥也不確定吃對沒

我們只做了第一段。第二、三、四段完全空白——而那正是長輩最需要人幫忙、
市面上也沒人做的地方。

**這一層做的事只有三件：幫他記、幫他問、幫他想起來。**
不給建議、不解讀醫囑、不評論醫生的判斷——所以完全沒有法規風險。
她是那個陪著去看病、幫忙記筆記的人，不是第二個醫生。

資料結構（一份側寫一個檔，跟效果飛輪同一個模子）：
  {personId: {"visits": [ {...} ]}}
  visit = {
    "id", "topic", "createdAt",
    "stage": "before" | "after",
    "when": 使用者自己講的時間（「下禮拜三」原話，不硬轉日期——猜錯比不猜更傷）
    "symptoms": [...],     # 這次要跟醫生講的：什麼時候開始、什麼情況加重
    "questions": [...],    # 想問醫生的（最多三個，多了他自己也記不住）
    "meds": [...],         # 現在在吃的藥與保健品
    "doctorSaid": [...],   # 看完之後他轉述的醫囑原話（**絕不加工、不解讀**）
    "nextVisit": "",       # 下次回診（他說的原話）
  }
"""
import json
import os
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("MUNEA_CLINIC_VISITS_PATH") or os.path.join(HERE, "clinic_visits.json")

STAGE_BEFORE = "before"
STAGE_AFTER = "after"
MAX_QUESTIONS = 3          # 超過三個他自己在診間也記不住、反而一個都問不出來
VISIT_EXPIRY_DAYS = 45     # 一個半月還沒去看＝這張小抄大概沒用了，不要一直提
_DAY = 86400


def _read():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(data):
    try:
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PATH)
        return True
    except Exception:
        return False


def _visits(person_id, data=None):
    data = data if data is not None else _read()
    return (data.get(person_id) or {}).get("visits") or []


def open_visit(person_id, topic="", when="", now=None):
    """他說要去看醫生 → 開一張小抄。同一個主題已經有未關閉的就沿用，不重複開。"""
    if not person_id:
        return None
    now = now or time.time()
    data = _read()
    visits = _visits(person_id, data)
    for v in visits:
        if v.get("stage") == STAGE_BEFORE and (not topic or v.get("topic") == topic):
            if when and not v.get("when"):
                v["when"] = when
                _write(data)
            return v
    visit = {"id": uuid.uuid4().hex[:12], "topic": topic or "", "when": when or "",
             "stage": STAGE_BEFORE, "createdAt": now,
             "symptoms": [], "questions": [], "meds": [],
             "doctorSaid": [], "nextVisit": ""}
    data.setdefault(person_id, {}).setdefault("visits", []).append(visit)
    _write(data)
    return visit


def add_note(person_id, field, text, visit_id=None):
    """往小抄上加一條。field＝symptoms／questions／meds／doctorSaid。"""
    if not (person_id and text):
        return None
    if field not in ("symptoms", "questions", "meds", "doctorSaid"):
        return None
    data = _read()
    visits = _visits(person_id, data)
    target = None
    for v in visits:
        if visit_id and v["id"] == visit_id:
            target = v
            break
        if not visit_id and v.get("stage") == (STAGE_AFTER if field == "doctorSaid" else STAGE_BEFORE):
            target = v
            break
    if target is None and not visit_id and field == "doctorSaid":
        # 他直接講「醫生說…」但我們沒有那張小抄——照樣接住，不要因為沒開過就丟掉
        for v in visits:
            if v.get("stage") == STAGE_BEFORE:
                target = v
                break
    if target is None:
        return None
    text = str(text).strip()
    if not text or text in target.get(field, []):
        return target
    if field == "questions" and len(target["questions"]) >= MAX_QUESTIONS:
        return target                      # 三個就夠，多了他在診間一個都問不出來
    target.setdefault(field, []).append(text)
    _write(data)
    return target


def mark_visited(person_id, next_visit="", visit_id=None, now=None):
    """他說看完了 → 這張小抄轉成「看診後」，開始接醫生說的話。"""
    if not person_id:
        return None
    data = _read()
    for v in _visits(person_id, data):
        if visit_id and v["id"] != visit_id:
            continue
        if v.get("stage") == STAGE_BEFORE:
            v["stage"] = STAGE_AFTER
            v["visitedAt"] = now or time.time()
            if next_visit:
                v["nextVisit"] = next_visit
            _write(data)
            return v
    return None


def pending_visit(person_id, now=None):
    """還沒去看、而且還沒過期的那張小抄（沒有就回 None）。"""
    if not person_id:
        return None
    now = now or time.time()
    for v in _visits(person_id):
        if v.get("stage") != STAGE_BEFORE:
            continue
        if now - v.get("createdAt", now) > VISIT_EXPIRY_DAYS * _DAY:
            continue
        return v
    return None


def recent_visited(person_id, now=None, within_days=7):
    """剛看完、還沒問到醫生說什麼的那一張——回家那幾天問最準。"""
    if not person_id:
        return None
    now = now or time.time()
    for v in _visits(person_id):
        if v.get("stage") != STAGE_AFTER or v.get("doctorSaid"):
            continue
        if now - v.get("visitedAt", 0) > within_days * _DAY:
            continue
        return v
    return None


def _lines(visit):
    out = []
    if visit.get("symptoms"):
        out.append("已經記下的狀況：" + "、".join(visit["symptoms"]))
    if visit.get("meds"):
        out.append("在吃的藥／保健品：" + "、".join(visit["meds"]))
    if visit.get("questions"):
        out.append("想問醫生的：" + "、".join(visit["questions"]))
    return out


def before_visit_cue(visit):
    """看診前：提醒她把小抄補完，並在快到日子時唸給他聽。"""
    if not visit:
        return ""
    missing = []
    if not visit.get("symptoms"):
        missing.append("這個不舒服是什麼時候開始的、什麼情況會比較嚴重")
    if not visit.get("meds"):
        missing.append("他現在固定在吃的藥跟保健品有哪些")
    if not visit.get("questions"):
        missing.append("這次最想問醫生的一件事")
    body = "；".join(_lines(visit)) or "還是空的"
    hint = ("這一輪可以自然補問其中一項（**一次只問一件**，不要變成問診表）：" + "、".join(missing)
            if missing else
            "小抄已經齊了——快到日子時提一句「我幫你記著了，到時候照著講就好」，讓他安心。")
    return ("（看診前小抄・不是用戶說的話——絕不把這段唸出來。他有一趟要看的診"
            + ("（他說：%s）" % visit["when"] if visit.get("when") else "")
            + "。目前記到的：" + body + "。" + hint
            + " **你在做的是幫他把話整理好，不是替他判斷病情**——不要因為整理小抄就開始給診斷或建議用藥。）")


def after_visit_cue(visit):
    """看診後：問醫生說了什麼，照原話記下來。"""
    if not visit:
        return ""
    return ("（看診後追醫囑・不是用戶說的話——絕不把這段唸出來。他最近去看了醫生"
            + ("（%s）" % visit["topic"] if visit.get("topic") else "")
            + "，還沒跟你講醫生說什麼。這一輪找個自然的時機問一句「醫生後來怎麼說？」，"
            "把他講的**照原話記下來就好**："
            "**絕不解讀醫囑、不評論醫生的判斷對不對、不建議他改藥或加藥**——"
            "他若問「醫生這樣說對嗎」，老實說這你不能判斷，鼓勵他回診時再問清楚或問藥師。"
            "順便問一句下次什麼時候回診，這樣你才提醒得到他。）")


def summary_for(person_id):
    """給 App／家人看的極簡摘要（不含任何判讀）。"""
    visits = _visits(person_id)
    return {"pending": pending_visit(person_id), "recent": recent_visited(person_id),
            "total": len(visits)}


# ── 從他自己的話聽出來（身分與時間都不猜、只聽） ────────────────────────────
BEFORE_WORDS = ("要去看醫生", "要看醫生", "要回診", "掛號", "預約門診", "約了醫生",
                "要去醫院", "要去診所", "下禮拜看", "明天看醫生", "排了檢查")
AFTER_WORDS = ("看完醫生", "看完診", "醫生說", "醫師說", "剛從醫院回來",
               "剛看完", "回診回來", "拿了藥回來")
# 「醫生說」也可能是在轉述很久以前的話——同一句若帶這些字才算剛看完
FRESH_HINT = ("今天", "剛剛", "剛才", "早上", "下午", "剛去", "回來")


def detect_stage(text):
    """回傳 "before" / "after" / None。純字串比對、零模型呼叫。"""
    t = text or ""
    if any(w in t for w in AFTER_WORDS):
        return STAGE_AFTER
    if any(w in t for w in BEFORE_WORDS):
        return STAGE_BEFORE
    return None


def cue_for(person_id, user_text="", now=None):
    """文字線／語音線共用：這一輪該不該帶看診小抄的提示。沒有就回空字串。

    ⚠ 順序有講究：先看他這輪有沒有講到看診（他正在講的事最優先），
    再看有沒有懸著的小抄——不然他明明在講別的，卻被硬拉回看診話題。
    """
    if not person_id:
        return ""
    stage = detect_stage(user_text)
    if stage == STAGE_AFTER:
        v = mark_visited(person_id) or recent_visited(person_id, now)
        return after_visit_cue(v) if v else ""
    if stage == STAGE_BEFORE:
        return before_visit_cue(open_visit(person_id, when="", now=now))
    v = recent_visited(person_id, now)
    if v:
        return after_visit_cue(v)
    v = pending_visit(person_id, now)
    return before_visit_cue(v) if v else ""
