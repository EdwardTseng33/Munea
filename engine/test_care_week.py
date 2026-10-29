# -*- coding: utf-8 -*-
"""週關懷摘要（care_week.py）純函式測試（補助案 C2 · 2026-10-13）

測五件事：
1. 心情：每日聚合、個人基準線（期間前 14 天）、最低的一天帶原句。
2. 聯絡：通話次數、最長空檔、最後一次、到今天幾天沒聯絡。
3. 守護腦：只算 medium 以上、high／critical 另外加總。
4. 三條異常規則：連續 3 天 ≤ 2、比自己掉 2 級、N 天沒聯絡、守護腦亮燈——各自附「為什麼亮」。
5. 文字層不准出現判定／連線用語（可能因為、導致、分數、診斷…），沒資料要寫「沒有紀錄」。

跑法：python engine/test_care_week.py（純函式、不連網）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import care_week as cw  # noqa: E402

TODAY = "2026-10-13"


def _sig(date, level, mood="平穩", said="", concerns=None, positives=None):
    return {"date": date, "level": level, "mood": mood, "wordObs": said, "concerns": concerns or [], "positives": positives or []}


def _call(date):
    return {"createdAt": date + "T10:00:00Z", "summary": "x"}


def _ev(date, level, cats):
    return {"eventTime": date + "T09:00:00Z", "riskLevel": level, "categories": cats}


def _week(signals=None, summaries=None, events=None, days=7):
    return cw.build_person_week({"id": "p1", "nick": "美玉"}, signals, summaries, events, today=TODAY, days=days)


def test_period_bounds():
    s, e = cw.period_bounds(7, TODAY)
    assert (s.isoformat(), e.isoformat()) == ("2026-10-07", "2026-10-13")
    s, e = cw.period_bounds(99, TODAY)  # 亂塞上限 31
    assert (e - s).days == 30


def test_mood_daily_and_baseline():
    sig = [_sig("2026-09-25", 4), _sig("2026-09-30", 4), _sig("2026-10-05", 4),  # 期間前 14 天 → 基準線 4.0
           _sig("2026-10-08", 3, said="今天澆花"), _sig("2026-10-08", 1, said="老伴忌日，很想他"),
           _sig("2026-10-10", 5, positives=["孫子要結婚"]), _sig("2026-10-12", 2, concerns=["膝蓋痛"])]
    w = _week(sig)
    m = w["mood"]
    assert m["daysWithChat"] == 3 and m["baselineAverage"] == 4.0
    d8 = [x for x in m["daily"] if x["date"] == "2026-10-08"][0]
    assert d8["chats"] == 2 and d8["level"] == 2.0 and d8["said"] == "老伴忌日，很想他"  # 同一天取平均、話取最後一次
    assert m["lowestDay"]["date"] == "2026-10-08"
    assert m["positives"] == ["孫子要結婚"] and m["concerns"] == ["膝蓋痛"]
    assert w["spokenHealth"]["items"] == ["膝蓋痛"] and "本人口述" in w["spokenHealth"]["source"]


def test_contact_gap_and_since_last():
    calls = [_call("2026-10-07"), _call("2026-10-08"), _call("2026-10-12"), _call("2026-10-02")]
    c = _week(summaries=calls)["contact"]
    assert c["calls"] == 3 and c["daysWithCall"] == ["2026-10-07", "2026-10-08", "2026-10-12"]
    assert c["longestGapDays"] == 3  # 9、10、11
    assert c["lastCallDate"] == "2026-10-12" and c["daysSinceLastCall"] == 1
    assert _week(summaries=[{"createdAt": "2026-10-10T00:00:00Z", "deletedAt": "2026-10-11T00:00:00Z"}])["contact"]["empty"]


def test_safety_counts_only_medium_and_above():
    ev = [_ev("2026-10-09", "low", ["emotional_distress"]), _ev("2026-10-10", "medium", ["medical_boundary"]),
          _ev("2026-10-11", "high", ["medical_emergency_signal"]), _ev("2026-10-01", "critical", ["self_harm_crisis"])]
    s = _week(events=ev)["safety"]
    assert s["counts"] == {"medium": 1, "high": 1} and s["highOrCritical"] == 1
    assert [x["level"] for x in s["items"]] == ["medium", "high"]


def test_anomaly_mood_streak():
    sig = [_sig("2026-10-09", 2, said="沒什麼意思"), _sig("2026-10-10", 1), _sig("2026-10-11", 2, said="不想動")]
    a = cw.detect_anomalies(_week(sig, summaries=[_call("2026-10-13")]))
    types = [x["type"] for x in a]
    assert types == ["mood_drop"], a
    assert "連續 3 天" in a[0]["fact"] and a[0]["lastSaid"] == "不想動"


def test_anomaly_mood_drop_vs_self():
    sig = [_sig("2026-09-28", 5), _sig("2026-10-01", 5), _sig("2026-10-04", 4),  # 基準 4.7
           _sig("2026-10-11", 3), _sig("2026-10-12", 2), _sig("2026-10-13", 3)]   # 最近 2.7 → 掉 2.0
    a = cw.detect_anomalies(_week(sig, summaries=[_call("2026-10-13")]))
    assert [x["type"] for x in a] == ["mood_drop"] and "比自己前 14 天" in a[0]["fact"]
    # 掉不到 2 級就不亮
    sig2 = sig[:3] + [_sig("2026-10-11", 4), _sig("2026-10-12", 3), _sig("2026-10-13", 4)]
    assert cw.detect_anomalies(_week(sig2, summaries=[_call("2026-10-13")])) == []


def test_anomaly_no_contact():
    a = cw.detect_anomalies(_week(summaries=[_call("2026-10-09")]))  # 到 10/13 四天沒聯絡
    assert [x["type"] for x in a] == ["no_contact"] and "4 天沒聯絡" in a[0]["fact"]
    assert cw.detect_anomalies(_week(summaries=[_call("2026-10-09")]), {"noContactDays": 5}) == []  # 機構把 N 調 5 就不亮
    none = cw.detect_anomalies(_week())
    assert [x["type"] for x in none] == ["no_contact"] and "沒有任何通話紀錄" in none[0]["fact"]


def test_anomaly_guardian():
    a = cw.detect_anomalies(_week(summaries=[_call("2026-10-13")], events=[_ev("2026-10-11", "high", ["protection_event"])]))
    assert [x["type"] for x in a] == ["guardian"] and "高風險燈" in a[0]["fact"]


def test_render_text_is_fact_only():
    sig = [_sig("2026-10-08", 1, said="老伴忌日，很想他", concerns=["走幾步就喘"])]
    w = _week(sig, summaries=[_call("2026-10-08")], events=[_ev("2026-10-08", "high", ["medical_emergency_signal"])])
    text = cw.render_text(w, cw.detect_anomalies(w))
    for bad in cw.FORBIDDEN_WORDS:
        assert bad not in text, bad
    assert "本人口述" in text and "走幾步就喘" in text and "老伴忌日" in text
    assert "這週沒有紀錄" in text  # 量測那段沒資料要明寫
    assert "不是判定" in text
    empty = cw.render_text(_week())
    assert "沒有通話紀錄" in empty and "這週沒有紀錄" in empty and "沒有亮燈" in empty


def test_org_report_totals():
    w1 = _week([_sig("2026-10-10", 1), _sig("2026-10-11", 1), _sig("2026-10-12", 2)], summaries=[_call("2026-10-12")])
    w2 = cw.build_person_week({"id": "p2"}, [], [_call("2026-10-13")], [], today=TODAY)
    report = cw.build_org_report([w1, w2], {"p1": cw.detect_anomalies(w1), "p2": cw.detect_anomalies(w2)})
    t = report["totals"]
    assert t["people"] == 2 and t["withAnomaly"] == 1 and t["moodDrop"] == 1 and t["calls"] == 2
    assert report["period"]["end"] == TODAY


# ───── 2026-10-26 補：規則邊界、設定開關、資料界線（補助案 C3 要求自動化測試 ≥25 項）─────

def test_streak_resets_when_mood_recovers():
    # 低、低、好、低、低：中間好過一天，連續就要重算，不能亮
    sig = [_sig("2026-10-08", 2), _sig("2026-10-09", 1), _sig("2026-10-10", 4), _sig("2026-10-11", 2), _sig("2026-10-12", 2)]
    assert cw.detect_anomalies(_week(sig, summaries=[_call("2026-10-13")])) == []


def test_streak_threshold_is_a_setting():
    sig = [_sig("2026-10-11", 2), _sig("2026-10-12", 1)]
    w = _week(sig, summaries=[_call("2026-10-13")])
    assert cw.detect_anomalies(w) == []  # 預設要 3 天
    a = cw.detect_anomalies(w, {"lowMoodStreak": 2})
    assert [x["type"] for x in a] == ["mood_drop"] and "連續 2 天" in a[0]["fact"]


def test_no_baseline_means_no_drop_alarm():
    # 沒有前 14 天的紀錄就沒有「跟自己比」的對象，不能拿量表硬比
    sig = [_sig("2026-10-11", 3), _sig("2026-10-12", 3), _sig("2026-10-13", 3)]
    w = _week(sig, summaries=[_call("2026-10-13")])
    assert w["mood"]["baselineAverage"] is None and cw.detect_anomalies(w) == []


def test_drop_levels_is_a_setting():
    sig = [_sig("2026-09-28", 4), _sig("2026-10-02", 4), _sig("2026-10-11", 3), _sig("2026-10-12", 3), _sig("2026-10-13", 2)]  # 基準 4.0、最近 2.7
    w = _week(sig, summaries=[_call("2026-10-13")])
    assert cw.detect_anomalies(w) == []  # 掉 1.3 < 2
    assert [x["type"] for x in cw.detect_anomalies(w, {"moodDropLevels": 1})] == ["mood_drop"]


def test_only_one_mood_drop_alarm_even_if_both_rules_hit():
    sig = [_sig("2026-09-28", 5), _sig("2026-10-02", 5), _sig("2026-10-11", 1), _sig("2026-10-12", 1), _sig("2026-10-13", 1)]
    a = cw.detect_anomalies(_week(sig, summaries=[_call("2026-10-13")]))
    assert [x["type"] for x in a] == ["mood_drop"]  # 連續低＋掉很多只亮一盞，不重複吵人


def test_no_contact_looks_at_now_not_old_gaps():
    # 期間中間空了 4 天但昨天又通上了：只當事實寫，不亮燈
    c_week = _week(summaries=[_call("2026-10-07"), _call("2026-10-12")])
    assert c_week["contact"]["longestGapDays"] == 4
    assert cw.detect_anomalies(c_week) == []


def test_no_contact_setting_zero_or_none_falls_back_to_default():
    w = _week(summaries=[_call("2026-10-09")])  # 4 天沒聯絡
    for bad in ({"noContactDays": 0}, {"noContactDays": None}, {}):
        a = cw.detect_anomalies(w, bad)
        assert [x["type"] for x in a] == ["no_contact"] and "3 天提醒" in a[0]["fact"], bad


def test_guardian_alarm_ignores_medium():
    w = _week(summaries=[_call("2026-10-13")], events=[_ev("2026-10-10", "medium", ["medical_boundary"])] * 3)
    assert w["safety"]["counts"] == {"medium": 3}
    assert cw.detect_anomalies(w) == []
    w2 = _week(summaries=[_call("2026-10-13")], events=[_ev("2026-10-10", "critical", ["self_harm_crisis"])])
    a = cw.detect_anomalies(w2)
    assert [x["type"] for x in a] == ["guardian"] and "critical×1" in a[0]["fact"]


def test_signals_outside_period_and_baseline_are_ignored():
    sig = [_sig("2026-09-01", 1), _sig("2026-10-14", 1), _sig("2026-10-10", 4)]  # 太早、未來、期間內
    m = _week(sig)["mood"]
    assert m["daysWithChat"] == 1 and m["baselineAverage"] is None and m["weekAverage"] == 4.0


def test_period_start_day_counts_in_week_not_baseline():
    sig = [_sig("2026-10-07", 2), _sig("2026-10-06", 5)]  # 10/07 是期間第一天；10/06 是基準線最後一天
    m = _week(sig)["mood"]
    assert m["daysWithChat"] == 1 and m["weekAverage"] == 2.0 and m["baselineAverage"] == 5.0


def test_safety_categories_string_is_normalized_and_undated_rows_skipped():
    s = _week(events=[_ev("2026-10-10", "high", "medical_emergency_signal"), {"riskLevel": "high", "categories": ["x"]}])["safety"]
    assert s["items"] == [{"time": "2026-10-10T09:00:00Z", "level": "high", "categories": ["medical_emergency_signal"]}]


def test_contact_skips_undated_and_deleted_rows():
    c = _week(summaries=[{"summary": "沒日期"}, {"createdAt": "2026-10-10T00:00:00Z", "deletedAt": "2026-10-11T00:00:00Z"}, _call("2026-10-11")])["contact"]
    assert c["calls"] == 1 and c["daysWithCall"] == ["2026-10-11"]


def test_render_text_every_section_states_its_source():
    w = _week([_sig("2026-10-10", 3)], summaries=[_call("2026-10-10")])
    text = cw.render_text(w)
    for head in ("【聯絡】", "【心情】", "【身體・本人口述】", "【身體・量測】", "【守護腦】"):
        line = [l for l in text.splitlines() if l.startswith(head)][0]
        assert "來源：" in line, line
    assert "【要看一下】" not in text  # 沒異常就不放這段


def test_render_text_anomaly_section_only_when_present():
    w = _week(summaries=[_call("2026-10-09")])
    a = cw.detect_anomalies(w)
    assert "【要看一下】" in cw.render_text(w, a) and "沒聯絡" in cw.render_text(w, a)
    assert "【要看一下】" not in cw.render_text(w, [])


def test_org_report_keeps_input_order_and_counts_each_type():
    w1 = cw.build_person_week({"id": "p1"}, [], [_call("2026-10-09")], [], today=TODAY)   # no_contact
    w2 = cw.build_person_week({"id": "p2"}, [], [_call("2026-10-13")], [_ev("2026-10-12", "high", ["x"])], today=TODAY)  # guardian
    w3 = cw.build_person_week({"id": "p3"}, [], [_call("2026-10-13")], [], today=TODAY)   # 沒事
    r = cw.build_org_report([w3, w1, w2], {k: cw.detect_anomalies(w) for k, w in (("p1", w1), ("p2", w2), ("p3", w3))})
    assert [p["week"]["personId"] for p in r["people"]] == ["p3", "p1", "p2"]  # 不排名、不重排
    t = r["totals"]
    assert (t["people"], t["withAnomaly"], t["noContact"], t["guardian"], t["moodDrop"]) == (3, 2, 1, 1, 0)


def test_forbidden_words_list_covers_judgement_and_causality():
    for word in ("可能因為", "導致", "診斷", "分數", "憂鬱症"):
        assert word in cw.FORBIDDEN_WORDS


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", t.__name__, e)
    print("\n結果：%d 通過 / %d 失敗（共 %d）" % (len(tests) - failed, failed, len(tests)))
    sys.exit(1 if failed else 0)
