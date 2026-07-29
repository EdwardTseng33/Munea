#!/usr/bin/env python3
"""效果飛輪（2026-07-29 · Edward「推進優化」後開工）。

**為什麼一定要有這層**：21 題衛教劇本裡每一題都寫了「3-5 天後回訪：這幾天有沒有比較好睡？」，
但程式裡一行都沒實作。所以她推薦完就結束了——不知道自己講過什麼、不知道他有沒有去做、
更不知道有沒有效。同一個人問第二次，拿到的還是一模一樣的三個方案。

「陪伴即追蹤」是這個產品的護城河，但**追蹤這件事在程式上一直沒發生**。這支補上：

    推薦 → 記下來 → 到期主動問 → 記效果 → 下次挑選時用得上

飛輪的意義：**每一次對話都讓她更懂這個人**。有效的下次先講、沒效的不要再端出來、
還沒試的可以再輕輕提一次——這是複利，不是一次性的優化。

設計紀律：
- 純資料層，不呼叫模型、不連網（跟 health_kb／health_selector 同一種東西）。
- 回訪日按「多快有感」算：今晚檔 3 天、一週檔 7 天、慢養檔 14 天——太早問他還沒感覺、
  太晚問他已經忘了。
- 只記自己的推薦與他的回答，不記任何醫療判斷。
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.environ.get("MUNEA_HEALTH_FOLLOWUP_PATH") or os.path.join(HERE, "health_followups.json")

DAY = 86400
# 多快有感 → 幾天後回訪剛好（太早問他沒感覺、太晚問他忘了）
FOLLOWUP_DAYS = {"今晚": 3, "一週": 7, "慢養": 14}
DEFAULT_FOLLOWUP_DAYS = 7
MAX_RECORDS_PER_PERSON = 200      # 防爆：只留最近的
FOLLOWUP_EXPIRY_DAYS = 30         # 超過一個月沒問到就別問了（他早忘了，硬問很怪）

OUTCOME_WORKED = "worked"
OUTCOME_NO_EFFECT = "no_effect"
OUTCOME_NOT_TRIED = "not_tried"
VALID_OUTCOMES = (OUTCOME_WORKED, OUTCOME_NO_EFFECT, OUTCOME_NOT_TRIED)


def _read():
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write(data):
    tmp = f"{STORE_PATH}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, STORE_PATH)


def record_recommendation(person_id, topic_id, solutions, now=None):
    """她推薦了什麼，記下來。solutions＝health_selector 挑出來的那幾個方案（dict 清單）。"""
    if not person_id or not topic_id or not solutions:
        return []
    now = now or time.time()
    store = _read()
    rows = store.setdefault(str(person_id), [])
    existing = {r["solutionId"] for r in rows if not r.get("outcome")}
    added = []
    for s in solutions:
        sid = s.get("id")
        if not sid or sid in existing:
            continue          # 同一個方案還沒問到結果就別重複記
        days = FOLLOWUP_DAYS.get(s.get("timeToEffect"), DEFAULT_FOLLOWUP_DAYS)
        row = {
            "topicId": topic_id, "solutionId": sid, "label": s.get("label") or sid,
            "recommendedAt": now, "dueAt": now + days * DAY, "outcome": None,
        }
        rows.append(row)
        added.append(row)
    if len(rows) > MAX_RECORDS_PER_PERSON:
        del rows[:-MAX_RECORDS_PER_PERSON]
    _write(store)
    return added


def due_followups(person_id, now=None, limit=1):
    """到期該問的（最舊的先問）。超過一個月的直接跳過——他早忘了、硬問很怪。"""
    now = now or time.time()
    rows = _read().get(str(person_id)) or []
    due = [r for r in rows
           if not r.get("outcome")
           and r.get("dueAt", 0) <= now
           and (now - r.get("recommendedAt", now)) <= FOLLOWUP_EXPIRY_DAYS * DAY]
    due.sort(key=lambda r: r.get("dueAt", 0))
    return due[:limit]


def record_outcome(person_id, solution_id, outcome, now=None):
    """他回答了——有效／沒效／還沒試。記進去，下次挑選就會不一樣。"""
    if outcome not in VALID_OUTCOMES:
        return None
    store = _read()
    rows = store.get(str(person_id)) or []
    for r in reversed(rows):          # 最近一筆優先
        if r.get("solutionId") == solution_id and not r.get("outcome"):
            r["outcome"] = outcome
            r["answeredAt"] = now or time.time()
            _write(store)
            return r
    return None


def outcomes_for(person_id):
    """這個人試過什麼、結果如何 → {solutionId: outcome}。給挑選層調整排序用。"""
    result = {}
    for r in _read().get(str(person_id)) or []:
        if r.get("outcome"):
            result[r["solutionId"]] = r["outcome"]
    return result


def followup_cue(row):
    """到期回訪要問的那句話（給主動開口／說明書用）。自然、不像問卷。"""
    label = row.get("label") or "上次聊的方法"
    return (
        f"（回訪提示、不是用戶說的話——絕不把這段唸出來：{int((time.time() - row.get('recommendedAt', 0)) // DAY)} 天前"
        f"你建議過他「{label}」。這一輪找個自然的時機關心一下後來怎麼樣了，"
        f"像「上次講的那個，你有試試看嗎？有沒有比較好一點？」——問一句就好，"
        f"他說沒試也別催、別說教；他說有效就替他高興、他說沒效就說「那我們換個方式試試」。）"
    )
