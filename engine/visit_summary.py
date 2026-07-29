"""就診摘要：把這個人這段期間發生的事，組成一頁帶去給醫生看的東西。

為什麼要有這支（M1 · F2/F3）：
門診只有三分鐘。醫生問「最近怎麼樣」，長輩答「還好」——真正的東西沒講到。
而健保雲端藥歷醫生本來就看得到，再印一次＝零價值。**沐寧的獨家是雲端藥歷裡沒有的**：
症狀時間軸（「上禮拜開始走幾步就喘」）、在家量測、藥實際有沒有吃。
這支就是把那些東西按時間排好，讓醫生三十秒看完。

繼承 health_context 的三條鐵律，一個字不改（那支是同一個資料源的上游）：
1. **跟自己比、不跟量表比**——沒有正常值、沒有分數、沒有紅黃綠燈。
2. **講事實、不講判定**——判定是醫生的事。這裡只擺事實。
3. 沒資料就誠實回空，不編。

再加三條這支專屬的（因為東西要遞到醫師手上，責任更重）：

4. **來源必須標記，不可混為一談。** 症狀是「長輩自己說的」（主觀、可能記錯、由 AI 從
   對話萃取），量測是機器量的（客觀）。兩者可信度天差地遠，醫師必須一眼分辨得出來，
   否則我們等於拿一句 AI 可能聽錯的話冒充臨床事實。這條是本支最重要的規矩。
5. **只並列、不連線。** 同一天出現「症狀變嚴重」和「血壓偏離平常」，只能並排陳列，
   **不可以**寫成「可能因為」「導致」「與…相關」。並列是事實，連線是判讀（紅線）。
6. **一頁上限、超出誠實揭露。** 醫師只看一頁。超過上限就明說「另有 N 筆未列出」，
   不可以悄悄截斷——悄悄截斷會讓人以為這就是全部。

不呼叫 AI（Edward 2026-07-27「不花錢證明」）：全程純程式組裝，生成一千份跟一份同價。
症狀文字讀的是記憶層**已經萃取好**的結果，本支不新增任何模型呼叫。
"""

import datetime

import health_context

# 使用者可選的期間（Edward 2026-07-28 拍板：四個固定選項，不做日期選擇器——長輩不會用）
PERIOD_DAYS = (7, 14, 30, 60)
DEFAULT_PERIOD = 14

# 時間軸一頁上限。超過就挑、並誠實回報漏了幾筆（鐵律 6）。
MAX_TIMELINE = 12

# 挑選優先序：症狀 > 用藥 > 量測。
# 為什麼症狀優先：那是醫師問診時**問不出來**的東西（長輩當場想不起來），
# 而血壓數字他自己會量、也看得到趨勢。稀缺的先留。
KIND_PRIORITY = {"symptom": 0, "med": 1, "vital": 2}

# 記憶層裡屬於「身體狀況」的型別（memory_engine.TYPES 的一支）
SYMPTOM_MEMORY_TYPE = "health_context"

# 低於這個信心分數的萃取結果不進摘要。
# 理由：這份東西要遞到醫師手上。AI 沒把握的句子寧可不放，
# 放了醫師也不知道該不該信，反而有害。
MIN_SYMPTOM_CONFIDENCE = 0.6


def _iso(d):
    return d.strftime("%Y-%m-%d")


def _parse_day(value):
    """吃 'YYYY-MM-DD' 或 ISO 時間戳，回 date；壞資料回 None（不炸、不猜）。"""
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
    except (ValueError, IndexError):
        return None


def period_bounds(period_days, today=None):
    """回 (起日, 迄日)。迄日＝今天，起日＝往前推 period_days-1 天（含今天共 N 天）。"""
    if period_days not in PERIOD_DAYS:
        period_days = DEFAULT_PERIOD
    end = today or datetime.date.today()
    if isinstance(end, str):
        end = _parse_day(end) or datetime.date.today()
    start = end - datetime.timedelta(days=period_days - 1)
    return start, end


def symptom_events(memories, start, end):
    """記憶層的身體狀況記錄 → 時間軸事件（來源＝長輩自己說的）。

    只收 health_context 型別、期間內、信心夠的。文字**原樣照搬**，不改寫、不摘要——
    改寫就是加工，加工過的話拿去給醫師看等於我們在替長輩發言。
    """
    out = []
    for item in memories or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != SYMPTOM_MEMORY_TYPE:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        try:
            confidence = float(item.get("confidence", 0.6) or 0.6)
        except (TypeError, ValueError):
            confidence = 0.6
        if confidence < MIN_SYMPTOM_CONFIDENCE:
            continue
        day = _parse_day(item.get("createdAt") or item.get("updatedAt"))
        if day is None or day < start or day > end:
            continue
        out.append({
            "date": _iso(day),
            "kind": "symptom",
            "source": "長輩自己說的",
            "text": content,
            "detail": "",
        })
    return out


def vital_events(health_log, start, end):
    """在家量測裡「跟他自己平常不一樣」的日子 → 時間軸事件（來源＝機器量的）。

    「平常」用 health_context 那把尺（近 14 天基線），**不是**整段期間的平均——
    因為基線就是那樣算的，這裡不另立標準。所以 60 天的摘要裡，「平常」仍然指近兩週的平常，
    呈現時必須標明（見 build() 回傳的 baselineNote），否則會誤導醫師。

    只陳列「幾號、量到多少、他平常多少」，不寫偏高偏低（鐵律 2）。
    """
    out = []
    if not isinstance(health_log, dict) or not health_log:
        return out

    # 血壓兩個數字要一起看，拆開沒意義（沿用 health_context 的處理）
    sys_base, _ = health_context.baseline_and_recent(health_log, "bpSys")
    dia_base, _ = health_context.baseline_and_recent(health_log, "bpDia")

    for day_key in sorted(health_log.keys()):
        day = _parse_day(day_key)
        if day is None or day < start or day > end:
            continue
        row = health_log.get(day_key) or {}
        if not isinstance(row, dict):
            continue

        sys_v, dia_v = row.get("bpSys"), row.get("bpDia")
        if sys_v and dia_v and (
            health_context._is_notable("bpSys", sys_v, sys_base)
            or health_context._is_notable("bpDia", dia_v, dia_base)
        ):
            detail = f"平常 {int(sys_base)}/{int(dia_base)}" if sys_base and dia_base else ""
            out.append({
                "date": _iso(day), "kind": "vital", "source": "量測",
                "text": f"血壓 {int(sys_v)}/{int(dia_v)}", "detail": detail,
            })

        for field in ("hr", "spo2", "sleepHours", "steps"):
            value = row.get(field)
            if value is None:
                continue
            baseline, _ = health_context.baseline_and_recent(health_log, field)
            if not health_context._is_notable(field, value, baseline):
                continue
            label = health_context.FIELD_LABEL[field]
            detail = f"平常 {health_context._fmt(baseline, field)}" if baseline else ""
            out.append({
                "date": _iso(day), "kind": "vital", "source": "量測",
                "text": f"{label} {health_context._fmt(value, field)}", "detail": detail,
            })
    return out


def medication_summary(doses, start, end):
    """整段期間的服藥實況（不是只有今天）。

    health_context.summarize_medication 只算當天——那是給「她心裡知道」用的。
    醫師要看的是「上次開的藥這段期間到底吃了沒」，所以這裡按藥名彙總整段期間。
    只給排了幾次、吃了幾次、漏了幾次，**不算順從率百分比**——
    百分比看起來像評分，而評分是判定（鐵律 2）。
    """
    by_name = {}
    for dose in doses or []:
        if not isinstance(dose, dict):
            continue
        day = _parse_day(dose.get("scheduledDate"))
        if day is None or day < start or day > end:
            continue
        name = str(dose.get("medName") or dose.get("name") or "").strip() or "藥"
        row = by_name.setdefault(name, {"name": name, "scheduled": 0, "taken": 0, "missed": 0})
        row["scheduled"] += 1
        status = dose.get("status")
        if status == "taken":
            row["taken"] += 1
        elif status in ("missed", "skipped"):
            row["missed"] += 1
    return sorted(by_name.values(), key=lambda r: (-r["missed"], r["name"]))


def medication_events(medication, start, end):
    """漏藥多到值得醫師知道 → 進時間軸。

    門檻＝整段期間漏 3 次以上。偶爾忘一次是常態、不值得占一頁的位置；
    連續漏才是醫師會想追問的事（可能副作用、可能吃不下、可能忘記）。
    一樣只講事實，不猜原因。
    """
    out = []
    for row in medication or []:
        if row.get("missed", 0) < 3:
            continue
        out.append({
            "date": _iso(end), "kind": "med", "source": "用藥紀錄",
            "text": f"{row['name']} 這段期間漏吃 {row['missed']} 次",
            "detail": f"共排 {row['scheduled']} 次",
        })
    return out


def _select(events):
    """超過一頁就挑：先按優先序與新近度挑，選完再按日期排回去。

    回 (要顯示的, 被略過的筆數)。被略過的筆數一定要往上報——
    悄悄截斷會讓醫師以為這就是全部（鐵律 6）。
    """
    if len(events) <= MAX_TIMELINE:
        return sorted(events, key=lambda e: e["date"]), 0
    ranked = sorted(
        events,
        key=lambda e: (KIND_PRIORITY.get(e["kind"], 9), _negated_date(e["date"])),
    )
    kept = ranked[:MAX_TIMELINE]
    return sorted(kept, key=lambda e: e["date"]), len(events) - len(kept)


def _negated_date(date_text):
    """日期反向排序鍵：越新越前面（字串日期不能直接取負，轉成可比較的負序）。"""
    return tuple(-int(part) for part in date_text.split("-"))


def build(period_days=DEFAULT_PERIOD, memories=None, health_log=None, doses=None, today=None):
    """組一份就診摘要。純程式、不呼叫 AI、沒資料就誠實回空。

    回 dict：
      periodDays / from / to        涵蓋期間（畫面與紙面都要印出來，讓醫師知道邊界）
      timeline                      合併時間軸，每筆帶 kind 與 source（鐵律 4）
      timelineOmitted               因一頁上限沒列出的筆數（鐵律 6）
      vitals                        期間末的量測事實（沿用 health_context）
      medication                    整段期間的服藥實況
      baselineNote                  「平常」是怎麼算的——必須印在紙上，否則誤導
      hasData                       全空時上游據此顯示「還沒有資料」，不生假摘要
    """
    if period_days not in PERIOD_DAYS:
        period_days = DEFAULT_PERIOD
    start, end = period_bounds(period_days, today)

    medication = medication_summary(doses, start, end)
    events = (
        symptom_events(memories, start, end)
        + vital_events(health_log, start, end)
        + medication_events(medication, start, end)
    )
    timeline, omitted = _select(events)

    vitals = health_context.summarize_vitals(health_log or {}, today=_iso(end))

    return {
        "periodDays": period_days,
        "from": _iso(start),
        "to": _iso(end),
        "timeline": timeline,
        "timelineOmitted": omitted,
        "vitals": vitals.get("facts", []),
        "medication": medication,
        # 這句一定要跟著資料走：60 天的摘要裡「平常」仍是近兩週的平常，
        # 不標的話醫師會以為那是整段期間的平均值。
        "baselineNote": f"「平常」＝他自己最近 {health_context.BASELINE_WINDOW} 天的數字，不做任何醫學比對",
        "hasData": bool(timeline or medication or vitals.get("facts")),
    }
