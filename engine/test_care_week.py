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
