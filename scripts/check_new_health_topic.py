#!/usr/bin/env python3
"""新題入庫前的驗收（2026-08-12 · 全面盤點那批開始用）。

**為什麼要有這支**：新題是分頭寫的，一次進來好幾份。人工看不出來的錯有固定幾種——
L3 保健品少寫每日上限、轉介卡漏掉、編了不該編的電話號碼、觸發字寫成整句
（插一個字就叫不出來，這個坑踩過四次）、卡片編號跟既有的撞號。
這支在合併**之前**擋，不要等進了庫才發現。

用法：
    python scripts/check_new_health_topic.py <新題.json> [<新題.json> ...]
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "engine")

RISK = ("L1", "L2", "L3", "L4", "L5")
MATURITY = ("proven", "emerging", "traditional")
TIME_TO = ("今晚", "一週", "慢養")
TYPES = ("行為調整", "運動", "食補", "保健品", "求助資源", "中醫調理", "用藥", "就醫")
EFFORT = ("低", "中", "高")
AUDIENCE = ("elder", "worker", "teen", "caregiver", "women")
REQUIRED = ("id", "label", "riskLevel", "maturity", "timeToEffect",
            "solutionType", "effortCost", "audience", "say")

# 只准這四支。其他號碼一律不准編——外國用戶被叫去打台灣的號碼是最壞的一種錯。
ALLOWED_NUMBERS = ("119", "1966", "1925", "110")
NUMBER_LIKE = re.compile(r"(?<!\d)(0\d{1,3}[-\s]?\d{6,8}|\d{3,4})(?!\d)")


def load_existing():
    with io.open(os.path.join(ENGINE, "health_solutions.json"), encoding="utf-8") as f:
        topics = json.load(f)["topics"]
    ids = {s["id"] for t in topics.values() for s in t["solutions"]}
    return topics, ids


def check(path, existing_topics, existing_ids, batch=()):
    bad = []
    def err(msg):
        bad.append(msg)

    with io.open(path, encoding="utf-8") as f:
        doc = json.load(f)

    tid = doc.get("topicId") or ""
    if not re.fullmatch(r"TW-EDU-\d\d", tid):
        err(f"題號格式不對：{tid!r}")
    if tid in existing_topics:
        err(f"題號 {tid} 已經有人用了")
    if not doc.get("title"):
        err("沒有標題")

    kws = doc.get("keywords") or []
    if len(kws) < 6:
        err(f"觸發字只有 {len(kws)} 個，太少（真人的講法很散，建議 8 個以上）")
    for kw in kws:
        if len(kw) >= 8:
            err(f"觸發字寫得像整句：{kw!r}——插一個字就叫不出來，要用詞根")

    sols = doc.get("solutions") or []
    if len(sols) < 8:
        err(f"只有 {len(sols)} 張卡，少於 8 張")

    seen, refers = set(), []
    actions = 0
    for s in sols:
        sid = s.get("id", "(沒有 id)")
        for k in REQUIRED:
            if not s.get(k):
                err(f"{sid} 缺 {k}")
        if sid in seen:
            err(f"{sid} 在這份裡重複")
        if sid in existing_ids:
            err(f"{sid} 跟既有題目的卡撞號")
        seen.add(sid)

        for field, allowed in (("riskLevel", RISK), ("maturity", MATURITY),
                               ("timeToEffect", TIME_TO), ("solutionType", TYPES),
                               ("effortCost", EFFORT)):
            if s.get(field) and s[field] not in allowed:
                err(f"{sid} 的 {field}={s[field]!r} 不在允許值裡")
        for a in s.get("audience") or []:
            if a not in AUDIENCE:
                err(f"{sid} 的 audience 有不認得的 {a!r}")

        say = s.get("say") or ""
        # L4 不是 blocked ＝ 這張卡永遠不會被講出來（挑選層會整條剔除）
        if s.get("riskLevel") == "L4" and not s.get("blocked"):
            err(f"{sid} 是 L4 卻沒標 blocked——這種卡生下來就是死的，永遠端不出去")
        if s.get("blocked") and not s.get("askedFor"):
            err(f"{sid} 是 blocked 卻沒有 askedFor——他點名了也叫不出來")
        if s.get("riskLevel") == "L3":
            for k in ("dailyCap", "verifiedAt"):
                if not s.get(k):
                    err(f"{sid} 是保健品（L3）卻缺 {k}——三件事少一件就不合格")
            # 「誰要小心」可以寫在禁忌（完全不該用）或 warnsAbout（這張就是警告他的），
            # 兩個欄位的行為不同，但都算把那一件事講清楚了。
            if not (s.get("contraindications") or s.get("warnsAbout")):
                err(f"{sid} 是保健品（L3）卻沒寫誰要小心")
            if not (s.get("evidence") or {}).get("finding"):
                err(f"{sid} 是保健品（L3）卻沒寫證據強度")
        if s.get("riskLevel") == "L5":
            refers.append(sid)
            if not s.get("escalateWhen"):
                err(f"{sid} 是轉介卡卻沒列紅旗")
        for w in s.get("askedFor") or []:
            # 2026-08-13：長度上限是為了擋「寫成一整句」，但英文成分名（metformin）
            # 本來就長、又是使用者真的會唸出來的字。純英數的點名字放寬到 16。
            limit = 16 if re.fullmatch(r"[A-Za-z0-9 .\-]+", w) else 8
            if len(w) >= limit:
                err(f"{sid} 的點名字寫得像整句：{w!r}")

        # 電話號碼：只准那四支
        for m in NUMBER_LIKE.finditer(say):
            tok = m.group(1)
            if tok in ALLOWED_NUMBERS:
                continue
            if len(tok) <= 4 and not tok.startswith("0"):
                continue          # 純數量（30 天、200 cc）不算號碼
            err(f"{sid} 出現疑似自編的電話：{tok}（只准 {'／'.join(ALLOWED_NUMBERS)}）")

        if s.get("riskLevel") not in ("L4", "L5") and not s.get("blocked"):
            if re.search(r"[0-9一二三四五六七八九十兩半]+\s*(份|杯|顆|克|cc|分鐘|次|天|秒)"
                         r"|每天|每餐|每週|改成|換成|先從|打\s*1966", say):
                actions += 1

    if len(refers) != 1:
        err(f"轉介卡要剛好一張，現在有 {len(refers)} 張：{refers}")
    if actions < 4:
        err(f"『今天做得到的事』只有 {actions} 張，規格要求至少 4 張")

    for r in doc.get("relatedTopics") or []:
        if r.get("topicId") not in existing_topics and r.get("topicId") not in batch:
            err(f"relatedTopics 指到不存在的題：{r.get('topicId')}")

    return tid, len(sols), actions, bad


def main(paths):
    existing_topics, existing_ids = load_existing()
    # 同一批一起進來的題，彼此互指是正常的（長照題會連到照顧技巧題）——
    # 只拿「既有庫」去比會誤判成指到不存在的題。
    batch = set()
    for p in paths:
        with io.open(p, encoding="utf-8") as f:
            batch.add(json.load(f).get("topicId"))
    total_bad = 0
    for p in paths:
        tid, n, actions, bad = check(p, existing_topics, existing_ids, batch)
        head = f"{os.path.basename(p)}　{tid}　{n} 張卡（動作 {actions}）"
        if bad:
            total_bad += len(bad)
            print(f"❌ {head}")
            for b in bad:
                print("     ·", b)
        else:
            print(f"✅ {head}")
    print()
    print("全部通過，可以合併" if not total_bad else f"共 {total_bad} 個問題，修完再合併")
    return 1 if total_bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
