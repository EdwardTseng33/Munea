# -*- coding: utf-8 -*-
"""週關懷摘要：把一個人這一週「跟沐寧之間發生的事」排成一頁事實（補助案 C2 第一塊，2026-10-13）。

為什麼要有這支：
機構窗口（護理師／社工）一個人顧幾十個長輩，不可能每通電話都聽；家人也一樣。
他們要的不是分數，是「這週他跟沐寧講了幾次話、心情走勢、有沒有講到身體、守護腦有沒有亮燈、
有幾天沒聯絡」——事實排好，判斷留給人。

繼承 visit_summary 的鐵律、一個字不改：
1. 跟自己比、不跟量表比——心情只用 App 本來就在用的 1–5 天氣等級，沒有分數、沒有紅黃綠燈。
2. 講事實、不講判定——「這週最低的一天他說：…」可以；「他可能憂鬱」不行。
3. 沒資料就誠實回空，不編；每一段都帶 source（本人口述／機器觀察／系統紀錄）。
4. 只並列、不連線——心情掉、身體不舒服同一天出現，只能並排，不可寫「可能因為」。
5. 不呼叫 AI：全程純程式組裝，一千份跟一份同價；讀的是記憶層已經萃取好的東西。

異常偵測（detect_anomalies）只做「規則、可解釋、可關」的三條，每條都附「為什麼亮」：
  mood_drop   心情連續 3 天 ≤ 2，或最近 3 天平均比自己前 14 天掉 2 級以上
  no_contact  連續 N 天沒通話（N 由機構／家人設定，預設 3）
  guardian    守護腦這週亮過 high／critical（即時通知另外走，這裡是週彙整）
準確率（≥ 80%）的分子分母來自窗口對每一筆的標記（已處理／誤報／觀察中），不是這裡算的。
"""
import datetime as _dt

DEFAULT_DAYS = 7
BASELINE_DAYS = 14
NO_CONTACT_DAYS_DEFAULT = 3
LOW_MOOD_LEVEL = 2
LOW_MOOD_STREAK = 3
MOOD_DROP_LEVELS = 2.0
HIGH_LEVELS = ("high", "critical", "crisis")

# 這些字一出現就是在「判定」或「連線」，摘要文字層禁用（測試會掃）
FORBIDDEN_WORDS = ("可能因為", "導致", "造成", "引起", "相關", "分數", "正常值", "診斷", "憂鬱症", "失智")


def _parse_date(value):
    if not value:
        return None
    text = str(value)[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


def period_bounds(days=DEFAULT_DAYS, today=None):
    """回 (start, end)，含頭含尾；today 不給就用本機今天。"""
    end = _parse_date(today) or _dt.date.today()
    days = max(1, min(31, int(days or DEFAULT_DAYS)))
    start = end - _dt.timedelta(days=days - 1)
    return start, end


def _in(d, start, end):
    return d is not None and start <= d <= end


def summarize_mood(signals, start, end, baseline_days=BASELINE_DAYS):
    """心情：每日聚合（同一天多次取平均、心情以最後一次為主）＋個人基準線（期間之前 14 天）。"""
    by_day = {}
    base_rows = []
    base_start = start - _dt.timedelta(days=baseline_days)
    for s in signals or []:
        d = _parse_date(s.get("date") or s.get("createdAt"))
        if d is None:
            continue
        if _in(d, start, end):
            by_day.setdefault(d, []).append(s)
        elif _in(d, base_start, start - _dt.timedelta(days=1)):
            base_rows.append(s)
    daily = []
    concerns, positives = [], []
    for d in sorted(by_day):
        rows = by_day[d]
        levels = [r.get("level") for r in rows if isinstance(r.get("level"), (int, float))]
        latest = rows[-1]
        daily.append({
            "date": d.isoformat(),
            "level": round(sum(levels) / len(levels), 1) if levels else None,
            "mood": latest.get("mood"),
            "chats": len(rows),
            "said": latest.get("wordObs") or latest.get("chatObs") or "",
        })
        for r in rows:
            for c in r.get("concerns") or []:
                if c and c not in concerns:
                    concerns.append(c)
            for p in r.get("positives") or []:
                if p and p not in positives:
                    positives.append(p)
    levels_week = [x["level"] for x in daily if x["level"] is not None]
    base_levels = [r.get("level") for r in base_rows if isinstance(r.get("level"), (int, float))]
    lowest = min((x for x in daily if x["level"] is not None), key=lambda x: x["level"], default=None)
    return {
        "source": "機器觀察（每次通話後由沐寧記錄的心情天氣，1–5 級）",
        "daysWithChat": len(daily),
        "daily": daily,
        "weekAverage": round(sum(levels_week) / len(levels_week), 1) if levels_week else None,
        "baselineAverage": round(sum(base_levels) / len(base_levels), 1) if base_levels else None,
        "baselineDays": baseline_days,
        "lowestDay": lowest,
        "concerns": concerns[:10],
        "positives": positives[:10],
        "empty": not daily,
    }


def summarize_contact(summaries, start, end, today=None):
    """聯絡：這週通了幾次話、哪幾天、最長幾天沒聯絡、最後一次是哪天。通話來源＝每通電話結束後的對話摘要紀錄。"""
    days = set()
    calls = 0
    last = None
    for s in summaries or []:
        if s.get("deletedAt"):
            continue
        d = _parse_date(s.get("createdAt") or s.get("date"))
        if d is None:
            continue
        if last is None or d > last:
            last = d
        if _in(d, start, end):
            calls += 1
            days.add(d)
    # 最長空檔：期間內逐日看，沒通話的連續天數
    longest = 0
    streak = 0
    cursor = start
    while cursor <= end:
        if cursor in days:
            streak = 0
        else:
            streak += 1
            longest = max(longest, streak)
        cursor += _dt.timedelta(days=1)
    ref = _parse_date(today) or end
    since_last = (ref - last).days if last else None
    return {
        "source": "系統紀錄（每通電話結束後的摘要）",
        "calls": calls,
        "daysWithCall": sorted(d.isoformat() for d in days),
        "longestGapDays": longest,
        "lastCallDate": last.isoformat() if last else None,
        "daysSinceLastCall": since_last,
        "empty": calls == 0,
    }


def summarize_safety(events, start, end):
    """守護腦：這週亮過幾次燈、哪一級、哪一類。不放原句（那是即時通知的事，週摘要只放次數與類別）。"""
    items = []
    counts = {}
    for e in events or []:
        d = _parse_date(e.get("eventTime") or e.get("createdAt"))
        if not _in(d, start, end):
            continue
        level = e.get("riskLevel") or e.get("level") or "unknown"
        if level in ("none", "low"):
            continue
        cats = e.get("categories") or []
        if isinstance(cats, str):
            cats = [cats]
        counts[level] = counts.get(level, 0) + 1
        items.append({"time": e.get("eventTime") or e.get("createdAt"), "level": level, "categories": list(cats)})
    items.sort(key=lambda x: x["time"] or "")
    return {
        "source": "系統紀錄（守護腦風險評估）",
        "counts": counts,
        "highOrCritical": sum(v for k, v in counts.items() if k in HIGH_LEVELS),
        "items": items,
        "empty": not items,
    }


def build_person_week(person, signals=None, summaries=None, safety_events=None, vitals_text=None,
                      today=None, days=DEFAULT_DAYS):
    """一個人的一週。person 至少要有 id；name／nick 有就帶（顯示用）。vitals_text 是 health_context 組好的事實句（可無）。"""
    start, end = period_bounds(days, today)
    mood = summarize_mood(signals, start, end)
    contact = summarize_contact(summaries, start, end, today=today)
    safety = summarize_safety(safety_events, start, end)
    return {
        "personId": (person or {}).get("id") or (person or {}).get("personId"),
        "displayName": (person or {}).get("nick") or (person or {}).get("name") or "",
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "contact": contact,
        "mood": mood,
        "spokenHealth": {
            "source": "本人口述（通話中自己說的，由記憶層萃取；可能記錯、不是臨床事實）",
            "items": mood["concerns"],
            "empty": not mood["concerns"],
        },
        "measured": {
            "source": "機器量測（在家量測／健康 App）",
            "text": vitals_text or "",
            "empty": not vitals_text,
        },
        "safety": safety,
        "honesty": {
            "allEmpty": mood["empty"] and contact["empty"] and safety["empty"] and not vitals_text,
            "note": "每一段都標了來源；沒資料的段落寫「這週沒有紀錄」，不是「他沒事」。",
        },
    }


def detect_anomalies(week, settings=None):
    """三條規則、每條附「為什麼亮」。settings: {noContactDays, lowMoodLevel, lowMoodStreak, moodDropLevels}."""
    settings = settings or {}
    n_days = int(settings.get("noContactDays") or NO_CONTACT_DAYS_DEFAULT)
    low_level = float(settings.get("lowMoodLevel") or LOW_MOOD_LEVEL)
    low_streak = int(settings.get("lowMoodStreak") or LOW_MOOD_STREAK)
    drop = float(settings.get("moodDropLevels") or MOOD_DROP_LEVELS)
    out = []

    # mood_drop：連續 N 天 ≤ 2
    daily = [x for x in week["mood"]["daily"] if x["level"] is not None]
    streak = 0
    streak_days = []
    for x in daily:
        if x["level"] <= low_level:
            streak += 1
            streak_days.append(x["date"])
            if streak >= low_streak:
                out.append({
                    "type": "mood_drop",
                    "when": x["date"],
                    "fact": "心情連續 %d 天在 %d 級以下（%s）。" % (streak, int(low_level), "、".join(streak_days[-streak:])),
                    "lastSaid": x["said"],
                    "suggestion": "打個電話問候；這是觀察，不是判定。",
                })
                break
        else:
            streak = 0
            streak_days = []
    # mood_drop：比自己前 14 天掉 2 級以上（最近 3 天平均）
    base = week["mood"]["baselineAverage"]
    recent = [x["level"] for x in daily[-3:]]
    if base is not None and recent:
        recent_avg = sum(recent) / len(recent)
        if base - recent_avg >= drop and not any(a["type"] == "mood_drop" for a in out):
            out.append({
                "type": "mood_drop",
                "when": daily[-1]["date"],
                "fact": "最近 3 天心情平均 %.1f 級，比自己前 %d 天的 %.1f 級低了 %.1f 級。" % (recent_avg, week["mood"]["baselineDays"], base, base - recent_avg),
                "lastSaid": daily[-1]["said"],
                "suggestion": "打個電話問候；這是跟他自己比，不是跟量表比。",
            })

    # no_contact：看「現在」——到今天已經 ≥ N 天沒通話、或根本沒有通話紀錄。
    # 期間內曾經空了幾天但後來又聯絡上的，只當事實寫在【聯絡】段（最長 N 天沒聯絡），不亮燈。
    c = week["contact"]
    since = c.get("daysSinceLastCall")
    if (since is not None and since >= n_days) or (c["empty"] and since is None):
        if c["lastCallDate"]:
            fact = "最後一次通話是 %s，到 %s 已經 %s 天沒聯絡（設定：%d 天提醒）。" % (
                c["lastCallDate"], week["period"]["end"], since if since is not None else c["longestGapDays"], n_days)
        else:
            fact = "這段期間沒有任何通話紀錄（設定：%d 天提醒）。" % n_days
        out.append({"type": "no_contact", "when": week["period"]["end"], "fact": fact, "suggestion": "確認一下人在不在、電話通不通。"})

    # guardian：這週亮過 high／critical
    s = week["safety"]
    if s["highOrCritical"]:
        levels = "、".join("%s×%d" % (k, v) for k, v in sorted(s["counts"].items()) if k in HIGH_LEVELS)
        out.append({
            "type": "guardian",
            "when": s["items"][-1]["time"] if s["items"] else week["period"]["end"],
            "fact": "守護腦這週亮了 %d 次高風險燈（%s）；即時通知已另外送出，這裡是週彙整。" % (s["highOrCritical"], levels),
            "suggestion": "看即時通知裡的原句與處理紀錄。",
        })
    return out


def render_text(week, anomalies=None):
    """純文字版（Email／PDF 的底稿）。每段都先寫來源，沒資料寫「這週沒有紀錄」。"""
    p = week["period"]
    name = week.get("displayName") or week.get("personId") or ""
    lines = ["%s｜%s ～ %s 週關懷摘要" % (name, p["start"], p["end"]), ""]
    c = week["contact"]
    lines.append("【聯絡】來源：%s" % c["source"])
    if c["empty"]:
        lines.append("  這週沒有通話紀錄。")
    else:
        lines.append("  通話 %d 次（%s）；最長 %d 天沒聯絡；最後一次 %s。" % (
            c["calls"], "、".join(c["daysWithCall"]), c["longestGapDays"], c["lastCallDate"]))
    m = week["mood"]
    lines.append("【心情】來源：%s" % m["source"])
    if m["empty"]:
        lines.append("  這週沒有紀錄。")
    else:
        lines.append("  有紀錄 %d 天，這週平均 %s 級；自己前 %d 天平均 %s 級。" % (
            m["daysWithChat"], m["weekAverage"], m["baselineDays"], m["baselineAverage"] if m["baselineAverage"] is not None else "（沒有可比的紀錄）"))
        if m["lowestDay"]:
            lines.append("  最低的一天 %s（%s 級）他說：%s" % (m["lowestDay"]["date"], m["lowestDay"]["level"], m["lowestDay"]["said"] or "（沒有留下一句話）"))
        if m["positives"]:
            lines.append("  開心的事：%s" % "；".join(m["positives"]))
    h = week["spokenHealth"]
    lines.append("【身體・本人口述】來源：%s" % h["source"])
    lines.append("  " + ("；".join(h["items"]) if h["items"] else "這週沒有紀錄。"))
    v = week["measured"]
    lines.append("【身體・量測】來源：%s" % v["source"])
    lines.append("  " + (v["text"] if v["text"] else (v.get("note") or "這週沒有紀錄。")))
    s = week["safety"]
    lines.append("【守護腦】來源：%s" % s["source"])
    if s["empty"]:
        lines.append("  這週沒有亮燈。")
    else:
        lines.append("  亮燈 %d 次：%s" % (len(s["items"]), "、".join("%s %s" % (x["level"], "/".join(x["categories"])) for x in s["items"])))
    if anomalies:
        lines.append("【要看一下】")
        for a in anomalies:
            lines.append("  · %s %s" % (a["fact"], a["suggestion"]))
    lines.append("")
    lines.append("說明：以上是事實排列，不是判定；心情等級是跟他自己比，不是跟任何量表比。")
    return "\n".join(lines)


def build_org_report(person_weeks, anomalies_by_person=None):
    """一個機構一份：每個人一段＋總表。不做排名、不做分數。"""
    anomalies_by_person = anomalies_by_person or {}
    people = []
    totals = {"people": 0, "withAnomaly": 0, "noContact": 0, "moodDrop": 0, "guardian": 0, "calls": 0}
    for w in person_weeks:
        a = anomalies_by_person.get(w["personId"], [])
        people.append({"week": w, "anomalies": a})
        totals["people"] += 1
        totals["calls"] += w["contact"]["calls"]
        if a:
            totals["withAnomaly"] += 1
        for x in a:
            key = {"no_contact": "noContact", "mood_drop": "moodDrop", "guardian": "guardian"}.get(x["type"])
            if key:
                totals[key] += 1
    period = person_weeks[0]["period"] if person_weeks else None
    return {"period": period, "totals": totals, "people": people}
