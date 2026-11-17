#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""補助案 C4 情境演練「預檢」（離線、不碰資料庫、不連正式機）。

做什麼：把 40 筆情境演練（engine/eval/c4_drill/scenarios_v1.json）各自當成一位測試長輩，
在暫存的本機資料裡開好「演練機構＋席次＋同意＋管理者」，餵進跟正式機同一份程式
（engine/org_alerts.py 的提醒匣、engine/care_week.py 的三條規則、engine/model_router.py 的守護腦），
看系統會不會發提醒、發哪一種，跟劇本的預期逐筆對照。

這是「正式演練之前先跑一遍」：正式演練（116/1）要在正式機用測試帳號真的灌資料、讓場域護理人員逐筆判定；
這裡只回答「程式行為跟劇本預期一不一致」，不算進 C4 的 50 筆。

跑法：
    python engine/eval/run_c4_drill.py                      # 守護腦只跑規則層（不連網）
    python engine/eval/run_c4_drill.py --with-ai-review     # 再加第二層 AI（正式線真路徑，需要 GEMINI_API_KEY）
    python engine/eval/run_c4_drill.py --out-md 報告.md
"""
import argparse
import datetime as _dt
import io
import json
import os
import sys
import tempfile
import uuid
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="munea-c4-drill-")
os.environ.setdefault("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY") or "c4-drill-offline")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
for key, name in (
    ("MUNEA_ORG_STAFF_PATH", "org_staff.json"), ("MUNEA_ORG_CONSENTS_PATH", "org_consents.json"),
    ("MUNEA_ENTERPRISE_CLIENTS_PATH", "clients.json"), ("MUNEA_ENTERPRISE_SEATS_PATH", "seats.json"),
    ("MUNEA_ENTERPRISE_SEAT_EVENTS_PATH", "seat_events.json"), ("MUNEA_ENTERPRISE_LOCAL_GRANTS_PATH", "grants.json"),
    ("MUNEA_ENTERPRISE_INVOICES_PATH", "invoices.json"), ("MUNEA_WELLBEING_PATH", "wellbeing.json"),
    ("MUNEA_CONVERSATION_SUMMARIES_PATH", "summaries.json"), ("MUNEA_PRODUCT_EVENTS_PATH", "events.json"),
    ("MUNEA_MEDICATION_DOSES_PATH", "doses.json"), ("MUNEA_AUDIT_EVENTS_STORE_PATH", "audit.json"),
):
    os.environ[key] = os.path.join(TMP, name)
sys.path.insert(0, ENGINE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import model_router  # noqa: E402
import org_alerts  # noqa: E402
import org_api  # noqa: E402

BASELINE_RECIPES = {  # 前 14 天平均 → 10 天整數心情
    3.8: [4] * 8 + [3] * 2, 4.4: [4] * 6 + [5] * 4, 4.5: [4] * 5 + [5] * 5, 3.0: [3] * 10,
}
TYPE_LABELS = {"mood_drop": "心情下降", "no_contact": "沒聯絡", "guardian": "守護腦"}


def _write(path_env, data):
    with io.open(os.environ[path_env], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _day(today, ago):
    return (today - _dt.timedelta(days=int(ago))).isoformat()


def _guardian_level(text, with_ai):
    """跟正式線同一條路：規則層判；不是 high／critical 而且有軟訊號，再送第二層 AI。"""
    r = model_router.guardian_evaluate_response({"text": text, "effort": "quick"})
    level = r["risk"]["level"]
    cats = list(r["risk"]["categories"] or [])
    via = "規則層"
    if level not in ("high", "critical") and with_ai and r["responsePolicy"].get("softSignalForReview"):
        import perception_engine
        sem = perception_engine.guardian_semantic_review(text, [], bool(r["responsePolicy"].get("reviewForced")))
        if sem and sem.get("level") in ("high", "critical"):
            level, cats, via = sem["level"], [sem.get("category") or "semantic"], "第二層 AI"
    return level, cats, via


def build_world(scenarios, today, with_ai):
    clients, seats, consents, staff, persons, signals, summaries, events, notes = {}, [], [], [], {}, {}, {}, [], {}
    for n in sorted({int(s.get("noContactDays") or 3) for s in scenarios}):
        cid = str(uuid.uuid4())
        clients[n] = {"id": cid, "name": f"C4 演練機構（{n} 天沒聯絡才提醒）", "planTier": "plus", "seatQuota": 200,
                      "status": "active", "clientKind": "care", "createdAt": "2026-11-01T00:00:00Z"}
        staff.append({"id": str(uuid.uuid4()), "enterpriseClientId": cid, "email": f"drill-admin-{n}@example.org",
                      "authUserId": str(uuid.uuid4()), "displayName": f"演練管理者（{n} 天）", "role": "org_admin", "status": "active"})
    for s in scenarios:
        n = int(s.get("noContactDays") or 3)
        cid = clients[n]["id"]
        seat_id, acc, per = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        seats.append({"id": seat_id, "enterpriseClientId": cid, "accountId": acc, "status": "active", "memberName": s["id"],
                      "inviteEmail": f"{s['id'].lower()}@drill.example.org", "createdAt": "2026-11-01T00:00:00Z"})
        consents.append({"id": str(uuid.uuid4()), "enterpriseClientId": cid, "seatId": seat_id, "accountId": acc,
                         "status": "granted", "grantedByRole": "self", "grantedAt": "2026-11-01T00:00:00Z"})
        persons[acc] = {"personId": per, "nickname": f"演練{s['id']}", "profileName": ""}
        rows = []
        for ago, level in s.get("mood") or []:
            rows.append({"personId": per, "date": _day(today, ago), "level": level, "mood": "低落" if level <= 2 else "平穩",
                         "wordObs": "", "concerns": [], "positives": [], "createdAt": _day(today, ago) + "T09:00:00Z"})
        if s.get("baselineAvg") is not None:
            for i, level in enumerate(BASELINE_RECIPES[float(s["baselineAvg"])]):
                ago = 8 + i
                rows.append({"personId": per, "date": _day(today, ago), "level": level, "mood": "平穩", "wordObs": "",
                             "concerns": [], "positives": [], "createdAt": _day(today, ago) + "T09:00:00Z"})
        signals[per] = rows
        summaries[per] = [{"id": f"cs-{s['id']}-{ago}", "personId": per, "summary": "", "createdAt": _day(today, ago) + "T10:00:00Z",
                           "deletedAt": None} for ago in (s.get("calls") or [])]
        judged = []
        for ago, text in s.get("sentences") or []:
            level, cats, via = _guardian_level(text, with_ai)
            judged.append({"text": text, "level": level, "via": via})
            if level in ("high", "critical", "medium", "low"):
                events.append({"accountId": acc, "personId": per, "eventTime": _day(today, ago) + "T11:00:00Z",
                               "riskLevel": level, "categories": cats})
        notes[s["id"]] = {"seatId": seat_id, "clientId": cid, "guardian": judged}
    _write("MUNEA_ENTERPRISE_CLIENTS_PATH", list(clients.values()))
    _write("MUNEA_ENTERPRISE_SEATS_PATH", seats)
    _write("MUNEA_ORG_CONSENTS_PATH", consents)
    _write("MUNEA_ORG_STAFF_PATH", staff)
    for env in ("MUNEA_WELLBEING_PATH", "MUNEA_CONVERSATION_SUMMARIES_PATH"):
        _write(env, [])
    _write("MUNEA_PRODUCT_EVENTS_PATH", {"events": []})
    loaders = {
        "persons": lambda ids: {a: persons[a] for a in ids if a in persons},
        "signals": lambda account_id, person_id: list(signals.get(person_id, [])),
        "summaries": lambda account_id, person_id: list(summaries.get(person_id, [])),
        "guardianEvents": lambda ids, since: [e for e in events if e.get("accountId") in set(ids)],
    }
    return clients, staff, loaders, notes


def run(scenarios, with_ai):
    today = _dt.date.today()
    clients, staff, loaders, notes = build_world(scenarios, today, with_ai)
    audit = []
    org_api.set_audit_sink(audit.append)

    def loader(client_id, since_iso, types):
        out = []
        for i, e in enumerate(audit):
            if e.get("eventType") in types:
                d = e.get("details") or {}
                out.append({"eventType": e["eventType"], "details": d,
                            "createdAt": f"{d.get('raisedAt') or d.get('markedAt') or d.get('savedAt') or ''}#{i:06d}"})
        return out

    org_alerts.set_event_loader(loader)
    by_seat = {}
    with patch.object(org_api, "_today", return_value=today.isoformat()):
        for n, client in clients.items():
            admin = next(s for s in staff if s["enterpriseClientId"] == client["id"])
            auth = {"authUserId": admin["authUserId"], "email": admin["email"]}
            if n != 3:
                saved = org_alerts.org_settings_save_response(auth, {"noContactDays": n})
                assert saved.get("ok"), saved
            out = org_alerts.org_alerts_response(auth, {}, loaders=loaders)
            assert out.get("ok"), out
            for a in out["alerts"]:
                by_seat.setdefault(a["seatId"], []).append(a)
    rows = []
    for s in scenarios:
        got = by_seat.get(notes[s["id"]]["seatId"], [])
        got_types = sorted({a["type"] for a in got})
        expect_types = sorted(s.get("expectTypes") or [])
        notified = bool(got)
        if s["expectNotify"] == notified and (not s["expectNotify"] or got_types == expect_types):
            verdict = "一致"
        elif s["expectNotify"] and not notified:
            verdict = "漏報（劇本要通知、系統沒發）"
        elif not s["expectNotify"] and notified:
            verdict = "多發（劇本不通知、系統發了）"
        else:
            verdict = "類型不同"
        rows.append({"id": s["id"], "rule": s["rule"], "expectNotify": s["expectNotify"], "expectTypes": expect_types,
                     "notified": notified, "gotTypes": got_types, "facts": [a["fact"] for a in got],
                     "guardian": notes[s["id"]]["guardian"], "verdict": verdict, "note": s.get("note") or ""})
    return rows


def render_md(rows, with_ai, source):
    ok = sum(1 for r in rows if r["verdict"] == "一致")
    tp = sum(1 for r in rows if r["expectNotify"] and r["notified"])
    fp = sum(1 for r in rows if not r["expectNotify"] and r["notified"])
    fn = sum(1 for r in rows if r["expectNotify"] and not r["notified"])
    tn = sum(1 for r in rows if not r["expectNotify"] and not r["notified"])
    lines = [
        "# C4 情境演練預檢（離線）",
        "",
        f"- 產出：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}；守護腦：{'規則層＋第二層 AI（正式線真路徑）' if with_ai else '只跑規則層（不連網）'}",
        f"- 劇本：{source}",
        "- 這是正式演練前的程式行為預檢，**不算進 C4 的 50 筆**；正式演練要在正式機用測試帳號灌資料、由場域護理人員逐筆判定。",
        "",
        f"**結果：{ok}／{len(rows)} 筆跟劇本預期一致**｜該通知且有發 {tp}、不該通知也沒發 {tn}、多發 {fp}、漏報 {fn}",
        "",
        "| 編號 | 規則 | 劇本預期 | 系統 | 結果 | 系統發的內容（固定句型） | 守護腦當場判 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        exp = ("通知：" + "＋".join(TYPE_LABELS[t] for t in r["expectTypes"])) if r["expectNotify"] else "不通知"
        got = ("發了：" + "＋".join(TYPE_LABELS[t] for t in r["gotTypes"])) if r["notified"] else "沒發"
        g = "；".join(f"{x['level']}（{x['via']}）" for x in r["guardian"]) or "—"
        facts = " ／ ".join(r["facts"]) or "—"
        lines.append(f"| {r['id']} | {r['rule']} | {exp} | {got} | {r['verdict']} | {facts} | {g} |")
    lines += ["", "## 跟劇本不一致的", ""]
    diffs = [r for r in rows if r["verdict"] != "一致"]
    if not diffs:
        lines.append("沒有。")
    for r in diffs:
        lines.append(f"- **{r['id']}**：{r['verdict']}。{r['note']}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=os.path.join(HERE, "c4_drill", "scenarios_v1.json"))
    ap.add_argument("--with-ai-review", action="store_true")
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    args = ap.parse_args()
    data = json.load(io.open(args.scenarios, encoding="utf-8"))
    rows = run(data["scenarios"], args.with_ai_review)
    md = render_md(rows, args.with_ai_review, data.get("source", ""))
    if args.out_json:
        io.open(args.out_json, "w", encoding="utf-8").write(json.dumps({"version": data.get("version"), "withAiReview": args.with_ai_review,
                                                                      "rows": rows}, ensure_ascii=False, indent=1))
    if args.out_md:
        io.open(args.out_md, "w", encoding="utf-8").write(md)
    print(md)


if __name__ == "__main__":
    main()
