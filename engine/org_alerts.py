"""機構端「異常提醒匣」＋逐筆判定（補助案 C4：異常通知上線、準確率 80% 以上、50 筆以上逐筆判定）。

一句話：每天的三條異常規則（心情下降／沒聯絡／守護腦亮燈）算出來的提醒，第一次被算到時「發出」一筆、
記下發出時間；照護人員在機構專區逐筆標「正確／誤報／觀察中」，只能新增、不能改舊的。

設計依據：docs/後台-B2B2C-產品框架設計-2026-10-28.md 第 2.3 節（權限）、3.2 節（標記留 2 年、不可刪）、
4.3 節 `/org/alerts`、`/org/alert/mark`、`/org/audit`；判定欄位與 C4 逐筆判定表對齊
（補助案-驗收管理/驗收證據/3-116年3月/C4/，2026-11-18 跟做量測的工作階段議定）。

存哪裡：不新開資料表。「發出」與「判定」都寫進既有的稽核紀錄（audit_events，只能新增），
事件種類 org_alert_raised／org_alert_marked。稽核紀錄本來就是「誰、何時、做了什麼」而且刪不掉，
正好是設計書要的「不可刪、只能再加一筆」；也省掉一次正式資料庫變更。

三條鐵線照舊：
  1. 機構只看自己家：一律從登入身分推機構，不收前端的機構參數。
  2. 沒同意的長輩不出現：提醒只算、只列「現在仍同意」的席次；撤回同意後，那位的舊提醒也一起從清單消失。
  3. 不帶原句：提醒內容只用規則的固定句型（fact），送出前過一次禁用鍵檢查。
"""
import datetime as _dt
import hashlib
import logging
import re

import care_week
import enterprise_seats
import org_api

LOGGER = logging.getLogger("munea.org_alerts")

EVENT_RAISED = "org_alert_raised"
EVENT_MARKED = "org_alert_marked"
EVENT_SETTINGS = "org_settings_saved"
NO_CONTACT_DAYS_DEFAULT = care_week.NO_CONTACT_DAYS_DEFAULT
SETTINGS_LOOKBACK_DAYS = 3650
ALERT_TYPES = ("mood_drop", "no_contact", "guardian")
TYPE_LABELS = {"mood_drop": "心情下降", "no_contact": "沒聯絡", "guardian": "守護腦亮燈"}
MARK_RESULTS = ("correct", "false_alarm", "watching")          # 正確／誤報／觀察中
RESULT_LABELS = {"correct": "正確", "false_alarm": "誤報", "watching": "觀察中"}
YES_NO = ("yes", "no")
LOOKBACK_DAYS = 90            # 提醒匣看多久以前的提醒
MOOD_EPISODE_DAYS = 7         # 同一位長輩 7 天內已經發過「心情下降」就不再發（同一段低潮只發一次）
REMARK_MAX = 200
ROLE_LABELS = {"org_admin": "機構管理者", "case_manager": "社工／個管", "care_worker": "照服員"}

# server.py 啟動時設：fn(client_id, since_iso, event_types) -> [audit event dict]（新到舊、舊到新都可以）
EVENT_LOADER = None


def set_event_loader(fn):
    global EVENT_LOADER
    EVENT_LOADER = fn


# ---------------------------------------------------------------------------
# 提醒的身分：同一件事算幾次都得到同一個編號
# ---------------------------------------------------------------------------

def _anchor(anomaly, week):
    """「這是哪一件事」的錨點。

    - 沒聯絡：最後一次通話的日子（同一段沒聯絡，不管拖幾天都是同一件）。
    - 守護腦：最後一次亮燈的時間（每一次新的亮燈是新的一件）。
    - 心情下降：規則給的日期；同一段低潮靠 MOOD_EPISODE_DAYS 擋重複。
    """
    kind = anomaly.get("type")
    if kind == "no_contact":
        return str((week.get("contact") or {}).get("lastCallDate") or "none")
    return str(anomaly.get("when") or "")


def _account_key(account_id):
    """帳號指紋：發出那一刻席次綁的是誰。之後席次換綁給別人，舊提醒不能掛到新的人名下。"""
    return hashlib.sha1(f"munea-org-alert|{account_id}".encode("utf-8")).hexdigest()[:16]


def alert_id(seat_id, kind, anchor):
    """ALR-<錨點日期>-<六碼>。同一件事算幾次都同一個編號；錨點沒有日期（例：從來沒通過話）就用 NONE。"""
    digest = hashlib.sha1(f"{seat_id}|{kind}|{anchor}".encode("utf-8")).hexdigest()[:6].upper()
    day = re.sub(r"[^0-9]", "", str(anchor))[:8]
    return f"ALR-{day if len(day) == 8 else 'NONE'}-{digest}"


# ---------------------------------------------------------------------------
# 讀稽核紀錄裡的「發出」與「判定」
# ---------------------------------------------------------------------------

def _load_events(client_id, since_iso):
    if EVENT_LOADER is None:
        raise RuntimeError("org_alerts event loader not configured")
    rows = EVENT_LOADER(client_id, since_iso, (EVENT_RAISED, EVENT_MARKED)) or []
    raised, marks = {}, {}
    for ev in rows:
        details = ev.get("details") or {}
        if str(details.get("clientId") or "") != str(client_id):
            continue  # 雙保險：讀取端已經用機構過濾，這裡再擋一次
        alert = str(details.get("alertId") or "")
        if not alert:
            continue
        if ev.get("eventType") == EVENT_RAISED:
            raised.setdefault(alert, {**details, "raisedAt": ev.get("createdAt") or details.get("raisedAt")})
        elif ev.get("eventType") == EVENT_MARKED:
            marks.setdefault(alert, []).append({**details, "markedAt": ev.get("createdAt") or details.get("markedAt")})
    for items in marks.values():
        items.sort(key=lambda m: str(m.get("markedAt") or ""))
    return raised, marks


# ---------------------------------------------------------------------------
# 機構自己的設定（目前只有「幾天沒聯絡才提醒」）：也是只能新增的紀錄，最後一筆為準
# ---------------------------------------------------------------------------

def client_settings(client_id):
    """回 {"noContactDays": n, "updatedAt": …}。讀不到就用預設，不擋提醒。"""
    out = {"noContactDays": NO_CONTACT_DAYS_DEFAULT, "updatedAt": None}
    if EVENT_LOADER is None:
        return out
    since_iso = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=SETTINGS_LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    try:
        rows = EVENT_LOADER(client_id, since_iso, (EVENT_SETTINGS,)) or []
    except Exception as exc:
        LOGGER.warning("org_alerts settings load failed; using defaults: %s", exc)
        return out
    latest = None
    for ev in rows:
        details = ev.get("details") or {}
        if ev.get("eventType") != EVENT_SETTINGS or str(details.get("clientId") or "") != str(client_id):
            continue
        stamp = str(ev.get("createdAt") or details.get("savedAt") or "")
        if latest is None or stamp >= latest[0]:
            latest = (stamp, details)
    if latest:
        try:
            out["noContactDays"] = max(1, min(30, int(latest[1].get("noContactDays"))))
            out["updatedAt"] = latest[0] or None
        except (TypeError, ValueError):
            pass
    return out


def org_settings_response(auth, data=None):
    """`/org/settings`：讀目前設定（看得到提醒匣的人都能讀）。"""
    staff, client = org_api._staff_and_client(auth)
    if not staff or not org_api.capabilities_for(staff, client)["careWeek"]:
        return org_api._not_found()
    settings = client_settings(client["id"])
    return org_api.assert_no_forbidden({"ok": True, "settings": settings, "canEdit": staff.get("role") == "org_admin",
                                        "limits": {"noContactDays": [1, 30]}})


def org_settings_save_response(auth, data=None):
    """`/org/settings/save`：只有機構管理者能改；每次改都留一筆（誰、何時、改成幾天）。"""
    data = data or {}
    staff, client = org_api._staff_and_client(auth)
    if not staff or staff.get("role") != "org_admin" or org_api._client_kind(client) == "esg":
        return org_api._not_found()
    try:
        days = int(data.get("noContactDays"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "no_contact_days_invalid", "allowed": [1, 30]}
    if not 1 <= days <= 30:
        return {"ok": False, "error": "no_contact_days_invalid", "allowed": [1, 30]}
    ok = org_api._audit({
        "eventType": EVENT_SETTINGS, "actorUserId": staff.get("authUserId"), "targetTable": "enterprise_clients",
        "targetId": client["id"], "details": {"clientId": client["id"], "noContactDays": days, "staffId": staff["id"],
                                             "role": staff["role"], "actorType": "org_staff", "savedAt": org_api._utc_now()},
    })
    if not ok:
        return {"ok": False, "error": "settings_not_recorded"}
    return org_api.assert_no_forbidden({"ok": True, "settings": {"noContactDays": days, "updatedAt": org_api._utc_now()}})


# ---------------------------------------------------------------------------
# 算出現在該有的提醒，第一次算到的「發出」
# ---------------------------------------------------------------------------

def _candidate_alerts(client, loaders, today, settings=None):
    """整家（不分分點）現在仍同意的席次，各自算一週、跑三條規則。settings＝機構自訂（沒聯絡天數）。"""
    seats = org_api._only_consented(
        [s for s in enterprise_seats.list_seats(client_id=client["id"]) if s.get("status") in org_api.SEAT_STATUSES_VISIBLE],
        client,
    )[:org_api.MAX_ELDERS]
    account_ids = [s["accountId"] for s in seats]
    start, _end = care_week.period_bounds(org_api.L1_DAYS, today)
    since_iso = (start - _dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    partial = []
    try:
        persons = loaders["persons"](account_ids) or {}
    except Exception as exc:
        LOGGER.warning("org_alerts persons lookup failed: %s", exc)
        persons, partial = {}, ["persons"]
    try:
        events = loaders["guardianEvents"](account_ids, since_iso) or []
    except Exception as exc:
        LOGGER.warning("org_alerts guardian events failed: %s", exc)
        events, partial = [], partial + ["safety"]
    out = []
    for seat in seats:
        account_id = seat["accountId"]
        info = persons.get(account_id) or {}
        person_id = info.get("personId")
        if not person_id:
            continue
        ev_for = [e for e in events if str(e.get("personId") or "") == str(person_id) or
                  (not e.get("personId") and str(e.get("accountId") or "") == str(account_id))]
        week = org_api._build_week(person_id, account_id, loaders, ev_for, today, org_api.L1_DAYS)
        for anomaly in org_api._strip_anomalies(care_week.detect_anomalies(week, settings or {})):
            kind = anomaly.get("type")
            if kind not in ALERT_TYPES:
                continue
            anchor = _anchor(anomaly, week)
            out.append({
                "alertId": alert_id(seat["id"], kind, anchor), "seatId": seat["id"], "accountId": account_id,
                "siteLabel": seat.get("siteLabel"), "type": kind, "anchor": anchor, "when": anomaly.get("when"),
                "fact": anomaly.get("fact"), "suggestion": anomaly.get("suggestion"),
            })
    return seats, persons, out, partial


def _suppressed(candidate, raised, today):
    """同一段心情低潮只發一次：這位長輩 7 天內已經發過心情下降，就不再發。"""
    if candidate["type"] != "mood_drop":
        return False
    floor = (today - _dt.timedelta(days=MOOD_EPISODE_DAYS)).isoformat()
    for item in raised.values():
        if item.get("seatId") == candidate["seatId"] and item.get("type") == "mood_drop" \
                and str(item.get("raisedAt") or "")[:10] >= floor:
            return True
    return False


def refresh_alerts(client, loaders=None, today=None):
    """算一次、把新出現的提醒「發出」（寫一筆 org_alert_raised）。回 (raised, marks, seats, persons, partial)。"""
    loaders = loaders or org_api.default_loaders()
    today_str = today or org_api._today()
    _start, today_date = care_week.period_bounds(1, today_str)
    since_iso = (today_date - _dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    raised, marks = _load_events(client["id"], since_iso)
    settings = client_settings(client["id"])
    seats, persons, candidates, partial = _candidate_alerts(client, loaders, today_str, {"noContactDays": settings["noContactDays"]})
    for cand in candidates:
        prior = raised.get(cand["alertId"])
        if (prior and prior.get("accountKey") in (None, _account_key(cand["accountId"]))) or _suppressed(cand, raised, today_date):
            continue
        if prior:
            # 同一個席次換了人、同一件事（例如都從沒通過話）：編號加上新指紋，當成新的一件
            cand = {**cand, "alertId": alert_id(cand["seatId"], cand["type"], f"{cand['anchor']}|{_account_key(cand['accountId'])}")}
            if cand["alertId"] in raised:
                continue
        now = org_api._utc_now()
        details = {
            "clientId": client["id"], "alertId": cand["alertId"], "seatId": cand["seatId"], "siteLabel": cand["siteLabel"],
            "type": cand["type"], "anchor": cand["anchor"], "when": cand["when"], "fact": cand["fact"],
            "suggestion": cand["suggestion"], "channel": "org_portal_inbox", "raisedAt": now, "actorType": "system",
            "accountKey": _account_key(cand["accountId"]),
        }
        ok = org_api._audit({
            "eventType": EVENT_RAISED, "accountId": cand["accountId"], "targetTable": "enterprise_seats",
            "targetId": cand["seatId"], "details": details,
        })
        if ok:
            raised[cand["alertId"]] = details
        else:
            partial = partial + ["alert_record"] if "alert_record" not in partial else partial
    return raised, marks, seats, persons, partial


# ---------------------------------------------------------------------------
# 給照護人員看
# ---------------------------------------------------------------------------

def _staff_names(client_id):
    try:
        return {s["id"]: s for s in org_api.list_staff(client_id=client_id)}
    except Exception as exc:
        LOGGER.warning("org_alerts staff lookup failed: %s", exc)
        return {}


def _public_mark(mark, staff_by_id):
    staff = staff_by_id.get(mark.get("staffId")) or {}
    return {
        "result": mark.get("result"), "resultLabel": RESULT_LABELS.get(mark.get("result"), ""),
        "isReal": mark.get("isReal"), "worthNotifying": mark.get("worthNotifying"),
        "remark": mark.get("remark") or "", "markedAt": mark.get("markedAt"),
        "markedBy": staff.get("displayName") or "", "markedByRole": ROLE_LABELS.get(mark.get("role") or staff.get("role"), ""),
    }


def _view(alert, marks, seat, info, staff_by_id):
    history = [_public_mark(m, staff_by_id) for m in marks.get(alert["alertId"], [])]
    latest = history[-1] if history else None
    return {
        "alertId": alert["alertId"], "seatId": alert["seatId"], "seatCode": org_api._seat_code(alert["seatId"]),
        "label": org_api._elder_label(info, seat, True), "siteLabel": seat.get("siteLabel"),
        "type": alert.get("type"), "typeLabel": TYPE_LABELS.get(alert.get("type"), ""),
        "when": alert.get("when"), "fact": alert.get("fact"), "suggestion": alert.get("suggestion"),
        "raisedAt": alert.get("raisedAt"), "status": latest["result"] if latest else "unmarked",
        "statusLabel": latest["resultLabel"] if latest else "還沒判定", "lastMark": latest, "markHistory": history,
    }


def _scope_seats(staff, seats):
    caps_site = staff.get("siteLabel") if staff.get("role") != "org_admin" else None
    if caps_site:
        return [s for s in seats if (s.get("siteLabel") or None) == caps_site]
    return seats


def org_alerts_response(auth, data=None, loaders=None, today=None):
    """`/org/alerts`：提醒匣。管理者看整家、社工看自己分點；照服員只拿名單旗標、企業 HR 沒有這頁。"""
    data = data or {}
    staff, client = org_api._staff_and_client(auth)
    if not staff:
        return org_api._not_found()
    caps = org_api.capabilities_for(staff, client)
    if not caps["careWeek"]:
        return org_api._not_found()
    try:
        raised, marks, seats, persons, partial = refresh_alerts(client, loaders, today)
    except Exception as exc:
        LOGGER.error("org_alerts refresh failed: %s", exc)
        return {"ok": False, "error": "alerts_unavailable"}
    visible = {s["id"]: s for s in _scope_seats(staff, seats)}
    staff_by_id = _staff_names(client["id"])
    alerts = []
    for alert in raised.values():
        seat = visible.get(alert.get("seatId"))
        if not seat:
            continue  # 別的分點、或已經撤回同意的長輩：不列
        if alert.get("accountKey") and alert["accountKey"] != _account_key(seat.get("accountId")):
            continue  # 席次已經換給別人：前一位的提醒不掛到新的人名下
        alerts.append(_view(alert, marks, seat, persons.get(seat["accountId"]) or {}, staff_by_id))
    status_filter = str(data.get("status") or "").strip()
    if status_filter in MARK_RESULTS + ("unmarked",):
        alerts = [a for a in alerts if a["status"] == status_filter]
    alerts.sort(key=lambda a: str(a.get("raisedAt") or ""), reverse=True)
    counts = {k: 0 for k in ("unmarked",) + MARK_RESULTS}
    for a in alerts:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    judged = counts["correct"] + counts["false_alarm"]
    payload = {
        "ok": True, "count": len(alerts), "alerts": alerts, "counts": counts,
        "accuracy": {"correct": counts["correct"], "falseAlarm": counts["false_alarm"], "judged": judged,
                     "rate": round(counts["correct"] / judged, 4) if judged else None,
                     "method": "正確 ÷（正確＋誤報）；觀察中不計。漏報要對照情境演練劇本另外算，不在這裡。"},
        "scope": {"siteLabel": caps["siteLabel"], "siteScoped": caps["siteScoped"]},
        "canMark": True, "lookbackDays": LOOKBACK_DAYS, "partial": partial,
        "privacy": {"statement": "只列已同意長輩的提醒；提醒內容是規則的固定句型，沒有對話原句。每一筆判定都會留下紀錄（誰、何時、判成什麼），不能刪改。"},
    }
    return org_api.assert_no_forbidden(payload)


_PHONE_RE = re.compile(r"(?:\+?886[-\s]?|0)9\d{2}[-\s]?\d{3}[-\s]?\d{3}|\b0\d{1,2}[-\s]?\d{6,8}\b")
_TW_ID_RE = re.compile(r"\b[A-Za-z][12]\d{8}\b")


def _clean_remark(value):
    """備註是照護人員自己打的字：去掉角括號、把電話與身分證號換成「〔已遮〕」、收成一行、最多 200 字。
    （全名、病名擋不住——畫面上會提醒不要寫；這裡只擋格式明確的。）"""
    text = re.sub(r"[<>]", "", str(value or ""))
    text = _TW_ID_RE.sub("〔已遮〕", text)
    text = _PHONE_RE.sub("〔已遮〕", text)
    return re.sub(r"\s+", " ", text).strip()[:REMARK_MAX]


def _norm_yes_no(value):
    text = str(value or "").strip().lower()
    if text in ("yes", "true", "1", "是", "y"):
        return "yes"
    if text in ("no", "false", "0", "否", "n"):
        return "no"
    return None


def org_alert_mark_response(auth, data=None, loaders=None, today=None):
    """`/org/alert/mark`：判定一筆提醒。只能新增一筆，不能改舊的；寫不進稽核就不算數。"""
    data = data or {}
    staff, client = org_api._staff_and_client(auth)
    if not staff:
        return org_api._not_found()
    caps = org_api.capabilities_for(staff, client)
    if not caps["careWeek"]:
        return org_api._not_found()
    alert_key = str(data.get("alertId") or "").strip()
    result = str(data.get("result") or "").strip()
    if not alert_key:
        return org_api._not_found()
    if result not in MARK_RESULTS:
        return {"ok": False, "error": "result_invalid", "allowed": list(MARK_RESULTS)}
    remark = _clean_remark(data.get("remark"))
    since_iso = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    try:
        raised, marks = _load_events(client["id"], since_iso)
    except Exception as exc:
        LOGGER.error("org_alerts load for mark failed: %s", exc)
        return {"ok": False, "error": "alerts_unavailable"}
    alert = raised.get(alert_key)
    if not alert:
        return org_api._not_found()
    consented = org_api._only_consented(
        [s for s in enterprise_seats.list_seats(client_id=client["id"]) if s.get("status") in org_api.SEAT_STATUSES_VISIBLE], client)
    seat = next((s for s in _scope_seats(staff, consented) if s.get("id") == alert.get("seatId")), None)
    if not seat or (alert.get("accountKey") and alert["accountKey"] != _account_key(seat.get("accountId"))):
        return org_api._not_found()   # 別的分點、已撤回同意、或席次已換人：跟「不存在」同一句
    details = {
        "clientId": client["id"], "alertId": alert_key, "seatId": seat["id"], "type": alert.get("type"),
        "result": result, "isReal": _norm_yes_no(data.get("isReal")), "worthNotifying": _norm_yes_no(data.get("worthNotifying")),
        "remark": remark, "staffId": staff["id"], "role": staff["role"], "actorType": "org_staff", "markedAt": org_api._utc_now(),
    }
    ok = org_api._audit({
        "eventType": EVENT_MARKED, "actorUserId": staff.get("authUserId"), "accountId": seat["accountId"],
        "targetTable": "enterprise_seats", "targetId": seat["id"], "details": details,
    })
    if not ok:
        return {"ok": False, "error": "mark_not_recorded"}
    marks.setdefault(alert_key, []).append(details)
    try:
        info = ((loaders or org_api.default_loaders())["persons"]([seat["accountId"]]) or {}).get(seat["accountId"]) or {}
    except Exception as exc:  # 稱呼拿不到只影響顯示，判定已經寫進去了
        LOGGER.warning("org_alerts person label lookup failed: %s", exc)
        info = {}
    view = _view(alert, marks, seat, info, _staff_names(client["id"]))
    return org_api.assert_no_forbidden({"ok": True, "alert": view})


AUDIT_ACTIONS = {
    "org_care_week_read": "看了週關懷摘要",
    EVENT_MARKED: "判定了一筆提醒",
    "org_staff_activated": "第一次登入",
    "org_consent_granted": "長輩（或家人）打開了同意",
    "org_consent_revoked": "長輩（或家人）關掉了同意",
    EVENT_SETTINGS: "改了提醒設定",
}


def org_audit_response(auth, data=None):
    """`/org/audit`：自家紀錄（誰在什麼時候看了誰、判定了什麼）。只有機構管理者看得到。"""
    staff, client = org_api._staff_and_client(auth)
    if not staff or staff.get("role") != "org_admin" or org_api._client_kind(client) == "esg":
        return org_api._not_found()
    since_iso = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    try:
        rows = EVENT_LOADER(client["id"], since_iso, tuple(AUDIT_ACTIONS)) if EVENT_LOADER else []
    except Exception as exc:
        LOGGER.error("org_alerts audit load failed: %s", exc)
        return {"ok": False, "error": "audit_unavailable"}
    staff_by_id = _staff_names(client["id"])
    by_auth = {s.get("authUserId"): s for s in staff_by_id.values() if s.get("authUserId")}
    items = []
    for ev in rows or []:
        details = ev.get("details") or {}
        if str(details.get("clientId") or "") != str(client["id"]) or ev.get("eventType") not in AUDIT_ACTIONS:
            continue
        who = staff_by_id.get(details.get("staffId")) or by_auth.get(ev.get("actorUserId")) or {}
        actor = who.get("displayName") or ("長輩或家人" if str(ev.get("eventType", "")).startswith("org_consent_") else "")
        seat_id = details.get("seatId") or (ev.get("targetId") if ev.get("targetTable") == "enterprise_seats" else None)
        items.append({
            "at": ev.get("createdAt"), "action": AUDIT_ACTIONS[ev["eventType"]], "eventType": ev["eventType"],
            "actor": actor, "actorRole": ROLE_LABELS.get(who.get("role") or details.get("role"), ""),
            "seatCode": org_api._seat_code(seat_id) if seat_id else None,
            "result": RESULT_LABELS.get(details.get("result"), "") if ev["eventType"] == EVENT_MARKED else None,
        })
    items.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return org_api.assert_no_forbidden({"ok": True, "count": len(items), "items": items[:500], "lookbackDays": LOOKBACK_DAYS})


# ---------------------------------------------------------------------------
# 營運端：匯出逐筆判定（欄位順序對齊 C4 逐筆判定表）
# ---------------------------------------------------------------------------

EXPORT_COLUMNS = ["事件編號", "演練編號", "來源", "規則", "系統有沒有通知", "第一次出現在提醒匣的時間", "通知內容",
                  "事情是真的嗎", "值得通知嗎", "判定結果", "判定者", "職稱", "判定日期", "備註", "判定次數"]
_YES_NO_LABEL = {"yes": "是", "no": "否", None: ""}
_DRILL_ID_RE = re.compile(r"^[A-Z]\d{2}$")


def admin_alerts_export_response(data=None):
    """營運後台（萬能鑰匙）匯出某家機構的提醒與判定，一列一筆。演練編號取自席次名冊稱呼（例 M01），只有營運端看得到。"""
    data = data or {}
    client_id = str(data.get("clientId") or data.get("client_id") or "").strip()
    client = enterprise_seats.get_client(client_id) if client_id else None
    if not client:
        return {"ok": False, "error": "client_not_found"}
    try:
        days = max(1, min(366, int(data.get("days") or LOOKBACK_DAYS)))
    except (TypeError, ValueError):
        days = LOOKBACK_DAYS
    since_iso = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    try:
        raised, marks = _load_events(client["id"], since_iso)
    except Exception as exc:
        LOGGER.error("org_alerts export load failed: %s", exc)
        return {"ok": False, "error": "alerts_unavailable"}
    seats = {s["id"]: s for s in enterprise_seats.list_seats(client_id=client["id"])}
    staff_by_id = _staff_names(client["id"])
    rows = []
    for alert in sorted(raised.values(), key=lambda a: str(a.get("raisedAt") or "")):
        seat = seats.get(alert.get("seatId")) or {}
        drill = str(seat.get("memberName") or "").strip().upper()
        drill = drill if _DRILL_ID_RE.match(drill) else ""
        history = marks.get(alert["alertId"], [])
        last = history[-1] if history else {}
        judge = staff_by_id.get(last.get("staffId")) or {}
        rows.append({
            "事件編號": alert["alertId"], "演練編號": drill, "來源": "演練" if drill else "試辦",
            "規則": alert.get("type"), "系統有沒有通知": "是", "第一次出現在提醒匣的時間": alert.get("raisedAt"),
            "通知內容": alert.get("fact"), "事情是真的嗎": _YES_NO_LABEL.get(last.get("isReal"), ""),
            "值得通知嗎": _YES_NO_LABEL.get(last.get("worthNotifying"), ""),
            "判定結果": RESULT_LABELS.get(last.get("result"), "") if last else "",
            "判定者": judge.get("displayName") or "", "職稱": ROLE_LABELS.get(last.get("role") or judge.get("role"), ""),
            "判定日期": str(last.get("markedAt") or "")[:10], "備註": last.get("remark") or "", "判定次數": len(history),
        })
    rows = [{k: _cell(v) for k, v in row.items()} for row in rows]
    # 沐寧代看機構資料要留紀錄（設計書 3.2）。寫不進去就不給——跟機構端讀週摘要同一條規矩。
    if not org_api._audit({
        "eventType": "org_alerts_exported", "targetTable": "enterprise_clients", "targetId": client["id"],
        "details": {"clientId": client["id"], "actorType": "munea_operator", "rowCount": len(rows), "days": days},
    }):
        return {"ok": False, "error": "audit_unavailable"}
    return {"ok": True, "client": {"id": client["id"], "name": client.get("name") or ""}, "columns": EXPORT_COLUMNS,
            "count": len(rows), "rows": rows, "days": days}


def _cell(value):
    """轉成試算表時，= + - @ 開頭的字會被當成公式：前面加一個單引號。"""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value
