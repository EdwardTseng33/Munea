"""健康脈絡：把這個人的身體數據，翻成她心裡知道的「事實」。

為什麼要有這支：在這之前，健康數據的水管是「長輩手機 → 雲端 → 家人畫面」，
AI 站在水管外面——她的說明書每一輪都告訴她「你看得到健康告警」，但實際上
一個數字都到不了她面前。結果就是她只能講「多喝水早點睡」這種對誰都一樣的話，
或者更糟：憑空編一句「你今天血壓有點高喔」。這支就是把她接進那根水管。

三條鐵律（延續 perception_engine 觀察層既有規矩，不是新發明的）：

1. 跟自己比、不跟量表比。沒有正常值、沒有分數、沒有紅黃綠燈。
   「今天 158/92，你這兩週大多在 130/80 上下」＝事實；「你血壓偏高」＝判定，不准。
2. 講事實、不講判定。判定是醫生的事。這支只負責把數字擺到她面前，
   還有「跟他自己平常比差多少」——要不要開口、怎麼講，是她的說明書在管。
3. 檔位 2「知道但不多嘴」（2026-07-17 Edward 拍板）：她心裡知道、他問就答、
   講話可以自然帶到；但不主動報數字、不主動報警。告警照舊走家人那條路。

沒資料就誠實回空——上游會據此告訴她「你不知道，不准編」。這條比什麼都重要：
一個以為自己看得到數據的模型，會很樂意生一個數據出來。
"""

# 每項數據的「雜訊地板」：低於這個差距就當量測誤差、不值得她知道。
# 這不是醫學閾值、跟正常值無關——純粹是「今天跟他自己平常比，差到值不值得注意」。
# 判定高低是醫生的事，這裡只決定要不要把這條擺到她面前。
NOISE_FLOOR = {
    "bpSys": 12,        # mmHg
    "bpDia": 8,
    "hr": 10,           # 次/分
    "spo2": 2,          # %
    "sleepHours": 1.0,  # 小時
    "steps": 0.4,       # 相對值：差 40% 以上才算（步數天天差很大）
}

FIELD_LABEL = {
    "bpSys": "血壓",
    "bpDia": "血壓",
    "hr": "心跳",
    "spo2": "血氧",
    "sleepHours": "睡眠",
    "steps": "活動量",
}

BASELINE_WINDOW = 14   # 個人基準線＝往前 14 天
BASELINE_SKIP = 3      # 排除最近 3 天（那是「最近」、不是「平常」）
RECENT_WINDOW = 3      # 「最近」＝最近 3 天
MIN_BASELINE_DAYS = 4  # 少於這天數就沒有「平常」可言、不比


def _sorted_days(log):
    """健康帳本 {'2026-07-17': {...}, ...} → 由舊到新的日期清單。"""
    if not isinstance(log, dict):
        return []
    return sorted(d for d in log.keys() if isinstance(d, str) and len(d) == 10)


def _values(log, days, field):
    out = []
    for d in days:
        row = log.get(d)
        if not isinstance(row, dict):
            continue
        v = row.get(field)
        if isinstance(v, (int, float)) and v > 0:
            out.append(float(v))
    return out


def _avg(values):
    return round(sum(values) / len(values), 1) if values else None


def baseline_and_recent(log, field):
    """回 (平常, 最近)——都是他自己的數字，不是任何量表。

    平常＝往前 14 天平均（排掉最近 3 天，那是「最近」不是「平常」）
    最近＝最近 3 天平均
    資料不夠就回 None，不硬湊。
    """
    days = _sorted_days(log)
    if not days:
        return None, None
    base_days = days[:-BASELINE_SKIP] if len(days) > BASELINE_SKIP else []
    base_values = _values(log, base_days[-BASELINE_WINDOW:], field)
    recent_values = _values(log, days[-RECENT_WINDOW:], field)
    baseline = _avg(base_values) if len(base_values) >= MIN_BASELINE_DAYS else None
    return baseline, _avg(recent_values)


def _is_notable(field, latest, baseline):
    """跟他自己平常比，差到值得她知道嗎？（雜訊地板、不是醫學判定）"""
    if latest is None or baseline is None:
        return False
    floor = NOISE_FLOOR.get(field)
    if floor is None:
        return False
    if field == "steps":  # 步數用相對值：天天差很大、絕對值沒意義
        return baseline > 0 and abs(latest - baseline) / baseline >= floor
    return abs(latest - baseline) >= floor


def _fmt(value, field):
    if value is None:
        return ""
    if field == "sleepHours":
        return f"{value:.1f} 小時"
    if field == "steps":
        return f"{int(round(value))} 步"
    if field == "spo2":
        return f"{int(round(value))}%"
    if field == "hr":
        return f"{int(round(value))} 下"
    return str(int(round(value)))


def _latest_day_with(log, field):
    for d in reversed(_sorted_days(log)):
        row = log.get(d)
        if isinstance(row, dict) and isinstance(row.get(field), (int, float)) and row[field] > 0:
            return d, float(row[field])
    return None, None


def summarize_vitals(log, today=None):
    """身體數據 → 她心裡知道的事實清單。

    回 {"facts": [...一句一條...], "notable": [...跟平常不一樣的欄位...]}
    每一條都是「數字＋他自己平常的數字」，沒有一句是判定。
    """
    facts, notable = [], []
    if not isinstance(log, dict) or not log:
        return {"facts": facts, "notable": notable}

    # 血壓兩個數字要一起講、拆開沒意義
    bp_day, sys_v = _latest_day_with(log, "bpSys")
    _, dia_v = _latest_day_with(log, "bpDia")
    if sys_v and dia_v:
        sys_base, _ = baseline_and_recent(log, "bpSys")
        dia_base, _ = baseline_and_recent(log, "bpDia")
        line = f"血壓：最近一次量到 {int(sys_v)}/{int(dia_v)}"
        if bp_day and today and bp_day != str(today)[:10]:
            line += f"（{bp_day} 量的，今天還沒量）"
        if sys_base and dia_base:
            line += f"；他自己平常大概在 {int(sys_base)}/{int(dia_base)}"
        facts.append(line)
        if _is_notable("bpSys", sys_v, sys_base) or _is_notable("bpDia", dia_v, dia_base):
            notable.append("bpSys")

    for field in ("hr", "spo2", "sleepHours", "steps"):
        day, latest = _latest_day_with(log, field)
        if latest is None:
            continue
        baseline, _ = baseline_and_recent(log, field)
        label = FIELD_LABEL[field]
        line = f"{label}：最近一次 {_fmt(latest, field)}"
        if day and today and day != str(today)[:10]:
            line += f"（{day}）"
        if baseline:
            line += f"；他自己平常大概 {_fmt(baseline, field)}"
        facts.append(line)
        if _is_notable(field, latest, baseline):
            notable.append(field)

    return {"facts": facts, "notable": notable}


def summarize_medication(doses, today):
    """今天的藥吃了沒。

    doses＝medication_dose_events 的當日紀錄（status: scheduled/taken/snoozed/skipped/missed）
    回一句人話，或空字串（今天沒排藥就不用講）。
    """
    today = str(today)[:10]
    rows = [d for d in (doses or []) if (d or {}).get("scheduledDate") == today]
    if not rows:
        return ""
    taken = sum(1 for d in rows if d.get("status") == "taken")
    total = len(rows)
    pending = [d for d in rows if d.get("status") in ("scheduled", "snoozed")]
    missed = [d for d in rows if d.get("status") in ("missed", "skipped")]
    line = f"今天的藥：排了 {total} 次，吃了 {taken} 次"
    if pending:
        labels = [str(d.get("slotLabel") or "").strip() for d in pending if d.get("slotLabel")]
        line += f"；還有 {len(pending)} 次沒到時間" + (f"（{'、'.join(labels[:3])}）" if labels else "")
    if missed:
        line += f"；有 {len(missed)} 次沒吃"
    return line


def build(vitals_entry=None, doses=None, mood_trend=None, today=None):
    """把三邊資料合成一份「她心裡知道的身體狀況」。

    vitals_entry＝家庭帳本裡這個人的那一格（含 365 天健康帳本 log）
    doses＝今天的用藥紀錄
    mood_trend＝wellbeing_trend_response 的結果（心情那條已經算好了、直接用）
    回 {"facts": [...], "notable": [...], "hasData": bool}
    沒資料就誠實回空——上游會據此告訴她「你不知道」。
    """
    facts, notable = [], []
    entry = vitals_entry if isinstance(vitals_entry, dict) else {}
    log = entry.get("log") if isinstance(entry.get("log"), dict) else {}

    vitals = summarize_vitals(log, today=today)
    facts.extend(vitals["facts"])
    notable.extend(vitals["notable"])

    med_line = summarize_medication(doses, today)
    if med_line:
        facts.append(med_line)

    # 心情：不重算，直接用已經算好的那條（同一套「跟自己比」的算法）。
    # 給她的是「觀察」不是數字——心情系統本來就有鐵律「絕無 0-100 分數、絕無臨床字眼」，
    # 而且丟一個「2.4」給她，她也不知道那是什麼意思、更講不出人話。
    trend = mood_trend if isinstance(mood_trend, dict) else {}
    baseline, recent = trend.get("baseline"), trend.get("recent")
    if baseline and recent:
        if trend.get("gentleConcern"):
            facts.append("心情：這幾天聊天比他自己平常安靜一些（跟他自己比，不代表有事）")
            notable.append("mood")
        else:
            facts.append("心情：這幾天跟他自己平常差不多")

    return {"facts": facts, "notable": notable, "hasData": bool(facts)}


def instruction_block(context):
    """把事實清單寫成她說明書裡的一段。

    檔位 2「知道但不多嘴」：資料給她、但明令不主動報數字、不主動報警。
    沒資料時這段更重要——它是那道圍籬，明講「你就是不知道、不准編」。
    """
    ctx = context if isinstance(context, dict) else {}
    facts = ctx.get("facts") or []
    if not facts:
        return (
            "（他的身體狀況：**你現在什麼都看不到**——他的血壓、心跳、血氧、睡眠、"
            "吃藥紀錄都沒有傳到你這裡。所以**絕對不要講任何他的健康數字、不要說「你今天血壓有點高」"
            "「你最近睡不好喔」這種你根本不知道的話**（講了就是捏造，長輩會當真、傷害信任）。"
            "他自己告訴你的、或你們聊過的，才可以接話。想知道就問他。）"
        )
    body = "\n".join(f"- {f}" for f in facts)
    note = ""
    if ctx.get("notable"):
        note = (
            "\n上面有幾項跟他自己平常不太一樣。**這不代表有問題**——你不是醫生、不做判斷。"
            "如果話題自然聊到，可以順著關心一句（像「這幾天睡得比較少喔？」）；"
            "但**不要主動報數字、不要說得像在警告他**。"
        )
    return (
        "（他的身體狀況——**這些是真的、是他自己的數字**，你心裡知道就好：\n"
        f"{body}{note}\n"
        "**怎麼用**：他問就照實講；聊天聊到相關的自然帶到。"
        "但**不要一開口就報數字、不要每次都提、不要主動報警**——"
        "身體數據異常有家人在看，那不是你的活。"
        "**只講上面有的**，上面沒有的就是你不知道，不准推測、不准補一個數字。"
        "還有：這些是事實不是診斷，**絕不說「偏高」「不正常」「有問題」**這種評判的話，"
        "那是醫生的事。）"
    )
